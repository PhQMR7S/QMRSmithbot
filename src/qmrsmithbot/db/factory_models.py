from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from qmrsmithbot.db.base import Base


class FactoryUpdateRecord(Base):
    __tablename__ = 'factory_updates'
    bot_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactoryConversationRecord(Base):
    __tablename__ = 'factory_conversations'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    step: Mapped[str] = mapped_column(String(32), nullable=False, default='idle')
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class TelegramLoginChallengeRecord(Base):
    __tablename__ = 'telegram_login_challenges'
    __table_args__ = (CheckConstraint('attempts >= 0 AND attempts <= 5',
                                     name='ck_telegram_login_attempts'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    browser_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    bot_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    approved_user_id: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramInlineBotRecord(Base):
    __tablename__ = 'telegram_inline_bots'
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),
        ForeignKey('bot_projects.id', ondelete='CASCADE'), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramInlineUpdateRecord(Base):
    __tablename__ = 'telegram_inline_updates'
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),
        ForeignKey('bot_projects.id', ondelete='CASCADE'), primary_key=True)
    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    response: Mapped[dict | None] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class FactoryButtonRecord(Base):
    __tablename__ = 'factory_buttons'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey('bot_projects.id', ondelete='CASCADE'), index=True)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey('factory_buttons.id', ondelete='CASCADE'), index=True)
    draft: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BotOwnerStateRecord(Base):
    __tablename__ = 'bot_owner_states'
    project_id: Mapped[UUID] = mapped_column(ForeignKey('bot_projects.id', ondelete='CASCADE'), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ContactDeliveryRecord(Base):
    __tablename__ = 'contact_deliveries'
    project_id: Mapped[UUID] = mapped_column(ForeignKey('bot_projects.id', ondelete='CASCADE'), primary_key=True)
    owner_message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    visitor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ContactBlockRecord(Base):
    __tablename__ = 'contact_blocks'
    project_id: Mapped[UUID] = mapped_column(ForeignKey('bot_projects.id', ondelete='CASCADE'), primary_key=True)
    visitor_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
