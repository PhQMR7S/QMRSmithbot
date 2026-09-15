from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.db.models import WorkflowVersionRecord
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
    """Durable execution ledger; uniqueness makes duplicate delivery harmless."""

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
        existing = await self.session.scalar(
            select(WorkflowExecutionRecord).where(
                WorkflowExecutionRecord.project_id == project_id,
                WorkflowExecutionRecord.update_id == update_id,
                WorkflowExecutionRecord.workflow_version_id == workflow_version_id,
            ).with_for_update()
        )
        if existing is not None:
            return existing, False
        record = WorkflowExecutionRecord(
            project_id=project_id,
            tenant_id=tenant_id,
            update_id=update_id,
            workflow_version_id=workflow_version_id,
            workflow_version=workflow_version,
            trace_id=trace_id,
        )
        self.session.add(record)
        await self.session.flush()
        return record, True
