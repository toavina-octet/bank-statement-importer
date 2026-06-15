from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from app.mail import ImapStatementCollector, MailCredentials, save_pdf_attachments


class FakeImap:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.selected_folder: str | None = None
        self.stored: list[tuple[str, str, str]] = []

    def __enter__(self) -> FakeImap:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        assert username == "user@example.com"
        assert password == "secret"
        return "OK", [b"logged in"]

    def select(self, folder: str) -> tuple[str, list[bytes]]:
        self.selected_folder = folder
        return "OK", [b"1"]

    def uid(self, command: str, *args: object) -> tuple[str, list[bytes | tuple[bytes, bytes]]]:
        if command == "SEARCH":
            return "OK", [b"101 102"]
        if command == "FETCH" and args[0] == "101":
            return "OK", [(b"101 (RFC822 {1}", _build_message("statement.pdf", b"%PDF-1.4"))]
        if command == "FETCH" and args[0] == "102":
            return "OK", [(b"102 (RFC822 {1}", _build_message("notes.txt", b"hello"))]
        if command == "STORE":
            self.stored.append((str(args[0]), str(args[1]), str(args[2])))
            return "OK", [b"stored"]
        raise AssertionError(f"Unexpected IMAP command: {command} {args}")


def test_fetch_unseen_pdf_messages_filters_pdf_attachments() -> None:
    fake = FakeImap("imap.example.com", 993)
    collector = ImapStatementCollector(_credentials(), imap_factory=lambda host, port: fake)

    messages = collector.fetch_unseen_pdf_messages()

    assert len(messages) == 1
    assert messages[0].uid == "101"
    assert messages[0].sender == "Bank <bank@example.com>"
    assert messages[0].attachments[0].filename == "statement.pdf"
    assert messages[0].attachments[0].content == b"%PDF-1.4"
    assert fake.selected_folder == "INBOX"


def test_mark_as_processed_sets_seen_flag() -> None:
    fake = FakeImap("imap.example.com", 993)
    collector = ImapStatementCollector(_credentials(), imap_factory=lambda host, port: fake)

    collector.mark_as_processed("101")

    assert fake.stored == [("101", "+FLAGS", "(\\Seen)")]


def test_save_pdf_attachments_prefixes_message_uid(tmp_path: Path) -> None:
    fake = FakeImap("imap.example.com", 993)
    collector = ImapStatementCollector(_credentials(), imap_factory=lambda host, port: fake)
    message = collector.fetch_unseen_pdf_messages()[0]

    saved = save_pdf_attachments(message, tmp_path)

    assert saved[0].path == tmp_path / "101_statement.pdf"
    assert saved[0].path.read_bytes() == b"%PDF-1.4"
    assert saved[0].size_bytes == 8


def _credentials() -> MailCredentials:
    return MailCredentials(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
    )


def _build_message(filename: str, content: bytes) -> bytes:
    message = EmailMessage()
    message["From"] = "Bank <bank@example.com>"
    message["To"] = "statements@example.com"
    message["Subject"] = "Monthly statement"
    message["Date"] = "Tue, 09 Jun 2026 10:00:00 +0000"
    message.set_content("Please find the attached document.")
    maintype, subtype = ("application", "pdf") if filename.endswith(".pdf") else ("text", "plain")
    message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    return message.as_bytes()
