"""Executable CP2 task-management contract checks."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).parents[3]
CONTRACTS = ROOT / "contracts/domain/task-management"
MAXIMUM_BOOST_LEVELS = 2
__all__: tuple[str, ...] = ()


def _schema(name: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((CONTRACTS / name).read_text(encoding="utf-8")))


def test_task_commands_are_strict_typed_intents_without_writable_status() -> None:
    schema = _schema("task-command.schema.json")
    validator = Draft202012Validator(schema)
    command = {
        "kind": "change_priority",
        "client_command_id": "018f0d5e-7b9a-7c01-8000-000000000100",
        "expected_version": 3,
        "priority": "P1",
        "reason": "Customer impact increased",
    }

    validator.validate(command)
    with pytest.raises(ValidationError):
        validator.validate({**command, "status": "done"})
    with pytest.raises(ValidationError):
        validator.validate({**command, "kind": "set_status"})
    assignment_kinds = cast(dict[str, object], schema["$defs"])["assignmentKind"]
    assert cast(dict[str, object], assignment_kinds)["enum"] == [
        "ticket_custodian",
        "current_assignee",
        "stage_owner",
        "reviewer_assignment",
        "runner_lease_owner",
    ]


def test_board_contract_has_exact_derived_lanes_and_loud_health() -> None:
    schema = _schema("board-view.schema.json")
    lane = cast(dict[str, object], cast(dict[str, object], schema["$defs"])["lane"])
    health = cast(dict[str, object], cast(dict[str, object], schema["$defs"])["health"])

    assert lane["enum"] == [
        "backlog",
        "ready",
        "in_progress",
        "in_review",
        "blocked",
        "complete",
    ]
    assert health["enum"] == ["CURRENT", "STATE_UNKNOWN"]


@pytest.mark.parametrize(
    ("changes", "expected", "underlying"),
    (
        ({}, "backlog", None),
        ({"admitted": True}, "ready", None),
        (
            {"admitted": True, "workflow_active": True, "activity_class": "work"},
            "in_progress",
            None,
        ),
        (
            {
                "admitted": True,
                "workflow_active": True,
                "activity_class": "verification",
                "stage_key": "arbitrary.legal-review",
            },
            "in_review",
            None,
        ),
        (
            {
                "admitted": True,
                "workflow_active": True,
                "activity_class": "work",
                "blocker_reason": "Waiting",
            },
            "blocked",
            "in_progress",
        ),
        ({"lifecycle_state": "closed"}, "complete", None),
    ),
)
def test_board_fold_contract_is_exhaustive_and_ignores_delivery_wording(
    changes: dict[str, Any], expected: str, underlying: str | None
) -> None:
    facts: dict[str, Any] = {
        "activity_class": None,
        "admitted": False,
        "blocker_reason": None,
        "delivery_facts": ("Production_Verified",),
        "lifecycle_state": "open",
        "stage_key": None,
        "workflow_active": False,
    }
    facts.update(changes)
    lane, resume = _contract_fold(facts)

    assert lane == expected
    assert resume == underlying


def test_scheduling_pack_validates_and_has_bounded_aging_tie_break() -> None:
    schema = _schema("scheduling-policy.schema.json")
    policy = json.loads(
        (ROOT / "packs/policies/scheduling/i1-priority-aging-v1.yaml").read_text(encoding="utf-8")
    )

    Draft202012Validator(schema).validate(policy)
    assert policy["hard_eligibility"]
    assert policy["aging"]["maximum_boost_levels"] == MAXIMUM_BOOST_LEVELS
    assert policy["preemption"]["allowed_only_if"] == "checkpoint_verified"
    assert policy["tie_break"] == ["eligible_since", "ticket_id"]


def test_scheduling_vectors_bound_starvation_and_preserve_restart_age() -> None:
    now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    aged_p2 = (UUID(int=3), "P2", now - timedelta(days=2), (), True)
    p0_flood = tuple(
        (UUID(int=value), "P0", now - timedelta(minutes=value), (), False) for value in (10, 11, 12)
    )
    ineligible = (UUID(int=1), "P2", now - timedelta(days=30), ("trust",), True)
    candidates = (ineligible, *p0_flood, aged_p2)

    first = _contract_order(candidates, now)
    restarted = _contract_order(candidates, now)
    assert first == restarted
    assert first[0] == aged_p2[0]
    assert ineligible[0] not in first


def _contract_fold(facts: dict[str, Any]) -> tuple[str, str | None]:
    if not facts["admitted"]:
        lane = "backlog"
    elif not facts["workflow_active"]:
        lane = "ready"
    elif facts["activity_class"] == "verification":
        lane = "in_review"
    else:
        lane = "in_progress"
    if facts["lifecycle_state"] in {"resolved", "closed"}:
        return "complete", None
    if facts["blocker_reason"] is not None:
        return "blocked", lane
    return lane, None


def _contract_order(
    candidates: tuple[tuple[UUID, str, datetime, tuple[str, ...], bool], ...],
    now: datetime,
) -> tuple[UUID, ...]:
    ranks = {"P0": 0, "P1": 1, "P2": 2}

    def key(item: tuple[UUID, str, datetime, tuple[str, ...], bool]) -> tuple[object, ...]:
        age = max(0, int((now - item[2]).total_seconds()))
        boost = min(MAXIMUM_BOOST_LEVELS, age // 86_400)
        return max(0, ranks[item[1]] - boost), item[2], item[0].int

    return tuple(item[0] for item in sorted((item for item in candidates if not item[3]), key=key))
