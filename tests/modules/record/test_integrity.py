"""Record acceptance identity rejects malformed cursor and digest evidence."""

from __future__ import annotations

from uuid import uuid4

import pytest

from ctower_kernel.record import DurabilityDecision, DurabilityState


@pytest.mark.parametrize("acceptance_position", (0, -1))
def test_accepted_decision_requires_a_positive_monotonic_position(
    acceptance_position: int,
) -> None:
    with pytest.raises(ValueError, match="acceptance position must be positive"):
        DurabilityDecision(
            command_id=uuid4(),
            state=DurabilityState.ACCEPTED,
            reason="standby_receipt_proven",
            policy_ref="ctower.cutover-rpo0@1",
            command_root="sha256:" + "a" * 64,
            acceptance_position=acceptance_position,
            retry_after_seconds=1,
        )


def test_accepted_decision_requires_one_exact_sha256_command_root() -> None:
    with pytest.raises(ValueError, match="command root must be one SHA-256 digest"):
        DurabilityDecision(
            command_id=uuid4(),
            state=DurabilityState.ACCEPTED,
            reason="standby_receipt_proven",
            policy_ref="ctower.cutover-rpo0@1",
            command_root="sha256:" + "a" * 63,
            acceptance_position=1,
            retry_after_seconds=1,
        )
