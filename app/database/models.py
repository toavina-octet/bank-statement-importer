from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProcessedDocument(Base):
    __tablename__ = "processed_documents"
    __table_args__ = (UniqueConstraint("sha256", name="uq_processed_documents_sha256"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    message_uid: Mapped[str] = mapped_column(String(255), nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # New fields for n8n integration (CDC Step 9 & 10)
    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    statement_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    old_balance: Mapped[float | None] = mapped_column(nullable=True)
    new_balance: Mapped[float | None] = mapped_column(nullable=True)
    is_coherent: Mapped[bool | None] = mapped_column(nullable=True)
    odoo_attachment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_slug: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
