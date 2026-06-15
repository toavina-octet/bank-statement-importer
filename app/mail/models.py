from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class MailCredentials:
    host: str
    port: int
    username: str
    password: str
    folder: str = "INBOX"
    use_ssl: bool = True


@dataclass(frozen=True)
class PdfAttachment:
    filename: str
    content: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class MailMessage:
    uid: str
    subject: str
    sender: str
    received_at: datetime | None
    attachments: tuple[PdfAttachment, ...]

    @property
    def has_pdf_attachments(self) -> bool:
        return bool(self.attachments)


@dataclass(frozen=True)
class SavedAttachment:
    message_uid: str
    filename: str
    path: Path
    size_bytes: int
