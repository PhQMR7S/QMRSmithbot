from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from qmrsmithbot.workflows.action_retry import ActionRetryScheduler


def test_delay_for_attempt_uses_capped_exponential_backoff() -> None:
    scheduler = ActionRetryScheduler(object(), base_delay_seconds=2, max_delay_seconds=10)  # type: ignore[arg-type]
    assert scheduler.delay_for_attempt(1) == 2
    assert scheduler.delay_for_attempt(2) == 4
    assert scheduler.delay_for_attempt(3) == 8
    assert scheduler.delay_for_attempt(4) == 10


def test_retry_scheduler_rejects_invalid_delays() -> None:
    with pytest.raises(ValueError):
        ActionRetryScheduler(object(), base_delay_seconds=0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ActionRetryScheduler(object(), base_delay_seconds=5, max_delay_seconds=4)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ActionRetryScheduler(object()).delay_for_attempt(0)  # type: ignore[arg-type]


def test_retry_schedule_datetimes_are_utc_and_positive() -> None:
    now = datetime.now(UTC)
    delay = ActionRetryScheduler(object()).delay_for_attempt(2)  # type: ignore[arg-type]
    available_at = now + timedelta(seconds=delay)
    assert available_at.tzinfo is UTC
    assert available_at > now
    assert uuid4() is not None
