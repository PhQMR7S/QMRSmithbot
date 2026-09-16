from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.db.workflow_runtime_models import WorkflowExecutionRecord
from qmrsmithbot.workflows.executor import ExecutionContext, ExecutionIdentity


@dataclass(frozen=True, slots=True)
class WorkflowExecutionSnapshot:
    id: UUID
    project_id: UUID
    tenant_id: UUID
    update_id: int
    workflow_version_id: UUID
    workflow_version: int
    status: str
    attempts: int
    visited_nodes: tuple[str, ...]
    pending_nodes: tuple[str, ...]
    context_values: dict
    checkpoint_version: int
    error: str | None
    trace_id: str
    started_at: datetime
    completed_at: datetime | None


class WorkflowExecutionStore:
    """Durable workflow execution identity, checkpoints, and terminal state."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, *, identity: ExecutionIdentity) -> WorkflowExecutionSnapshot:
        tenant_id = self._uuid(identity.tenant_id, "tenant_id")
        project_id = self._uuid(identity.project_id, "project_id")
        workflow_version_id = self._uuid(identity.workflow_version_id, "workflow_version_id")
        statement = (
            insert(WorkflowExecutionRecord)
            .values(
                project_id=project_id,
                tenant_id=tenant_id,
                update_id=identity.update_id,
                workflow_version_id=workflow_version_id,
                workflow_version=identity.workflow_version,
                status="running",
                attempts=0,
                visited_nodes=[],
                pending_nodes=[],
                context_values={},
                checkpoint_version=0,
                error=None,
                trace_id=identity.trace_id,
            )
            .on_conflict_do_nothing(constraint="uq_workflow_execution_update_version")
        )
        await self.session.execute(statement)
        row = await self.session.scalar(
            select(WorkflowExecutionRecord).where(
                WorkflowExecutionRecord.project_id == project_id,
                WorkflowExecutionRecord.update_id == identity.update_id,
                WorkflowExecutionRecord.workflow_version_id == workflow_version_id,
            )
        )
        if row is None:
            raise RuntimeError("workflow execution could not be created or loaded")
        if row.tenant_id != tenant_id or row.workflow_version != identity.workflow_version:
            raise RuntimeError("workflow execution identity does not match durable record")
        return self._to_snapshot(row)

    async def restore(self, *, execution_id: UUID) -> WorkflowExecutionSnapshot:
        row = await self.session.scalar(
            select(WorkflowExecutionRecord).where(WorkflowExecutionRecord.id == execution_id)
        )
        if row is None:
            raise RuntimeError("workflow execution not found")
        return self._to_snapshot(row)

    async def checkpoint(
        self,
        *,
        execution_id: UUID,
        visited_nodes: list[str],
        pending_nodes: list[str],
        context_values: dict,
        expected_version: int,
    ) -> WorkflowExecutionSnapshot:
        row = await self.session.scalar(
            select(WorkflowExecutionRecord)
            .where(
                WorkflowExecutionRecord.id == execution_id,
                WorkflowExecutionRecord.status == "running",
            )
            .with_for_update()
        )
        if row is None:
            raise RuntimeError("workflow execution is not running")
        if row.checkpoint_version != expected_version:
            raise RuntimeError("workflow execution checkpoint version conflict")
        row.visited_nodes = list(visited_nodes)
        row.pending_nodes = list(pending_nodes)
        row.context_values = dict(context_values)
        row.checkpoint_version += 1
        row.error = None
        await self.session.flush()
        return self._to_snapshot(row)

    async def mark_completed(self, *, execution_id: UUID) -> WorkflowExecutionSnapshot:
        row = await self._locked_running(execution_id)
        row.status = "completed"
        row.pending_nodes = []
        row.error = None
        row.completed_at = datetime.now(UTC)
        await self.session.flush()
        return self._to_snapshot(row)

    async def mark_failed(self, *, execution_id: UUID, error: str) -> WorkflowExecutionSnapshot:
        row = await self._locked_running(execution_id)
        row.status = "failed"
        row.pending_nodes = list(row.pending_nodes)
        row.error = error[:1000]
        row.completed_at = None
        await self.session.flush()
        return self._to_snapshot(row)

    async def cancel(self, *, execution_id: UUID, reason: str = "workflow execution cancelled") -> WorkflowExecutionSnapshot:
        row = await self.session.scalar(
            select(WorkflowExecutionRecord)
            .where(
                WorkflowExecutionRecord.id == execution_id,
                WorkflowExecutionRecord.status == "running",
            )
            .with_for_update(skip_locked=True)
        )
        if row is None:
            raise RuntimeError("workflow execution is not running")
        row.status = "cancelled"
        row.pending_nodes = []
        row.error = reason[:1000]
        row.completed_at = datetime.now(UTC)
        await self.session.flush()
        return self._to_snapshot(row)

    async def apply_to_context(
        self,
        *,
        execution_id: UUID,
        context: ExecutionContext,
    ) -> WorkflowExecutionSnapshot:
        snapshot = await self.restore(execution_id=execution_id)
        if context.identity is None:
            raise RuntimeError("execution context identity is required")
        if (
            str(snapshot.tenant_id) != context.identity.tenant_id
            or str(snapshot.project_id) != context.identity.project_id
            or snapshot.update_id != context.identity.update_id
            or str(snapshot.workflow_version_id) != context.identity.workflow_version_id
            or snapshot.workflow_version != context.identity.workflow_version
        ):
            raise RuntimeError("workflow execution identity does not match context")
        context.values.clear()
        context.values.update(snapshot.context_values)
        context.visited[:] = list(snapshot.visited_nodes)
        return snapshot

    async def _locked_running(self, execution_id: UUID) -> WorkflowExecutionRecord:
        row = await self.session.scalar(
            select(WorkflowExecutionRecord)
            .where(
                WorkflowExecutionRecord.id == execution_id,
                WorkflowExecutionRecord.status == "running",
            )
            .with_for_update()
        )
        if row is None:
            raise RuntimeError("workflow execution is not running")
        return row

    @staticmethod
    def _uuid(value: str, field: str) -> UUID:
        try:
            return UUID(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be a valid UUID") from exc

    @staticmethod
    def _to_snapshot(row: WorkflowExecutionRecord) -> WorkflowExecutionSnapshot:
        return WorkflowExecutionSnapshot(
            id=row.id,
            project_id=row.project_id,
            tenant_id=row.tenant_id,
            update_id=row.update_id,
            workflow_version_id=row.workflow_version_id,
            workflow_version=row.workflow_version,
            status=row.status,
            attempts=row.attempts,
            visited_nodes=tuple(row.visited_nodes),
            pending_nodes=tuple(row.pending_nodes),
            context_values=dict(row.context_values),
            checkpoint_version=row.checkpoint_version,
            error=row.error,
            trace_id=row.trace_id,
            started_at=row.started_at,
            completed_at=row.completed_at,
        )
