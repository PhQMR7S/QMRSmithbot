from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.db.workflow_runtime_models import WorkflowExecutionRecord


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    project_id: UUID
    update_id: int
    workflow_version_id: UUID

    @property
    def value(self) -> str:
        raw = f"{self.project_id}:{self.update_id}:{self.workflow_version_id}".encode()
        return hashlib.sha256(raw).hexdigest()


class WorkflowExecutionStore:
    """Durable execution ledger with database-enforced duplicate suppression."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        *,
        project_id: UUID,
        tenant_id: UUID,
        update_id: int,
        workflow_version_id: UUID,
        workflow_version: int,
        trace_id: str,
    ) -> tuple[WorkflowExecutionRecord, bool]:
        """Atomically claim an execution key and return the durable record.

        PostgreSQL's unique constraint is the serialization primitive.  A
        select-then-insert sequence is intentionally avoided because two
        workers can otherwise observe the same missing row concurrently.
        """
        statement = (
            insert(WorkflowExecutionRecord)
            .values(
                project_id=project_id,
                tenant_id=tenant_id,
                update_id=update_id,
                workflow_version_id=workflow_version_id,
                workflow_version=workflow_version,
                status="running",
                attempts=0,
                visited_nodes=[],
                trace_id=trace_id,
            )
            .on_conflict_do_nothing(constraint="uq_workflow_execution_update_version")
            .returning(WorkflowExecutionRecord.id)
        )
        result = await self.session.execute(statement)
        created_id = result.scalar_one_or_none()
        if created_id is not None:
            record = await self.session.scalar(
                select(WorkflowExecutionRecord).where(WorkflowExecutionRecord.id == created_id)
            )
            if record is None:
                raise RuntimeError("workflow execution disappeared after insertion")
            return record, True

        existing = await self.session.scalar(
            select(WorkflowExecutionRecord)
            .where(
                WorkflowExecutionRecord.project_id == project_id,
                WorkflowExecutionRecord.update_id == update_id,
                WorkflowExecutionRecord.workflow_version_id == workflow_version_id,
            )
            .with_for_update()
        )
        if existing is None:
            raise RuntimeError("workflow execution conflict was not materialized")
        if existing.tenant_id != tenant_id:
            raise RuntimeError("workflow execution tenant invariant violated")
        return existing, False
