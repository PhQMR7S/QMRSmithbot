from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from qmrsmithbot.db.base import Base


class WorkflowExecutionRecord(Base):
    __tablename__ = "workflow_executions"
    __table_args__ = (
        UniqueConstraint("project_id", "update_id", "workflow_version_id", name="uq_workflow_execution_update_version"),
        CheckConstraint("attempts >= 0", name="ck_workflow_execution_attempts_nonnegative"),
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_workflow_execution_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bot_projects.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    workflow_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="CASCADE"), index=True)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visited_nodes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
