from __future__ import annotations

import logging
from base64 import b64encode
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import odoorpc

from app.banking.models import StatementData, Transaction

logger = logging.getLogger(__name__)


class OdooClientError(Exception):
    """Raised when Odoo operations fail."""


class OdooClient:
    _ACCOUNT_TARGET_MAP: dict[str, str] = {
        "27234520161-90": "61-90 USD",
        "27234520100-79": "JOURNAL RELEVE",
    }

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
            target_model, target_id = self._resolve_attachment_target(
                data.account_number,
                data.statement_date,
                data,
            )

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
            if target_model and target_id is not None:
                attachment_payload["res_model"] = target_model
                attachment_payload["res_id"] = target_id

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

    def get_last_statement_balance(self, account_number: str) -> Decimal | None:
        journal_id = self._find_journal_id(account_number)
        if journal_id is None:
            logger.info("No Odoo journal mapping found for account %s", account_number)
            return None

        statement_id = self._find_last_bank_statement_id(
            journal_id,
            current_date=date.today(),
        )
        if statement_id is None:
            logger.info("No bank statement found in Odoo for journal id=%s", journal_id)
            return None

        statement = self._odoo.env["account.bank.statement"].browse(statement_id)
        balance_end = getattr(statement, "balance_end", None)
        if balance_end is None:
            balance_end = getattr(statement, "balance_end_real", None)

        if balance_end is None:
            logger.info("Bank statement %s has no ending balance field", statement_id)
            return None

        return Decimal(str(balance_end))

    def _resolve_attachment_target(
        self,
        account_number: str,
        statement_date: datetime.date,
        data: StatementData,
    ) -> tuple[str | None, int | None]:
        journal_id = self._find_journal_id(account_number)
        if journal_id is not None:
            statement_id = self._find_bank_statement_id(journal_id, statement_date)
            if statement_id is not None:
                self._update_bank_statement(statement_id, data)
                return "account.bank.statement", statement_id

            created_statement_id = self._create_bank_statement(journal_id, data)
            if created_statement_id is not None:
                return "account.bank.statement", created_statement_id

            return "account.journal", journal_id

        account_id = self._find_account_id(account_number)
        if account_id is not None:
            return "account.account", account_id

        return None, None

    def _find_journal_id(self, account_number: str) -> int | None:
        journal_name = self._map_account_number_to_journal_name(account_number)
        if journal_name is None:
            return None

        journal_id = self._search_one(
            "account.journal",
            [("name", "=", journal_name)],
            limit=1,
        )
        if journal_id is None:
            journal_id = self._search_one(
                "account.journal",
                [("code", "=", journal_name)],
                limit=1,
            )
        return journal_id

    def _find_last_bank_statement_id(
        self,
        journal_id: int,
        current_date: date | None = None,
    ) -> int | None:

        domain = [("journal_id", "=", journal_id)]

        if current_date is not None:
            domain.append(("date", "<", current_date.isoformat()))

        return self._search_one(
            "account.bank.statement",
            domain,
            limit=1,
            order="date desc",
        )

    def _find_bank_statement_id(self, journal_id: int, statement_date: datetime.date) -> int | None:
        return self._search_one(
            "account.bank.statement",
            [
                ("journal_id", "=", journal_id),
                ("date", "=", statement_date),
            ],
            limit=1,
        )

    def _create_bank_statement(self, journal_id: int, data: StatementData) -> int | None:
        try:
            last_balance = self.get_last_statement_balance(data.account_number)

            if last_balance is None:
                last_balance = data.old_balance

            statement_values = {
                "journal_id": journal_id,
                "date": data.statement_date.isoformat(),
                "balance_start": str(data.old_balance),
                "balance_end": str(data.new_balance),
                "name": f"BNI1 Relevé {data.statement_date.isoformat()}",
            }
            if self._supports_field("account.bank.statement", "balance_start_real"):
                statement_values["balance_start_real"] = str(data.old_balance)
            if self._supports_field("account.bank.statement", "balance_end_real"):
                statement_values["balance_end_real"] = str(data.new_balance)

            statement_id = self._odoo.env["account.bank.statement"].create(statement_values)
            if statement_id is not None:
                self._create_bank_statement_lines(statement_id, data.transactions)
            return statement_id
        except Exception as exc:
            logger.warning(
                "Failed to create account.bank.statement for journal_id=%s date=%s: %s",
                journal_id,
                data.statement_date,
                exc,
            )
            return None

    def _update_bank_statement(self, statement_id: int, data: StatementData) -> bool:
        try:
            statement_record = self._odoo.env["account.bank.statement"].browse(statement_id)

            last_balance = self.get_last_statement_balance(data.account_number)
            if last_balance is None:
                last_balance = data.old_balance

            update_values = {
                "balance_start": str(last_balance),
                "balance_end": str(data.new_balance),
                "name": f"BNI1 Relevé {data.statement_date.isoformat()}",
            }
            if self._supports_field("account.bank.statement", "balance_start_real"):
                update_values["balance_start_real"] = str(last_balance)
            if self._supports_field("account.bank.statement", "balance_end_real"):
                update_values["balance_end_real"] = str(data.new_balance)

            statement_record.write(update_values)

            line_ids = self._odoo.env["account.bank.statement.line"].search(
                [("statement_id", "=", statement_id)]
            )
            if line_ids not in (None, False, 0, []):
                self._odoo.env["account.bank.statement.line"].unlink(line_ids)

            self._create_bank_statement_lines(statement_id, data.transactions)

            return True
        except Exception as exc:
            logger.warning(
                "Failed to update account.bank.statement %s: %s",
                statement_id,
                exc,
            )
            return False

    def _create_bank_statement_lines(
        self,
        statement_id: int,
        transactions: tuple[Transaction, ...],
    ) -> Decimal:
        total = Decimal("0.00")
        try:
            line_model = self._odoo.env["account.bank.statement.line"]
            for transaction in transactions:
                line_model.create(
                    {
                        "statement_id": statement_id,
                        "date": transaction.date.isoformat(),
                        "name": transaction.label,
                        "payment_ref": transaction.label,
                        "amount": str(transaction.signed_amount),
                    }
                )
                total += transaction.signed_amount
        except Exception as exc:
            logger.warning(
                "Failed to create bank statement lines for statement_id=%s: %s",
                statement_id,
                exc,
            )
        return total

    def _find_account_id(self, account_number: str) -> int | None:
        account_name = self._map_account_number_to_journal_name(account_number)
        if account_name is None:
            return None

        account_id = self._search_one(
            "account.account",
            [("name", "=", account_name)],
            limit=1,
        )
        if account_id is None:
            account_id = self._search_one(
                "account.account",
                [("code", "=", account_name)],
                limit=1,
            )
        return account_id

    def _supports_field(self, model_name: str, field_name: str) -> bool:
        try:
            model = self._odoo.env[model_name]
            if not hasattr(model, "fields_get"):
                return False
            return field_name in model.fields_get()
        except Exception:
            return False

    def _search_one(
        self,
        model_name: str,
        domain: list[tuple[str, str, object]],
        **kwargs,
    ) -> int | None:
        normalized_domain = [
            (field, operator, self._normalize_value(value)) for field, operator, value in domain
        ]
        normalized_kwargs = {key: self._normalize_value(value) for key, value in kwargs.items()}

        record_ids = self._odoo.env[model_name].search(
            normalized_domain,
            **normalized_kwargs,
        )
        if record_ids in (None, False, 0, []):
            return None
        if isinstance(record_ids, int):
            return record_ids
        if isinstance(record_ids, list):
            return record_ids[0] if record_ids else None
        return None

    def _normalize_value(self, value: object) -> object:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return value

    def _map_account_number_to_journal_name(self, account_number: str) -> str | None:
        normalized = account_number.strip()
        return self._ACCOUNT_TARGET_MAP.get(normalized)

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
        transaction_summary = []
        for transaction in data.transactions[:5]:
            prefix = "+" if transaction.is_credit else "-"
            transaction_summary.append(
                f"{transaction.date.isoformat()} {transaction.label} {prefix}{transaction.amount}"
            )

        context_lines = [
            "Imported bank statement",
            f"Client: {client_name}",
            f"Account number: {data.account_number}",
            f"Statement date: {data.statement_date.isoformat()}",
            f"Balance initiale: {data.old_balance}",
            f"Solde final: {data.new_balance}",
            f"Transactions: {len(data.transactions)}",
            *transaction_summary,
            f"Coherent: {is_coherent}",
            f"Sender: {sender or ''}",
            f"Received at: {received_at.isoformat() if received_at else ''}",
            f"Message UID: {message_uid or ''}",
        ]

        return "\n".join(line for line in context_lines if line)
