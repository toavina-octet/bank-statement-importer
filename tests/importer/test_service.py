from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy import create_engine

from app.banking.models import StatementData, Transaction
from app.config import BankingSettings, ClientConfig, MailboxSettings, OdooSettings
from app.database import create_session_factory, initialize_database
from app.importer import StatementImportService
from app.mail import MailMessage, PdfAttachment


class FakeCollector:
    def __init__(self, messages: list[MailMessage]) -> None:
        self._messages = messages
        self.processed_uids: list[str] = []

    def fetch_unseen_pdf_messages(self) -> list[MailMessage]:
        return self._messages

    def mark_as_processed(self, uid: str) -> None:
        self.processed_uids.append(uid)


def test_import_service_saves_authorized_pdf_and_registers_hash(tmp_path: Path) -> None:
    message = _message(sender="Bank <releves@example-bank.com>")
    collector = FakeCollector([message])
    session_factory = _session_factory()

    mock_extractor = MagicMock()
    mock_extractor.extract_text.return_value = "dummy text"
    mock_parser = MagicMock()
    mock_parser.parse.return_value = StatementData(
        account_number="FR123",
        statement_date=datetime.now().date(),
        old_balance=Decimal("0.00"),
        new_balance=Decimal("0.00"),
        transactions=(),
    )
    mock_odoo = MagicMock()

    with session_factory() as session:
        service = StatementImportService(
            client=_client(),
            collector=collector,  # type: ignore[arg-type]
            session=session,
            inbox_dir=tmp_path,
            pdf_extractor=mock_extractor,
            parser=mock_parser,
            odoo_client=mock_odoo,
        )

        summary = service.run_once()

        assert summary.scanned_messages == 1
        assert summary.imported_documents == 1
        assert summary.duplicate_documents == 0
        assert summary.rejected_messages == 0
        assert collector.processed_uids == ["101"]
        assert (tmp_path / "vinamora" / "101_statement.pdf").read_bytes() == b"%PDF-1.4"
        mock_extractor.extract_text.assert_called_once()
        mock_parser.parse.assert_called_once_with("dummy text")
        mock_odoo.archive_statement.assert_called_once()


def test_import_service_uses_last_odoo_balance_as_initial_balance(
    tmp_path: Path, monkeypatch
) -> None:
    message = _message(sender="Bank <releves@example-bank.com>")
    collector = FakeCollector([message])
    session_factory = _session_factory()

    mock_extractor = MagicMock()
    mock_extractor.extract_text.return_value = "dummy text"
    mock_parser = MagicMock()
    mock_parser.parse.return_value = StatementData(
        account_number="FR123",
        statement_date=datetime.now().date(),
        old_balance=Decimal("1000.00"),
        new_balance=Decimal("1500.00"),
        transactions=(),
    )
    mock_odoo = MagicMock()
    mock_odoo.get_last_statement_balance.return_value = Decimal("999999.99")

    mock_validate = MagicMock()
    monkeypatch.setattr("app.importer.service.validate_statement_coherence", mock_validate)

    with session_factory() as session:
        service = StatementImportService(
            client=_client(),
            collector=collector,  # type: ignore[arg-type]
            session=session,
            inbox_dir=tmp_path,
            pdf_extractor=mock_extractor,
            parser=mock_parser,
            odoo_client=mock_odoo,
        )

        summary = service.run_once()

        assert summary.imported_documents == 1
        assert summary.rejected_messages == 0
        mock_odoo.archive_statement.assert_called_once()
        archived_data = mock_odoo.archive_statement.call_args[1]["data"]
        assert archived_data.old_balance == Decimal("999999.99")
        assert archived_data.new_balance == Decimal("1500.00")
        assert archived_data.transactions == ()
        mock_validate.assert_not_called()


def test_import_service_preserves_transactions_after_odoo_balance_override(tmp_path: Path) -> None:
    message = _message(sender="Bank <releves@example-bank.com>")
    collector = FakeCollector([message])
    session_factory = _session_factory()

    mock_extractor = MagicMock()
    mock_extractor.extract_text.return_value = "dummy text"
    mock_parser = MagicMock()
    mock_parser.parse.return_value = StatementData(
        account_number="FR123",
        statement_date=datetime.now().date(),
        old_balance=Decimal("1000.00"),
        new_balance=Decimal("1050.00"),
        transactions=(
            Transaction(
                date=datetime.now().date(), label="TX1", amount=Decimal("100.00"), is_credit=False
            ),
            Transaction(
                date=datetime.now().date(), label="TX2", amount=Decimal("150.00"), is_credit=True
            ),
        ),
    )
    mock_odoo = MagicMock()
    mock_odoo.get_last_statement_balance.return_value = Decimal("999999.99")

    with session_factory() as session:
        service = StatementImportService(
            client=_client(),
            collector=collector,  # type: ignore[arg-type]
            session=session,
            inbox_dir=tmp_path,
            pdf_extractor=mock_extractor,
            parser=mock_parser,
            odoo_client=mock_odoo,
        )

        summary = service.run_once()

        assert summary.imported_documents == 1
        assert summary.rejected_messages == 0
        mock_odoo.archive_statement.assert_called_once()
        archived_data = mock_odoo.archive_statement.call_args[1]["data"]
        assert archived_data.old_balance == Decimal("999999.99")
        assert archived_data.new_balance == Decimal("1050.00")
        assert len(archived_data.transactions) == 2
        assert archived_data.transactions[0].label == "TX1"
        assert archived_data.transactions[1].label == "TX2"


def test_import_service_rejects_unauthorized_sender(tmp_path: Path) -> None:
    collector = FakeCollector([_message(sender="Fraud <fraud@example.com>")])
    session_factory = _session_factory()

    with session_factory() as session:
        service = StatementImportService(
            client=_client(),
            collector=collector,  # type: ignore[arg-type]
            session=session,
            inbox_dir=tmp_path,
        )

        summary = service.run_once()

        assert summary.imported_documents == 0
        assert summary.duplicate_documents == 0
        assert summary.rejected_messages == 1
        assert summary.outcomes[0].status == "rejected"
        assert summary.outcomes[0].reason == "unauthorized_sender"
        assert collector.processed_uids == ["101"]
        assert not (tmp_path / "vinamora").exists()


def test_import_service_reports_duplicate_documents(tmp_path: Path) -> None:
    collector = FakeCollector([_message(uid="101"), _message(uid="102")])
    session_factory = _session_factory()

    with session_factory() as session:
        service = StatementImportService(
            client=_client(),
            collector=collector,  # type: ignore[arg-type]
            session=session,
            inbox_dir=tmp_path,
        )

        summary = service.run_once()

        assert summary.imported_documents == 1
        assert summary.duplicate_documents == 1
        assert [outcome.status for outcome in summary.outcomes] == ["imported", "duplicate"]
        assert collector.processed_uids == ["101", "102"]


def _session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    initialize_database(engine)
    return create_session_factory(engine)


def _client() -> ClientConfig:
    return ClientConfig(
        slug="vinamora",
        odoo=OdooSettings(
            version=19,
            url="https://odoo.example.com",
            database="vinamora",
            username="technical-user@example.com",
            password_env="VINAMORA_ODOO_PASSWORD",
        ),
        mailbox=MailboxSettings(
            email="statements@example.com",
            host="imap.example.com",
            port=993,
            username="statements@example.com",
            password_env="VINAMORA_IMAP_PASSWORD",
        ),
        banking=BankingSettings(authorized_senders=("releves@example-bank.com",)),
    )


def _message(
    *,
    uid: str = "101",
    sender: str = "Bank <releves@example-bank.com>",
) -> MailMessage:
    return MailMessage(
        uid=uid,
        subject="Monthly statement",
        sender=sender,
        received_at=datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
        attachments=(PdfAttachment(filename="statement.pdf", content=b"%PDF-1.4"),),
    )
