from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from qmrsmithbot.db.base import Base


class TelegramWebhookStateRecord(Base):
    __tablename__ = "telegram_webhook_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('inactive', 'active', 'error')",
            name="ck_telegram_webhook_states_status",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bot_projects.id", ondelete="CASCADE"), primary_key=True
    )
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="inactive")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TelegramUpdateInboxRecord(Base):
    __tablename__ = "telegram_update_inbox"
    __table_args__ = (
        UniqueConstraint("project_id", "update_id", name="uq_telegram_update_project_update"),
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_telegram_update_inbox_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bot_projects.id", ondelete="CASCADE"), index=True
    )
    telegram_bot_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
