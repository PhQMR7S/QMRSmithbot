from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
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
