from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
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
