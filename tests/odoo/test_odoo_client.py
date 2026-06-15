from datetime import UTC, date, datetime
from decimal import Decimal

from app.banking.models import StatementData
from app.odoo.client import OdooClient


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

    class FakeEnv(dict):
        def __init__(self, attachment_model: FakeAttachmentModel) -> None:
            super().__init__({"ir.attachment": attachment_model})
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
            "Old balance: 1000.00",
            "New balance: 1250.00",
            "Transactions: 0",
            "Coherent: True",
            "Sender: Bank <bank@example.com>",
            "Received at: 2026-06-11T08:30:00+00:00",
            "Message UID: 101",
        ]
    )
