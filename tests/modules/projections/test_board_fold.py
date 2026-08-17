"""Pure six-lane Board fold through public projection values."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from ctower_kernel.projections import BoardFacts, BoardLane, derive_board_card

__all__: tuple[str, ...] = ()


def test_board_fold_uses_fact_precedence_and_activity_not_stage_labels() -> None:
    facts = _facts()

    assert derive_board_card(facts).lane is BoardLane.BACKLOG
    assert derive_board_card(replace(facts, admitted=True)).lane is BoardLane.READY
    assert (
        derive_board_card(
            replace(facts, admitted=True, workflow_active=True, activity_class="work")
        ).lane
        is BoardLane.IN_PROGRESS
    )
    assert (
        derive_board_card(
            replace(
                facts,
                admitted=True,
                workflow_active=True,
                activity_class="verification",
                stage_key="arbitrary.legal-review",
            )
        ).lane
        is BoardLane.IN_REVIEW
    )
    blocked = derive_board_card(
        replace(
            facts,
            admitted=True,
            workflow_active=True,
            activity_class="verification",
            blocker_reason="Waiting for operator",
            blocker_opened_at=datetime.now(UTC),
        )
    )
    complete = derive_board_card(
        replace(facts, lifecycle_state="closed", blocker_reason="ignored at terminal")
    )

    assert blocked.lane is BoardLane.BLOCKED
    assert blocked.underlying_lane is BoardLane.IN_REVIEW
    assert complete.lane is BoardLane.COMPLETE
    assert complete.underlying_lane is None


def _facts() -> BoardFacts:
    return BoardFacts(
        ticket_id=uuid4(),
        project_key="ctower",
        display_key="CTW-7",
        title="Fold vector",
        priority="P2",
        lifecycle_state="open",
        admitted=False,
        workflow_active=False,
        stage_key="anything",
        activity_class="work",
        custodian_id=uuid4(),
        assignee_id=None,
        blocker_reason=None,
        blocker_opened_at=None,
        risk=None,
        delivery_facts=(),
        version=1,
    )
