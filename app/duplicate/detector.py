from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import ProcessedDocument


class DuplicateDetector:
    def __init__(self, session: Session) -> None:
        self._session = session

    def is_duplicate(self, content: bytes) -> bool:
        document_hash = calculate_sha256(content)
        statement = select(ProcessedDocument.id).where(ProcessedDocument.sha256 == document_hash)
        return self._session.execute(statement).scalar_one_or_none() is not None

    def register_document(
        self,
        *,
        content: bytes,
        filename: str,
        message_uid: str,
        received_at: datetime | None,
    ) -> ProcessedDocument | None:
        document_hash = calculate_sha256(content)
        if self._is_duplicate_hash(document_hash):
            return None

        document = ProcessedDocument(
            sha256=document_hash,
            filename=filename,
            size_bytes=len(content),
            message_uid=message_uid,
            received_at=received_at,
        )
        self._session.add(document)
        self._session.flush()
        return document

    def _is_duplicate_hash(self, document_hash: str) -> bool:
        statement = select(ProcessedDocument.id).where(ProcessedDocument.sha256 == document_hash)
        return self._session.execute(statement).scalar_one_or_none() is not None


def calculate_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
