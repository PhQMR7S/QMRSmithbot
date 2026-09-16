from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    lease_expires_at: datetime | None


class ActionLedgerService:
    """Durable action state, idempotency, retry state, ordering, leases, and recovery."""

    def __init__(self, session: AsyncSession, *, lease_seconds: float = 60.0) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.session = session
        self.lease_seconds = lease_seconds

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
        lease_expires_at = now + timedelta(seconds=self.lease_seconds)
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
        row.lease_expires_at = lease_expires_at
        row.error = None
        await self.session.flush()
        return self._to_entry(row)

    async def claim_due_batch(
        self,
        *,
        limit: int,
        now: datetime | None = None,
    ) -> list[ActionLedgerEntry]:
        """Claim due retries atomically, preserving per-execution action ordering."""
        if limit < 1:
            raise ValueError("claim limit must be positive")
        current_time = now or datetime.now(UTC)
        lease_expires_at = current_time + timedelta(seconds=self.lease_seconds)
        predecessor = aliased(ActionLedgerRecord)
        predecessor_completed = ~select(predecessor.id).where(
            predecessor.execution_id == ActionLedgerRecord.execution_id,
            predecessor.sequence < ActionLedgerRecord.sequence,
            predecessor.status != "completed",
        ).exists()
        rows = list(
            (
                await self.session.scalars(
                    select(ActionLedgerRecord)
                    .where(
                        ActionLedgerRecord.status == "failed",
                        ActionLedgerRecord.retryable.is_(True),
                        ActionLedgerRecord.available_at.is_not(None),
                        ActionLedgerRecord.available_at <= current_time,
                        predecessor_completed,
                    )
                    .order_by(
                        ActionLedgerRecord.available_at,
                        ActionLedgerRecord.created_at,
                        ActionLedgerRecord.id,
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for row in rows:
            row.status = "running"
            row.started_at = current_time
            row.available_at = None
            row.lease_expires_at = lease_expires_at
            row.error = None
        if rows:
            await self.session.flush()
        return [self._to_entry(row) for row in rows]

    async def renew_lease(self, *, ledger_id: UUID) -> ActionLedgerEntry | None:
        now = datetime.now(UTC)
        row = await self.session.scalar(
            select(ActionLedgerRecord)
            .where(ActionLedgerRecord.id == ledger_id, ActionLedgerRecord.status == "running")
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        await self.session.flush()
        return self._to_entry(row)

    async def recover_expired_lease_entries(
        self,
        *,
        now: datetime | None = None,
    ) -> list[ActionLedgerEntry]:
        """Recover expired running actions and return their durable entries."""
        current_time = now or datetime.now(UTC)
        rows = list(
            (
                await self.session.scalars(
                    select(ActionLedgerRecord)
                    .where(
                        ActionLedgerRecord.status == "running",
                        ActionLedgerRecord.lease_expires_at.is_not(None),
                        ActionLedgerRecord.lease_expires_at <= current_time,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for row in rows:
            row.status = "failed"
            row.retryable = True
            row.available_at = None
            row.lease_expires_at = None
            row.started_at = None
            row.completed_at = None
            row.error = "action execution lease expired"
        if rows:
            await self.session.flush()
        return [self._to_entry(row) for row in rows]

    async def recover_expired_leases(self, *, now: datetime | None = None) -> int:
        """Recover expired leases and return the number of recovered actions."""
        return len(await self.recover_expired_lease_entries(now=now))

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
        row.lease_expires_at = None
        await self.session.flush()
        return self._to_entry(row)

    async def fail(
        self,
        *,
        ledger_id: UUID,
        error: str,
        retryable: bool,
        max_attempts: int | None = None,
    ) -> ActionLedgerEntry:
        if max_attempts is not None and max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        row = await self.session.scalar(
            select(ActionLedgerRecord).where(ActionLedgerRecord.id == ledger_id).with_for_update()
        )
        if row is None:
            raise RuntimeError("action ledger entry not found")
        if row.status != "running":
            raise RuntimeError("action ledger entry is not running")
        will_dead_letter = retryable and max_attempts is not None and row.attempt >= max_attempts
        row.status = "dead_letter" if will_dead_letter else "failed"
        row.error = error[:1000]
        row.retryable = retryable and not will_dead_letter
        row.available_at = None
        row.lease_expires_at = None
        if retryable and not will_dead_letter:
            row.attempt += 1
        row.completed_at = None
        await self.session.flush()
        return self._to_entry(row)

    async def cancel(self, *, ledger_id: UUID, reason: str = "action execution cancelled") -> ActionLedgerEntry | None:
        """Cancel a not-yet-running action; running work must be stopped by its processor."""
        row = await self.session.scalar(
            select(ActionLedgerRecord)
            .where(
                ActionLedgerRecord.id == ledger_id,
                ActionLedgerRecord.status.in_(("pending", "failed")),
            )
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.status = "cancelled"
        row.retryable = False
        row.available_at = None
        row.lease_expires_at = None
        row.error = reason[:1000]
        await self.session.flush()
        return self._to_entry(row)

    async def cancel_execution(self, *, execution_id: UUID, reason: str = "workflow execution cancelled") -> int:
        """Cancel all pending/retryable actions belonging to an execution."""
        rows = list(
            (
                await self.session.scalars(
                    select(ActionLedgerRecord)
                    .where(
                        ActionLedgerRecord.execution_id == execution_id,
                        ActionLedgerRecord.status.in_(("pending", "failed")),
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for row in rows:
            row.status = "cancelled"
            row.retryable = False
            row.available_at = None
            row.lease_expires_at = None
            row.error = reason[:1000]
        if rows:
            await self.session.flush()
        return len(rows)

    async def replay(self, *, ledger_id: UUID) -> ActionLedgerEntry | None:
        """Explicitly requeue a dead-lettered action without resetting its attempt history."""
        row = await self.session.scalar(
            select(ActionLedgerRecord)
            .where(ActionLedgerRecord.id == ledger_id, ActionLedgerRecord.status == "dead_letter")
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.status = "pending"
        row.retryable = False
        row.available_at = None
        row.lease_expires_at = None
        row.error = None
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
            lease_expires_at=row.lease_expires_at,
        )
