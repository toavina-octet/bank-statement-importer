from __future__ import annotations

import email
import imaplib
import logging
from collections.abc import Callable, Iterable
from datetime import datetime
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path

from app.logging.audit import audit_logger
from app.mail.exceptions import MailCollectionError
from app.mail.models import MailCredentials, MailMessage, PdfAttachment, SavedAttachment

ImapFactory = Callable[[str, int], imaplib.IMAP4]
logger = logging.getLogger(__name__)


class ImapStatementCollector:
    def __init__(
        self,
        credentials: MailCredentials,
        imap_factory: ImapFactory | None = None,
    ) -> None:
        self._credentials = credentials
        self._imap_factory = imap_factory or self._default_imap_factory

    def fetch_unseen_pdf_messages(self) -> list[MailMessage]:
        with self._connect() as mailbox:
            self._select_folder(mailbox)
            uids = self._search_unseen(mailbox)
            return [
                message
                for message in self._fetch_messages(mailbox, uids)
                if message.has_pdf_attachments
            ]

    def mark_as_processed(self, uid: str) -> None:
        with self._connect() as mailbox:
            self._select_folder(mailbox)
            status, _ = mailbox.uid("STORE", uid, "+FLAGS", "(\\Seen)")
            if status != "OK":
                raise MailCollectionError(f"Could not mark message as processed: {uid}")

    def _connect(self) -> imaplib.IMAP4:
        mailbox = self._imap_factory(self._credentials.host, self._credentials.port)
        try:
            status, _ = mailbox.login(self._credentials.username, self._credentials.password)
            if status != "OK":
                raise MailCollectionError("IMAP login failed")
            logger.info("IMAP connection successful: host=%s", self._credentials.host)
            audit_logger.log_connection_success(provider=f"imap:{self._credentials.host}")
            return mailbox
        except Exception as exc:
            logger.error(
                "IMAP connection failed: host=%s error=%s",
                self._credentials.host,
                exc,
            )
            audit_logger.log_connection_failure(
                provider=f"imap:{self._credentials.host}",
                error=exc,
            )
            raise

    def _select_folder(self, mailbox: imaplib.IMAP4) -> None:
        status, _ = mailbox.select(self._credentials.folder)
        if status != "OK":
            raise MailCollectionError(
                f"Could not select mailbox folder: {self._credentials.folder}"
            )

    def _search_unseen(self, mailbox: imaplib.IMAP4) -> list[str]:
        status, data = mailbox.uid("SEARCH", None, "UNSEEN")
        if status != "OK" or not data:
            raise MailCollectionError("Could not search unseen messages")
        return data[0].decode("ascii").split()

    def _fetch_messages(self, mailbox: imaplib.IMAP4, uids: Iterable[str]) -> list[MailMessage]:
        messages: list[MailMessage] = []
        for uid in uids:
            status, data = mailbox.uid("FETCH", uid, "(RFC822)")
            if status != "OK":
                raise MailCollectionError(f"Could not fetch message: {uid}")

            raw_message = _extract_raw_message(data)
            parsed_message = email.message_from_bytes(raw_message)
            messages.append(_parse_message(uid=uid, message=parsed_message))

        return messages

    def _default_imap_factory(self, host: str, port: int) -> imaplib.IMAP4:
        if self._credentials.use_ssl:
            return imaplib.IMAP4_SSL(host, port)
        return imaplib.IMAP4(host, port)


def save_pdf_attachments(message: MailMessage, target_dir: Path) -> list[SavedAttachment]:
    target_dir.mkdir(parents=True, exist_ok=True)
    saved: list[SavedAttachment] = []

    for attachment in message.attachments:
        safe_filename = _safe_filename(attachment.filename)
        destination = target_dir / f"{message.uid}_{safe_filename}"
        destination.write_bytes(attachment.content)
        saved.append(
            SavedAttachment(
                message_uid=message.uid,
                filename=attachment.filename,
                path=destination,
                size_bytes=attachment.size_bytes,
            )
        )

    return saved


def _extract_raw_message(data: list[bytes | tuple[bytes, bytes]]) -> bytes:
    for item in data:
        if isinstance(item, tuple) and len(item) == 2:
            return item[1]
    raise MailCollectionError("IMAP fetch response did not contain a raw message")


def _parse_message(uid: str, message: Message) -> MailMessage:
    return MailMessage(
        uid=uid,
        subject=_decode_header_value(message.get("Subject", "")),
        sender=_decode_header_value(message.get("From", "")),
        received_at=_parse_received_at(message.get("Date")),
        attachments=tuple(_extract_pdf_attachments(message)),
    )


def _extract_pdf_attachments(message: Message) -> list[PdfAttachment]:
    attachments: list[PdfAttachment] = []

    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue

        filename = part.get_filename()
        if not filename or not filename.lower().endswith(".pdf"):
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        attachments.append(
            PdfAttachment(
                filename=_decode_header_value(filename),
                content=payload,
            )
        )

    return attachments


def _decode_header_value(value: str) -> str:
    decoded_parts = email.header.decode_header(value)
    fragments: list[str] = []
    for fragment, encoding in decoded_parts:
        if isinstance(fragment, bytes):
            fragments.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            fragments.append(fragment)
    return "".join(fragments).strip()


def _parse_received_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _safe_filename(filename: str) -> str:
    sanitized = filename.replace("\\", "_").replace("/", "_").strip()
    return sanitized or "attachment.pdf"
