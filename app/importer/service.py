from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.banking.models import StatementData
from app.banking.parser import BaseParser, ParsingError
from app.banking.validator import CoherenceError, validate_statement_coherence
from app.config import ClientConfig
from app.duplicate import DuplicateDetector, calculate_sha256
from app.logging.audit import audit_logger
from app.mail import ImapStatementCollector, MailMessage, save_pdf_attachments
from app.odoo.client import OdooClient, OdooClientError
from app.pdf.extractor import PdfExtractionError, PdfExtractor


@dataclass(frozen=True)
class ImportOutcome:
    client_slug: str
    message_uid: str
    filename: str
    status: str
    reason: str | None = None
    path: Path | None = None


@dataclass(frozen=True)
class ImportRunSummary:
    client_slug: str
    scanned_messages: int
    imported_documents: int
    duplicate_documents: int
    rejected_messages: int
    outcomes: tuple[ImportOutcome, ...]


class StatementImportService:
    def __init__(
        self,
        *,
        client: ClientConfig,
        collector: ImapStatementCollector,
        session: Session,
        inbox_dir: Path,
        pdf_extractor: PdfExtractor | None = None,
        parser: BaseParser | None = None,
        odoo_client: OdooClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._client = client
        self._collector = collector
        self._session = session
        self._inbox_dir = inbox_dir
        self._pdf_extractor = pdf_extractor or PdfExtractor()
        self._parser = parser
        self._odoo_client = odoo_client
        self._logger = logger or logging.getLogger(__name__)

    def run_once(self) -> ImportRunSummary:
        messages = self._collector.fetch_unseen_pdf_messages()
        detector = DuplicateDetector(self._session)
        outcomes: list[ImportOutcome] = []

        for message in messages:
            if not self._client.banking.is_authorized_sender(message.sender):
                outcomes.extend(self._reject_message(message, reason="unauthorized_sender"))
                continue

            saved_attachments = save_pdf_attachments(
                message,
                self._inbox_dir / self._client.slug,
            )

            for saved_attachment, attachment in zip(
                saved_attachments,
                message.attachments,
                strict=True,
            ):
                doc_record = detector.register_document(
                    content=attachment.content,
                    filename=attachment.filename,
                    message_uid=message.uid,
                    received_at=message.received_at,
                )

                if doc_record is None:
                    document_hash = calculate_sha256(attachment.content)
                    audit_logger.log_duplicate_detected(
                        client=self._client.slug,
                        hash_val=document_hash,
                    )
                    outcomes.append(
                        ImportOutcome(
                            client_slug=self._client.slug,
                            message_uid=message.uid,
                            filename=attachment.filename,
                            status="duplicate",
                            reason="sha256_already_processed",
                            path=saved_attachment.path,
                        )
                    )
                    continue

                # Set client slug on record
                doc_record.client_slug = self._client.slug

                # NEW: PDF Processing
                if self._parser:
                    try:
                        text = self._pdf_extractor.extract_text(saved_attachment.path)
                        data = self._parser.parse(text)
                        self._logger.info("Statement imported successfully")

                        if self._odoo_client:
                            last_balance = self._odoo_client.get_last_statement_balance(
                                data.account_number,
                            )
                            if last_balance is not None:
                                if last_balance != data.old_balance:
                                    self._logger.info(
                                        "Replacing parsed old balance with last Odoo ending balance for %s: %s",
                                        data.account_number,
                                        last_balance,
                                    )
                                data = StatementData(
                                    account_number=data.account_number,
                                    statement_date=data.statement_date,
                                    old_balance=last_balance,
                                    new_balance=data.new_balance,
                                    transactions=data.transactions,
                                )
                            else:
                                validate_statement_coherence(data)
                        else:
                            validate_statement_coherence(data)
                        
                        # Persist data for external scheduler or monitoring (Step 9)
                        doc_record.account_number = data.account_number
                        doc_record.statement_date = datetime.combine(
                            data.statement_date,
                            datetime.min.time(),
                        )
                        doc_record.old_balance = float(data.old_balance)
                        doc_record.new_balance = float(data.new_balance)
                        doc_record.is_coherent = True
                        
                        if self._odoo_client:
                            attachment_id = self._odoo_client.archive_statement(
                                data=data,
                                pdf_path=saved_attachment.path,
                                client_name=self._client.slug,
                                sender=message.sender,
                                received_at=message.received_at,
                                message_uid=message.uid,
                                is_coherent=True,
                            )
                            doc_record.odoo_attachment_id = attachment_id
                            
                            audit_logger.log_import_success(
                                client=self._client.slug,
                            )
                        
                    except (
                        PdfExtractionError,
                        ParsingError,
                        CoherenceError,
                        OdooClientError,
                    ) as exc:
                        doc_record.is_coherent = False
                        audit_logger.log_technical_error(
                            context=f"statement_import:{self._client.slug}:{attachment.filename}",
                            error=exc,
                        )
                        audit_logger.log_import_rejected(
                            client=self._client.slug,
                            reason=exc.__class__.__name__.lower(),
                            details={"filename": attachment.filename, "error": str(exc)},
                        )
                        outcomes.append(
                            ImportOutcome(
                                client_slug=self._client.slug,
                                message_uid=message.uid,
                                filename=attachment.filename,
                                status="rejected",
                                reason=str(exc),
                                path=saved_attachment.path,
                            )
                        )
                        continue

                outcomes.append(
                    ImportOutcome(
                        client_slug=self._client.slug,
                        message_uid=message.uid,
                        filename=attachment.filename,
                        status="imported",
                        path=saved_attachment.path,
                    )
                )

            self._collector.mark_as_processed(message.uid)

        summary = _build_summary(
            client_slug=self._client.slug,
            scanned_messages=len(messages),
            outcomes=outcomes,
        )
        self._logger.info(
            "Import run completed for client=%s scanned=%d imported=%d duplicates=%d rejected=%d",
            summary.client_slug,
            summary.scanned_messages,
            summary.imported_documents,
            summary.duplicate_documents,
            summary.rejected_messages,
        )
        return summary

    def _reject_message(self, message: MailMessage, reason: str) -> list[ImportOutcome]:
        audit_logger.log_import_rejected(
            client=self._client.slug,
            reason=reason,
            details={"uid": message.uid, "sender": message.sender},
        )
        self._collector.mark_as_processed(message.uid)
        return [
            ImportOutcome(
                client_slug=self._client.slug,
                message_uid=message.uid,
                filename=attachment.filename,
                status="rejected",
                reason=reason,
            )
            for attachment in message.attachments
        ]


def _build_summary(
    *,
    client_slug: str,
    scanned_messages: int,
    outcomes: list[ImportOutcome],
) -> ImportRunSummary:
    return ImportRunSummary(
        client_slug=client_slug,
        scanned_messages=scanned_messages,
        imported_documents=sum(outcome.status == "imported" for outcome in outcomes),
        duplicate_documents=sum(outcome.status == "duplicate" for outcome in outcomes),
        rejected_messages=len(
            {
                outcome.message_uid
                for outcome in outcomes
                if outcome.status == "rejected"
            }
        ),
        outcomes=tuple(outcomes),
    )
