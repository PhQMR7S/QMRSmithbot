from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.workflows.action_ledger import ActionLedgerEntry, ActionLedgerService
from qmrsmithbot.workflows.action_retry import ActionRetryScheduler
from qmrsmithbot.workflows.actions import ActionEngine, ActionExecutionError, ActionResult
from qmrsmithbot.workflows.executor import ExecutionContext
from qmrsmithbot.workflows.schema import WorkflowNode


class ActionExecutionDeferred(RuntimeError):
    """Raised when durable state prevents an action from running yet."""


@dataclass(frozen=True, slots=True)
class DurableActionResult:
    ledger_id: UUID
    result: ActionResult


class DurableActionExecutor:
    """Bridge ActionEngine to the durable ledger, retries, and leases."""

    def __init__(
        self,
        session: AsyncSession,
        action_engine: ActionEngine,
        *,
        execution_id: UUID,
        lease_seconds: float = 60.0,
        retry_base_delay_seconds: float = 2.0,
        retry_max_delay_seconds: float = 300.0,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.ledger = ActionLedgerService(session, lease_seconds=lease_seconds)
        self.retry_scheduler = ActionRetryScheduler(
            session,
            base_delay_seconds=retry_base_delay_seconds,
            max_delay_seconds=retry_max_delay_seconds,
        )
        self.action_engine = action_engine
        self.execution_id = execution_id

    async def execute(
        self,
        *,
        node: WorkflowNode,
        context: ExecutionContext,
        sequence: int,
    ) -> DurableActionResult:
        tenant_id, project_id = self._identity(context)
        idempotency_key = self._idempotency_key(context, node)
        entry = await self.ledger.get_or_create(
            execution_id=self.execution_id,
            tenant_id=tenant_id,
            project_id=project_id,
            node_id=node.id,
            action_type=node.type,
            idempotency_key=idempotency_key,
            sequence=sequence,
        )

        if entry.status == "running" and self._lease_expired(entry):
            await self.ledger.recover_expired_leases(now=datetime.now(UTC))
            entry = await self.ledger.get_or_create(
                execution_id=self.execution_id,
                tenant_id=tenant_id,
                project_id=project_id,
                node_id=node.id,
                action_type=node.type,
                idempotency_key=idempotency_key,
                sequence=sequence,
            )
        if entry.status == "completed":
            return DurableActionResult(entry.id, self._result_from_entry(entry))

        claimed = await self.ledger.claim(ledger_id=entry.id)
        if claimed is None:
            raise ActionExecutionDeferred(f"action {node.id} is not currently claimable")

        try:
            result = await self.action_engine.execute(
                node=node,
                context=context,
                attempt=claimed.attempt,
            )
        except ActionExecutionError as exc:
            failed = await self.ledger.fail(
                ledger_id=claimed.id,
                error=str(exc),
                retryable=exc.kind.value == "retryable",
            )
            if failed.retryable:
                await self.retry_scheduler.schedule(ledger_id=failed.id)
            raise
        except Exception:
            await self.ledger.fail(
                ledger_id=claimed.id,
                error="unexpected action execution failure",
                retryable=False,
            )
            raise

        metadata = dict(result.metadata)
        metadata.setdefault("external_key", result.external_key)
        durable_result = ActionResult(
            action_type=result.action_type,
            external_key=result.external_key,
            attempt=result.attempt,
            metadata=metadata,
        )
        completed = await self.ledger.complete(
            ledger_id=claimed.id,
            result=durable_result,
        )
        return DurableActionResult(completed.id, durable_result)

    @staticmethod
    def _lease_expired(entry: ActionLedgerEntry) -> bool:
        return entry.lease_expires_at is not None and entry.lease_expires_at <= datetime.now(UTC)

    @staticmethod
    def _identity(context: ExecutionContext) -> tuple[UUID, UUID]:
        if not context.tenant_id or not context.project_id:
            raise ActionExecutionDeferred("action execution is missing durable identity")
        try:
            return UUID(context.tenant_id), UUID(context.project_id)
        except ValueError as exc:
            raise ActionExecutionDeferred("action execution identity is invalid") from exc

    @staticmethod
    def _idempotency_key(context: ExecutionContext, node: WorkflowNode) -> str:
        if context.update_id is None or not context.workflow_version_id:
            raise ActionExecutionDeferred("action execution is missing idempotency identity")
        return f"{context.update_id}:{context.workflow_version_id}:{node.id}"

    @staticmethod
    def _result_from_entry(entry: ActionLedgerEntry) -> ActionResult:
        metadata = dict(entry.result_metadata)
        external_key = str(metadata.pop("external_key", f"ledger:{entry.id}"))
        return ActionResult(
            action_type=entry.action_type,
            external_key=external_key,
            attempt=entry.attempt,
            metadata=metadata,
        )
