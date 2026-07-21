"""Public Record durability decisions stay small, typed, and fail closed."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from ctower_kernel.record import (
    DurabilityDecision,
    DurabilityHealth,
    DurabilityHealthStatus,
    DurabilityState,
)
from ctower_kernel.record.postgres import PostgresRecord

_INVALID_DECISION_CASES = [
    (
        DurabilityState.ACCEPTED,
        None,
        "sha256:" + "3" * 64,
        1,
        "accepted durability requires an acceptance position",
    ),
    (
        DurabilityState.PENDING,
        18,
        "sha256:" + "4" * 64,
        1,
        "pending durability cannot carry an acceptance position",
    ),
    (
        DurabilityState.PENDING,
        None,
        "not-a-command-root",
        1,
        "command root must be one SHA-256 digest",
    ),
    (
        DurabilityState.PENDING,
        None,
        "sha256:" + "Z" * 64,
        1,
        "command root must be one SHA-256 digest",
    ),
    (
        DurabilityState.ACCEPTED,
        0,
        "sha256:" + "5" * 64,
        1,
        "acceptance position must be positive",
    ),
    (
        DurabilityState.PENDING,
        None,
        "sha256:" + "6" * 64,
        0,
        "durability retry interval must be between 1 and 60 seconds",
    ),
    (
        DurabilityState.PENDING,
        None,
        "sha256:" + "7" * 64,
        61,
        "durability retry interval must be between 1 and 60 seconds",
    ),
]


def test_pending_decision_cannot_carry_an_acceptance_position() -> None:
    decision = DurabilityDecision(
        command_id=uuid4(),
        state=DurabilityState.PENDING,
        reason="policy_pending_only",
        policy_ref="ctower.pending-only@1",
        command_root="sha256:" + "1" * 64,
        acceptance_position=None,
        retry_after_seconds=1,
    )

    assert decision.accepted is False


def test_accepted_decision_requires_the_global_acceptance_cursor() -> None:
    decision = DurabilityDecision(
        command_id=uuid4(),
        state=DurabilityState.ACCEPTED,
        reason="standby_receipt_proven",
        policy_ref="ctower.cutover-rpo0@1",
        command_root="sha256:" + "2" * 64,
        acceptance_position=17,
        retry_after_seconds=1,
    )

    assert decision.accepted is True


def test_health_reports_unknown_without_inventing_a_watermark() -> None:
    health = DurabilityHealth(
        status=DurabilityHealthStatus.STATE_UNKNOWN,
        policy_ref="ctower.pending-only@1",
        target_identity="unconfigured",
        acceptance_position=None,
        observed_at=datetime(2026, 7, 21, tzinfo=UTC),
        reason="pending_only",
    )

    assert health.acceptance_position is None


@pytest.mark.parametrize(
    ("state", "acceptance_position", "command_root", "retry_after_seconds", "message"),
    _INVALID_DECISION_CASES,
)
def test_invalid_durability_decisions_fail_closed(
    state: DurabilityState,
    acceptance_position: int | None,
    command_root: str,
    retry_after_seconds: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        DurabilityDecision(
            command_id=uuid4(),
            state=state,
            reason="policy_pending_only",
            policy_ref="ctower.pending-only@1",
            command_root=command_root,
            acceptance_position=acceptance_position,
            retry_after_seconds=retry_after_seconds,
        )


def test_health_fails_closed_when_the_primary_is_unavailable() -> None:
    record = PostgresRecord("postgresql://postgres@127.0.0.1:1/ctower?connect_timeout=1")

    health = record.durability_health(now=datetime(2026, 7, 21, tzinfo=UTC))

    assert health.status is DurabilityHealthStatus.STATE_UNKNOWN
    assert health.acceptance_position is None
    assert health.reason == "primary_unavailable"
