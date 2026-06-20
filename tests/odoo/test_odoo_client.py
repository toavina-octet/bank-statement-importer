from datetime import UTC, date, datetime
from decimal import Decimal

from app.banking.models import StatementData, Transaction
from app.odoo.client import OdooClient


class FakeAttachment:
    def __init__(self, id: int, values: dict[str, object]) -> None:
        self.id = id
        self.name = values["name"]
        self.res_model = values.get("res_model")
        self.res_id = values.get("res_id")
        self.create_uid = None
        self.company_id = None


def test_archive_statement_sends_pdf_as_base64(tmp_path, monkeypatch) -> None:
    created_values: dict[str, object] = {}

    class FakeRelatedUser:
        def __init__(self, id: int) -> None:
            self.id = id

    class FakeRelatedCompany:
        def __init__(self, id: int) -> None:
            self.id = id

    class FakeAttachment:
        def __init__(self, id: int, values: dict[str, object]) -> None:
            self.id = id
            self.name = values["name"]
            self.res_model = values.get("res_model")
            self.res_id = values.get("res_id")
            self.create_uid = FakeRelatedUser(30)
            self.company_id = FakeRelatedCompany(1)

    class FakeAttachmentModel:
        def __init__(self) -> None:
            self._created_values: dict[str, object] = {}

        def create(self, values: dict[str, object]) -> int:
            self._created_values = values
            created_values.update(values)
            return 42

        def browse(self, attachment_id: int) -> FakeAttachment:
            return FakeAttachment(attachment_id, self._created_values)

        def search_count(self, _domain: list[tuple[str, str, int]]) -> int:
            return 1

        def search(self, _domain: list[tuple[str, str, int]]) -> list[int]:
            return [42]

    class FakeAccountModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain in (
                [("name", "=", "61-90 USD")],
                [("code", "=", "61-90 USD")],
            )
            return []

    class FakeEnv(dict):
        def __init__(self, attachment_model: FakeAttachmentModel) -> None:
            super().__init__(
                {
                    "ir.attachment": attachment_model,
                    "account.account": FakeAccountModel(),
                }
            )
            self.uid = 1

    class FakeOdoo:
        def __init__(self, host: str, protocol: str, port: int) -> None:
            self.host = host
            self.protocol = protocol
            self.port = port
            self.env = FakeEnv(FakeAttachmentModel())

    monkeypatch.setattr("app.odoo.client.odoorpc.ODOO", FakeOdoo)
    pdf_path = tmp_path / "statement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    client = OdooClient(
        url="https://odoo.example.com",
        db="db",
        username="user",
        password="secret",
        version=19,
    )

    attachment_id = client.archive_statement(
        data=StatementData(
            account_number="ACC-1",
            statement_date=date(2026, 6, 10),
            old_balance=Decimal("1000.00"),
            new_balance=Decimal("1250.00"),
            transactions=(),
        ),
        pdf_path=pdf_path,
        client_name="vinamora",
        sender="Bank <bank@example.com>",
        received_at=datetime(2026, 6, 11, 8, 30, tzinfo=UTC),
        message_uid="101",
        is_coherent=True,
    )

    assert attachment_id == 42
    assert created_values["datas"] == "JVBERi0xLjQ="
    assert created_values["mimetype"] == "application/pdf"
    assert "res_model" not in created_values
    assert "res_id" not in created_values
    assert created_values["description"] == "\n".join(
        [
            "Imported bank statement",
            "Client: vinamora",
            "Account number: ACC-1",
            "Statement date: 2026-06-10",
            "Balance initiale: 1000.00",
            "Solde final: 1250.00",
            "Transactions: 0",
            "Coherent: True",
            "Sender: Bank <bank@example.com>",
            "Received at: 2026-06-11T08:30:00+00:00",
            "Message UID: 101",
        ]
    )


def test_archive_statement_attaches_to_dashboard_account(monkeypatch, tmp_path) -> None:
    created_values: dict[str, object] = {}

    class FakeAccountModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("name", "=", "61-90 USD")]
            return [55]

    class FakeAttachmentModel:
        def __init__(self) -> None:
            self._created_values: dict[str, object] = {}

        def create(self, values: dict[str, object]) -> int:
            self._created_values = values
            created_values.update(values)
            return 42

        def browse(self, attachment_id: int) -> FakeAttachment:
            return FakeAttachment(attachment_id, self._created_values)

    class FakeJournalModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain in (
                [("name", "=", "61-90 USD")],
                [("code", "=", "61-90 USD")],
            )
            return []

    class FakeEnv(dict):
        def __init__(self) -> None:
            super().__init__(
                {
                    "ir.attachment": FakeAttachmentModel(),
                    "account.account": FakeAccountModel(),
                    "account.journal": FakeJournalModel(),
                }
            )

    class FakeOdoo:
        def __init__(self, host: str, protocol: str, port: int) -> None:
            self.host = host
            self.protocol = protocol
            self.port = port
            self.env = FakeEnv()

    monkeypatch.setattr("app.odoo.client.odoorpc.ODOO", FakeOdoo)

    pdf_path = tmp_path / "statement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    client = OdooClient(
        url="https://odoo.example.com",
        db="db",
        username="user",
        password="secret",
        version=19,
    )

    attachment_id = client.archive_statement(
        data=StatementData(
            account_number="27234520161-90",
            statement_date=date(2026, 6, 10),
            old_balance=Decimal("1000.00"),
            new_balance=Decimal("1250.00"),
            transactions=(),
        ),
        pdf_path=pdf_path,
        client_name="vinamora",
        sender="Bank <bank@example.com>",
        received_at=datetime(2026, 6, 11, 8, 30, tzinfo=UTC),
        message_uid="101",
        is_coherent=True,
    )

    assert attachment_id == 42
    assert created_values["res_model"] == "account.account"
    assert created_values["res_id"] == 55
    assert "Balance initiale: 1000.00" in created_values["description"]
    assert "Solde final: 1250.00" in created_values["description"]


def test_archive_statement_attaches_to_statement_by_date(monkeypatch, tmp_path) -> None:
    created_values: dict[str, object] = {}

    class FakeStatementRecord:
        def __init__(
            self, balance_end: Decimal | None = None, balance_end_real: Decimal | None = None
        ) -> None:
            self.balance_end = balance_end
            self.balance_end_real = balance_end_real

    class FakeJournalModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("name", "=", "61-90 USD")]
            return [11]

    class FakeStatementModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            if domain == [("journal_id", "=", 11), ("date", "=", "2026-06-10")]:
                return [22]
            raise AssertionError(f"Unexpected domain: {domain}")

        def browse(self, statement_id: int) -> FakeStatementRecord:
            assert statement_id == 22
            return FakeStatementRecord(balance_end=Decimal("9876.54"))

        def write(self, values: dict[str, object]) -> bool:
            assert values["balance_start"] == "1000.00"
            assert values["balance_end"] == "1250.00"
            assert values["name"] == "BNI1 Relevé 2026-06-10"
            return True

    class FakeAttachmentModel:
        def __init__(self) -> None:
            self._created_values: dict[str, object] = {}

        def create(self, values: dict[str, object]) -> int:
            self._created_values = values
            created_values.update(values)
            return 42

        def browse(self, attachment_id: int) -> FakeAttachment:
            return FakeAttachment(attachment_id, self._created_values)

    class FakeEnv(dict):
        def __init__(self) -> None:
            super().__init__(
                {
                    "ir.attachment": FakeAttachmentModel(),
                    "account.journal": FakeJournalModel(),
                    "account.bank.statement": FakeStatementModel(),
                }
            )

    class FakeOdoo:
        def __init__(self, host: str, protocol: str, port: int) -> None:
            self.host = host
            self.protocol = protocol
            self.port = port
            self.env = FakeEnv()

    monkeypatch.setattr("app.odoo.client.odoorpc.ODOO", FakeOdoo)

    pdf_path = tmp_path / "statement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    client = OdooClient(
        url="https://odoo.example.com",
        db="db",
        username="user",
        password="secret",
        version=19,
    )

    attachment_id = client.archive_statement(
        data=StatementData(
            account_number="27234520161-90",
            statement_date=date(2026, 6, 10),
            old_balance=Decimal("1000.00"),
            new_balance=Decimal("1250.00"),
            transactions=(),
        ),
        pdf_path=pdf_path,
        client_name="vinamora",
        sender="Bank <bank@example.com>",
        received_at=datetime(2026, 6, 11, 8, 30, tzinfo=UTC),
        message_uid="101",
        is_coherent=True,
    )

    assert attachment_id == 42
    assert created_values["res_model"] == "account.bank.statement"
    assert created_values["res_id"] == 22
    assert "Balance initiale: 1000.00" in created_values["description"]
    assert "Solde final: 1250.00" in created_values["description"]


def test_archive_statement_creates_bank_statement_when_date_missing(monkeypatch, tmp_path) -> None:
    created_values: dict[str, object] = {}
    created_statement_values: dict[str, object] = {}
    created_lines: list[dict[str, object]] = []

    class FakeJournalModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("name", "=", "61-90 USD")]
            return [11]

    class FakeStatementModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("journal_id", "=", 11), ("date", "=", "2026-06-10")]
            return []

        def create(self, values: dict[str, object]) -> int:
            created_statement_values.update(values)
            return 22

        def fields_get(self) -> dict[str, object]:
            return {"balance_end_real": {}}

    class FakeStatementLineModel:
        def create(self, values: dict[str, object]) -> int:
            created_lines.append(values)
            return 101

    class FakeAttachmentModel:
        def __init__(self) -> None:
            self._created_values: dict[str, object] = {}

        def create(self, values: dict[str, object]) -> int:
            self._created_values = values
            created_values.update(values)
            return 42

        def browse(self, attachment_id: int) -> FakeAttachment:
            return FakeAttachment(attachment_id, self._created_values)

    class FakeEnv(dict):
        def __init__(self) -> None:
            super().__init__(
                {
                    "ir.attachment": FakeAttachmentModel(),
                    "account.journal": FakeJournalModel(),
                    "account.bank.statement": FakeStatementModel(),
                    "account.bank.statement.line": FakeStatementLineModel(),
                }
            )

    class FakeOdoo:
        def __init__(self, host: str, protocol: str, port: int) -> None:
            self.host = host
            self.protocol = protocol
            self.port = port
            self.env = FakeEnv()

    monkeypatch.setattr("app.odoo.client.odoorpc.ODOO", FakeOdoo)

    pdf_path = tmp_path / "statement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    client = OdooClient(
        url="https://odoo.example.com",
        db="db",
        username="user",
        password="secret",
        version=19,
    )

    attachment_id = client.archive_statement(
        data=StatementData(
            account_number="27234520161-90",
            statement_date=date(2026, 6, 10),
            old_balance=Decimal("1000.00"),
            new_balance=Decimal("1250.00"),
            transactions=(
                Transaction(
                    date=date(2026, 6, 10), label="TX1", amount=Decimal("100.00"), is_credit=False
                ),
                Transaction(
                    date=date(2026, 6, 10), label="TX2", amount=Decimal("150.00"), is_credit=True
                ),
            ),
        ),
        pdf_path=pdf_path,
        client_name="vinamora",
        sender="Bank <bank@example.com>",
        received_at=datetime(2026, 6, 11, 8, 30, tzinfo=UTC),
        message_uid="101",
        is_coherent=True,
    )

    assert attachment_id == 42
    assert created_statement_values["journal_id"] == 11
    assert created_statement_values["date"] == "2026-06-10"
    assert created_statement_values["balance_start"] == "1000.00"
    assert created_statement_values["balance_end"] == "1250.00"
    assert created_lines == [
        {
            "statement_id": 22,
            "date": "2026-06-10",
            "name": "TX1",
            "payment_ref": "TX1",
            "amount": "-100.00",
        },
        {
            "statement_id": 22,
            "date": "2026-06-10",
            "name": "TX2",
            "payment_ref": "TX2",
            "amount": "150.00",
        },
        {
            "statement_id": 22,
            "date": "2026-06-10",
            "name": "Ajustement solde final",
            "payment_ref": "Ajustement solde final",
            "amount": "200.00",
        },
    ]
    assert created_values["res_model"] == "account.bank.statement"
    assert created_values["res_id"] == 22


def test_get_last_statement_balance_from_odoo_statement(monkeypatch) -> None:
    class FakeStatementRecord:
        def __init__(
            self, balance_end: Decimal | None = None, balance_end_real: Decimal | None = None
        ) -> None:
            self.balance_end = balance_end
            self.balance_end_real = balance_end_real

    class FakeJournalModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("name", "=", "61-90 USD")]
            return [11]

    class FakeStatementModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("journal_id", "=", 11)]
            return [22]

        def browse(self, statement_id: int) -> FakeStatementRecord:
            assert statement_id == 22
            return FakeStatementRecord(balance_end=Decimal("9876.54"))

    class FakeAttachmentModel:
        def __init__(self) -> None:
            self._created_values: dict[str, object] = {}

        def create(self, values: dict[str, object]) -> int:
            self._created_values = values
            return 42

        def browse(self, attachment_id: int) -> FakeAttachment:
            return FakeAttachment(attachment_id, self._created_values)

    class FakeEnv(dict):
        def __init__(self) -> None:
            super().__init__(
                {
                    "ir.attachment": FakeAttachmentModel(),
                    "account.journal": FakeJournalModel(),
                    "account.bank.statement": FakeStatementModel(),
                }
            )

    class FakeOdoo:
        def __init__(self, host: str, protocol: str, port: int) -> None:
            self.host = host
            self.protocol = protocol
            self.port = port
            self.env = FakeEnv()

    monkeypatch.setattr("app.odoo.client.odoorpc.ODOO", FakeOdoo)

    client = OdooClient(
        url="https://odoo.example.com",
        db="db",
        username="user",
        password="secret",
        version=19,
    )

    balance = client.get_last_statement_balance("27234520161-90")

    assert balance == Decimal("9876.54")


def test_get_last_statement_balance_returns_none_when_no_statement(monkeypatch) -> None:
    class FakeJournalModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("name", "=", "61-90 USD")]
            return [11]

    class FakeStatementModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("journal_id", "=", 11)]
            return 0

    class FakeAttachmentModel:
        def __init__(self) -> None:
            self._created_values: dict[str, object] = {}

        def create(self, values: dict[str, object]) -> int:
            self._created_values = values
            return 42

    class FakeEnv(dict):
        def __init__(self) -> None:
            super().__init__(
                {
                    "ir.attachment": FakeAttachmentModel(),
                    "account.journal": FakeJournalModel(),
                    "account.bank.statement": FakeStatementModel(),
                }
            )

    class FakeOdoo:
        def __init__(self, host: str, protocol: str, port: int) -> None:
            self.host = host
            self.protocol = protocol
            self.port = port
            self.env = FakeEnv()

    monkeypatch.setattr("app.odoo.client.odoorpc.ODOO", FakeOdoo)

    client = OdooClient(
        url="https://odoo.example.com",
        db="db",
        username="user",
        password="secret",
        version=19,
    )

    balance = client.get_last_statement_balance("27234520161-90")

    assert balance is None


def test_archive_statement_attaches_to_last_statement(monkeypatch, tmp_path) -> None:
    created_values: dict[str, object] = {}

    class FakeStatementRecord:
        def __init__(
            self, balance_end: Decimal | None = None, balance_end_real: Decimal | None = None
        ) -> None:
            self.balance_end = balance_end
            self.balance_end_real = balance_end_real

    class FakeJournalModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("name", "=", "61-90 USD")]
            return [11]

    class FakeStatementModel:
        def search(self, domain: list[tuple[str, str, object]], **kwargs):
            assert domain == [("journal_id", "=", 11), ("date", "=", "2026-06-10")]
            return [22]

        def browse(self, statement_id: int) -> FakeStatementRecord:
            assert statement_id == 22
            return FakeStatementRecord(balance_end=Decimal("9876.54"))

    class FakeAttachmentModel:
        def __init__(self) -> None:
            self._created_values: dict[str, object] = {}

        def create(self, values: dict[str, object]) -> int:
            self._created_values = values
            created_values.update(values)
            return 42

        def browse(self, attachment_id: int) -> FakeAttachment:
            return FakeAttachment(attachment_id, self._created_values)

    class FakeEnv(dict):
        def __init__(self) -> None:
            super().__init__(
                {
                    "ir.attachment": FakeAttachmentModel(),
                    "account.journal": FakeJournalModel(),
                    "account.bank.statement": FakeStatementModel(),
                }
            )

    class FakeOdoo:
        def __init__(self, host: str, protocol: str, port: int) -> None:
            self.host = host
            self.protocol = protocol
            self.port = port
            self.env = FakeEnv()

    monkeypatch.setattr("app.odoo.client.odoorpc.ODOO", FakeOdoo)

    pdf_path = tmp_path / "statement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    client = OdooClient(
        url="https://odoo.example.com",
        db="db",
        username="user",
        password="secret",
        version=19,
    )

    attachment_id = client.archive_statement(
        data=StatementData(
            account_number="27234520161-90",
            statement_date=date(2026, 6, 10),
            old_balance=Decimal("1000.00"),
            new_balance=Decimal("1250.00"),
            transactions=(),
        ),
        pdf_path=pdf_path,
        client_name="vinamora",
        sender="Bank <bank@example.com>",
        received_at=datetime(2026, 6, 11, 8, 30, tzinfo=UTC),
        message_uid="101",
        is_coherent=True,
    )

    assert attachment_id == 42
    assert created_values["res_model"] == "account.bank.statement"
    assert created_values["res_id"] == 22
    assert "Balance initiale: 1000.00" in created_values["description"]
    assert "Solde final: 1250.00" in created_values["description"]
