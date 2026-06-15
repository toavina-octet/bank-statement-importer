from __future__ import annotations

import logging
from base64 import b64encode
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import odoorpc

from app.banking.models import StatementData

logger = logging.getLogger(__name__)


class OdooClientError(Exception):
    """Raised when Odoo operations fail."""


class OdooClient:
    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        password: str,
        version: int,
        protocol: str = "jsonrpc+ssl",
        port: int = 443,
    ) -> None:
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        self.version = version
        
        # Initialize OdooRPC
        # Parse host and port from the configured URL.
        parsed_url = urlparse(url)
        host = parsed_url.hostname or url
        port = parsed_url.port or port
        self._odoo = odoorpc.ODOO(host, protocol=protocol, port=port)

    def login(self) -> None:
        try:
            self._odoo.login(self.db, self.username, self.password)
            logger.info("Logged in to Odoo %s at %s", self.version, self.url)
        except Exception as exc:
            logger.error("Odoo login failed: %s", exc)
            raise OdooClientError(f"Login failed: {exc}") from exc

    def archive_statement(
        self,
        data: StatementData,
        pdf_path: Path,
        client_name: str,
        *,
        sender: str | None = None,
        received_at: datetime | None = None,
        message_uid: str | None = None,
        is_coherent: bool = True,
    ) -> int:
        """Upload the processed statement PDF and its extracted metadata to Odoo."""
        try:
            with open(pdf_path, "rb") as f:
                content = b64encode(f.read()).decode("ascii")

            attachment_payload = {
                "name": pdf_path.name,
                "datas": content,
                "mimetype": "application/pdf",
                "description": self._build_attachment_description(
                    data=data,
                    client_name=client_name,
                    sender=sender,
                    received_at=received_at,
                    message_uid=message_uid,
                    is_coherent=is_coherent,
                ),
            }

            attachment_id = self._odoo.env["ir.attachment"].create(attachment_payload)

            logger.info("Created Odoo attachment id=%s", attachment_id)
            try:
                self._odoo.env["ir.attachment"].browse(attachment_id)

                logger.info(
                    "Attachment browse completed for id=%s",
                    attachment_id,
                )
            except Exception as exc:
                logger.warning(
                    "Odoo attachment follow-up check failed for id=%s: %s",
                    attachment_id,
                    exc,
                )

            return attachment_id

        except Exception as exc:
            logger.error("Failed to archive statement in Odoo: %s", exc)
            raise OdooClientError(f"Archiving failed: {exc}") from exc

    def _build_attachment_description(
        self,
        *,
        data: StatementData,
        client_name: str,
        sender: str | None,
        received_at: datetime | None,
        message_uid: str | None,
        is_coherent: bool,
    ) -> str:
        return "\n".join(
            [
                "Imported bank statement",
                f"Client: {client_name}",
                f"Account number: {data.account_number}",
                f"Statement date: {data.statement_date.isoformat()}",
                f"Old balance: {data.old_balance}",
                f"New balance: {data.new_balance}",
                f"Transactions: {len(data.transactions)}",
                f"Coherent: {is_coherent}",
                f"Sender: {sender or ''}",
                f"Received at: {received_at.isoformat() if received_at else ''}",
                f"Message UID: {message_uid or ''}",
            ]
        )
