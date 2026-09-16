from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from qmrsmithbot.db.workflow_runtime_models import WorkflowExecutionRecord
from qmrsmithbot.workflows.execution_store import WorkflowExecutionStore
from qmrsmithbot.workflows.executor import ExecutionContext, ExecutionIdentity


def make_row(*, status: str = "running") -> MagicMock:
    row = MagicMock()
    row.id = uuid4()
    row.project_id = uuid4()
    row.tenant_id = uuid4()
    row.update_id = 42
    row.workflow_version_id = uuid4()
    row.workflow_version = 7
    row.status = status
    row.attempts = 0
    row.visited_nodes = ["start"]
    row.pending_nodes = ["send"]
    row.context_values = {"name": "QMR"}
    row.checkpoint_version = 2
    row.error = None
    row.trace_id = "trace-1"
    row.started_at = datetime.now(UTC)
    row.completed_at = None
    return row


def make_identity(row: MagicMock) -> ExecutionIdentity:
    return ExecutionIdentity(
        tenant_id=str(row.tenant_id),
        project_id=str(row.project_id),
        update_id=row.update_id,
        workflow_version_id=str(row.workflow_version_id),
        workflow_version=row.workflow_version,
        trace_id=row.trace_id,
    )


def test_workflow_execution_constraints_include_checkpoint_and_cancellation() -> None:
    constraints = {constraint.name for constraint in WorkflowExecutionRecord.__table__.constraints}
    assert "uq_workflow_execution_update_version" in constraints
    assert "ck_workflow_execution_attempts_nonnegative" in constraints
    assert "ck_workflow_execution_checkpoint_nonnegative" in constraints
    assert "ck_workflow_execution_status" in constraints


def test_checkpoint_query_locks_running_execution() -> None:
    session = AsyncMock()
    row = make_row()
    session.scalar = AsyncMock(return_value=row)
    store = WorkflowExecutionStore(session)

    result = asyncio.run(
        store.checkpoint(
            execution_id=row.id,
            visited_nodes=["start", "set"],
            pending_nodes=["send"],
            context_values={"name": "QMR"},
            expected_version=2,
        )
    )

    assert result.checkpoint_version == 3
    assert row.visited_nodes == ["start", "set"]
    assert row.pending_nodes == ["send"]
    statement = session.scalar.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql.upper()
    assert "status" in sql


def test_checkpoint_rejects_stale_version() -> None:
    session = AsyncMock()
    row = make_row()
    session.scalar = AsyncMock(return_value=row)
    store = WorkflowExecutionStore(session)

    with pytest.raises(RuntimeError, match="checkpoint version conflict"):
        asyncio.run(
            store.checkpoint(
                execution_id=row.id,
                visited_nodes=["start"],
                pending_nodes=[],
                context_values={},
                expected_version=1,
            )
        )


def test_apply_to_context_restores_durable_state() -> None:
    session = AsyncMock()
    row = make_row()
    session.scalar = AsyncMock(return_value=row)
    store = WorkflowExecutionStore(session)
    context = ExecutionContext(identity=make_identity(row), values={"stale": True}, visited=["old"])

    snapshot = asyncio.run(store.apply_to_context(execution_id=row.id, context=context))

    assert snapshot.id == row.id
    assert context.values == {"name": "QMR"}
    assert context.visited == ["start"]


def test_apply_to_context_rejects_identity_mismatch() -> None:
    session = AsyncMock()
    row = make_row()
    session.scalar = AsyncMock(return_value=row)
    store = WorkflowExecutionStore(session)
    context = ExecutionContext(
        identity=ExecutionIdentity(
            tenant_id=str(row.tenant_id),
            project_id=str(uuid4()),
            update_id=row.update_id,
            workflow_version_id=str(row.workflow_version_id),
            workflow_version=row.workflow_version,
            trace_id=row.trace_id,
        )
    )

    with pytest.raises(RuntimeError, match="identity does not match"):
        asyncio.run(store.apply_to_context(execution_id=row.id, context=context))


def test_mark_completed_sets_terminal_state() -> None:
    session = AsyncMock()
    row = make_row()
    session.scalar = AsyncMock(return_value=row)
    store = WorkflowExecutionStore(session)

    snapshot = asyncio.run(store.mark_completed(execution_id=row.id))

    assert snapshot.status == "completed"
    assert row.pending_nodes == []
    assert row.completed_at is not None


def test_mark_failed_bounds_error() -> None:
    session = AsyncMock()
    row = make_row()
    session.scalar = AsyncMock(return_value=row)
    store = WorkflowExecutionStore(session)

    snapshot = asyncio.run(store.mark_failed(execution_id=row.id, error="x" * 2000))

    assert snapshot.status == "failed"
    assert len(snapshot.error or "") == 1000
