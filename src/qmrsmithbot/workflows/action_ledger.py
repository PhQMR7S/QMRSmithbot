from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from qmrsmithbot.db.workflow_runtime_models import ActionLedgerRecord
from qmrsmithbot.workflows.actions import ActionResult


@dataclass(frozen=True, slots=True)
class ActionLedgerEntry:
    id: UUID
    execution_id: UUID
    tenant_id: UUID
    project_id: UUID
    node_id: str
    action_type: str
    idempotency_key: str
    sequence: int
    status: str
    attempt: int
    retryable: bool
    result_metadata: dict
    error: str | None
    completed_at: datetime | None


class ActionLedgerService:
    """Durable action state, idempotency, retry state, and execution ordering."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        *,
        execution_id: UUID,
        tenant_id: UUID,
        project_id: UUID,
        node_id: str,
        action_type: str,
        idempotency_key: str,
        sequence: int,
    ) -> ActionLedgerEntry:
        if sequence < 1:
            raise ValueError("action sequence must be positive")
        statement = (
            insert(ActionLedgerRecord)
            .values(
                execution_id=execution_id,
                tenant_id=tenant_id,
                project_id=project_id,
                node_id=node_id,
                action_type=action_type,
                idempotency_key=idempotency_key,
                sequence=sequence,
                status="pending",
                attempt=1,
                retryable=False,
                result_metadata={},
            )
            .on_conflict_do_nothing(constraint="uq_action_ledger_execution_node_key")
        )
        await self.session.execute(statement)
        row = await self.session.scalar(
            select(ActionLedgerRecord).where(
                ActionLedgerRecord.execution_id == execution_id,
                ActionLedgerRecord.node_id == node_id,
                ActionLedgerRecord.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            raise RuntimeError("action ledger entry could not be created or loaded")
        return self._to_entry(row)

    async def claim(self, *, ledger_id: UUID) -> ActionLedgerEntry | None:
        now = datetime.now(UTC)
        predecessor = aliased(ActionLedgerRecord)
        predecessor_completed = ~select(predecessor.id).where(
            predecessor.execution_id == ActionLedgerRecord.execution_id,
            predecessor.sequence < ActionLedgerRecord.sequence,
            predecessor.status != "completed",
        ).exists()
        row = await self.session.scalar(
            select(ActionLedgerRecord)
            .where(
                ActionLedgerRecord.id == ledger_id,
                ActionLedgerRecord.status.in_(("pending", "failed")),
                or_(
                    ActionLedgerRecord.status == "pending",
                    and_(
                        ActionLedgerRecord.status == "failed",
                        ActionLedgerRecord.retryable,
                        or_(
                            ActionLedgerRecord.available_at.is_(None),
                            ActionLedgerRecord.available_at <= now,
                        ),
                    ),
                ),
                predecessor_completed,
            )
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.status = "running"
        row.started_at = now
        row.available_at = None
        row.error = None
        await self.session.flush()
        return self._to_entry(row)

    async def complete(self, *, ledger_id: UUID, result: ActionResult) -> ActionLedgerEntry:
        row = await self.session.scalar(
            select(ActionLedgerRecord).where(ActionLedgerRecord.id == ledger_id).with_for_update()
        )
        if row is None:
            raise RuntimeError("action ledger entry not found")
        if row.status == "completed":
            return self._to_entry(row)
        if row.status != "running":
            raise RuntimeError("action ledger entry is not running")
        row.status = "completed"
        row.attempt = result.attempt
        row.retryable = False
        row.result_metadata = dict(result.metadata)
        row.completed_at = datetime.now(UTC)
        row.error = None
        row.available_at = None
        await self.session.flush()
        return self._to_entry(row)

    async def fail(
        self,
        *,
        ledger_id: UUID,
        error: str,
        retryable: bool,
    ) -> ActionLedgerEntry:
        row = await self.session.scalar(
            select(ActionLedgerRecord).where(ActionLedgerRecord.id == ledger_id).with_for_update()
        )
        if row is None:
            raise RuntimeError("action ledger entry not found")
        if row.status != "running":
            raise RuntimeError("action ledger entry is not running")
        row.status = "failed"
        row.error = error[:1000]
        row.retryable = retryable
        row.available_at = None
        if retryable:
            row.attempt += 1
        row.completed_at = None
        await self.session.flush()
        return self._to_entry(row)

    @staticmethod
    def _to_entry(row: ActionLedgerRecord) -> ActionLedgerEntry:
        return ActionLedgerEntry(
            id=row.id,
            execution_id=row.execution_id,
            tenant_id=row.tenant_id,
            project_id=row.project_id,
            node_id=row.node_id,
            action_type=row.action_type,
            idempotency_key=row.idempotency_key,
            sequence=row.sequence,
            status=row.status,
            attempt=row.attempt,
            retryable=row.retryable,
            result_metadata=dict(row.result_metadata),
            error=row.error,
            completed_at=row.completed_at,
        )
