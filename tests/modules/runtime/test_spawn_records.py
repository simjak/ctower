"""RED-first unit tests for spawn record types and lifecycle transitions (R2982)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest

from ctower_kernel.runtime import (
    SpawnRecordCreate,
    SpawnRecordGet,
    SpawnRecordList,
    SpawnRecordProblem,
    SpawnRecordRow,
    SpawnRecordTransitionCommand,
    SpawnRecordTransitionRow,
)
from ctower_kernel.runtime._spawn_records import VALID_STATUSES, VALID_TRANSITIONS

__all__: tuple[str, ...] = ()

_STATUS_404 = 404
_STATUS_409 = 409
_STATUS_422 = 422


class TestSpawnRecordTypes:
    """Spawn record data types serialize and validate correctly."""

    def test_create_request_payload(self) -> None:
        """SpawnRecordCreate produces the expected API payload."""
        command = SpawnRecordCreate(
            client_command_id=uuid4(),
            project_key="ctower",
            seat_key="engineer",
            crew_name="mc-engineer-r3000-spawn",
            task_file_ref="/path/to/task.md",
            worktree_path="/srv/projects/ctower/.worktrees/r3000-spawn",
            harness="hermes",
            model="deepseek-v4-flash",
            effort="max",
            workspace_id=uuid4(),
        )
        payload = command.request_payload()
        assert payload["project_key"] == "ctower"
        assert payload["seat_key"] == "engineer"
        assert payload["crew_name"] == "mc-engineer-r3000-spawn"
        assert payload["harness"] == "hermes"
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["effort"] == "max"
        assert "workspace_id" in payload

    def test_create_request_payload_no_optionals(self) -> None:
        """Optional fields are omitted from payload when None."""
        command = SpawnRecordCreate(
            client_command_id=uuid4(),
            project_key="ctower",
            seat_key="engineer",
            crew_name="mc-engineer-r3000-spawn",
            task_file_ref="/path/to/task.md",
            worktree_path="/path/to/worktree",
            harness="hermes",
            model="deepseek-v4-flash",
            effort=None,
            workspace_id=None,
        )
        payload = command.request_payload()
        assert "effort" not in payload
        assert "workspace_id" not in payload

    def test_transition_request_payload(self) -> None:
        """SpawnRecordTransitionCommand produces correct API payload."""
        command = SpawnRecordTransitionCommand(
            client_command_id=uuid4(),
            spawn_id=uuid4(),
            to_status="running",
            reason="dispatch confirmed",
        )
        payload = command.request_payload()
        assert payload["to_status"] == "running"
        assert payload["reason"] == "dispatch confirmed"

    def test_transition_request_payload_no_reason(self) -> None:
        """Reason is omitted from payload when None."""
        command = SpawnRecordTransitionCommand(
            client_command_id=uuid4(),
            spawn_id=uuid4(),
            to_status="completed",
            reason=None,
        )
        payload = command.request_payload()
        assert "reason" not in payload

    def test_row_response_payload(self) -> None:
        """SpawnRecordRow serializes correctly."""
        spawn_id = uuid4()
        principal_id = uuid4()
        now = datetime.now(UTC)
        row = SpawnRecordRow(
            spawn_id=spawn_id,
            project_key="ctower",
            seat_key="engineer",
            crew_name="mc-engineer-r3000-spawn",
            task_file_ref="/task.md",
            worktree_path="/worktree",
            harness="hermes",
            model="deepseek-v4-flash",
            effort="max",
            workspace_id=None,
            status="running",
            principal_id=principal_id,
            created_at=now,
            updated_at=now,
            transitions=(),
        )
        payload = row.response_payload()
        assert payload["spawn_id"] == str(spawn_id)
        assert payload["project_key"] == "ctower"
        assert payload["status"] == "running"
        assert payload["transitions"] == []
        assert "workspace_id" not in payload

    def test_row_with_workspace_id(self) -> None:
        """Workspace_id appears in payload when set."""
        spawn_id = uuid4()
        workspace_id = uuid4()
        now = datetime.now(UTC)
        row = SpawnRecordRow(
            spawn_id=spawn_id,
            project_key="ctower",
            seat_key="engineer",
            crew_name="mc-engineer-r3000-spawn",
            task_file_ref="/task.md",
            worktree_path="/worktree",
            harness="hermes",
            model="deepseek-v4-flash",
            effort=None,
            workspace_id=workspace_id,
            status="requested",
            principal_id=uuid4(),
            created_at=now,
            updated_at=now,
            transitions=(),
        )
        payload = row.response_payload()
        assert payload["workspace_id"] == str(workspace_id)

    def test_transition_row_payload(self) -> None:
        """SpawnRecordTransitionRow serializes correctly."""
        now = datetime.now(UTC)
        t = SpawnRecordTransitionRow(
            transition_id=uuid4(),
            spawn_id=uuid4(),
            from_status="requested",
            to_status="accepted",
            reason="operator confirmed",
            principal_id=uuid4(),
            transitioned_at=now,
        )
        payload = t.response_payload()
        assert payload["from_status"] == "requested"
        assert payload["to_status"] == "accepted"
        assert payload["reason"] == "operator confirmed"

    def test_transition_row_payload_no_reason(self) -> None:
        """Reason omitted from payload when None."""
        now = datetime.now(UTC)
        t = SpawnRecordTransitionRow(
            transition_id=uuid4(),
            spawn_id=uuid4(),
            from_status="running",
            to_status="completed",
            reason=None,
            principal_id=uuid4(),
            transitioned_at=now,
        )
        payload = t.response_payload()
        assert "reason" not in payload

    def test_list_response_payload(self) -> None:
        """SpawnRecordList wraps multiple rows."""
        now = datetime.now(UTC)
        r1 = SpawnRecordRow(
            spawn_id=uuid4(),
            project_key="ctower",
            seat_key="engineer",
            crew_name="mc-engineer-r3000-spawn",
            task_file_ref="/t.md",
            worktree_path="/w",
            harness="hermes",
            model="deepseek",
            effort=None,
            workspace_id=None,
            status="running",
            principal_id=uuid4(),
            created_at=now,
            updated_at=now,
            transitions=(),
        )
        r2 = SpawnRecordRow(
            spawn_id=uuid4(),
            project_key="ctower",
            seat_key="qa",
            crew_name="mc-qa-3000",
            task_file_ref="/t2.md",
            worktree_path="/w2",
            harness="claude",
            model="opus",
            effort=None,
            workspace_id=None,
            status="completed",
            principal_id=uuid4(),
            created_at=now,
            updated_at=now,
            transitions=(),
        )
        lst = SpawnRecordList(records=(r1, r2))
        payload = lst.response_payload()
        records = cast("list[dict[str, object]]", payload["records"])
        assert len(records) == 2  # noqa: PLR2004
        assert records[0]["status"] == "running"
        assert records[1]["status"] == "completed"

    def test_get_response_payload(self) -> None:
        """SpawnRecordGet wraps a single row."""
        now = datetime.now(UTC)
        row = SpawnRecordRow(
            spawn_id=uuid4(),
            project_key="ctower",
            seat_key="engineer",
            crew_name="mc-engineer-r3000-spawn",
            task_file_ref="/t.md",
            worktree_path="/w",
            harness="hermes",
            model="deepseek",
            effort="max",
            workspace_id=None,
            status="requested",
            principal_id=uuid4(),
            created_at=now,
            updated_at=now,
            transitions=(),
        )
        get_obj = SpawnRecordGet(record=row)
        payload = get_obj.response_payload()
        assert isinstance(payload, dict)
        assert payload["spawn_id"] == str(row.spawn_id)
        assert payload["status"] == "requested"

    def test_problem_response_payload(self) -> None:
        """SpawnRecordProblem serializes correctly."""
        problem = SpawnRecordProblem(
            code="invalid-status",
            detail="'bogus' is not a valid spawn status.",
            status=_STATUS_422,
            title="Invalid status",
            command_id=uuid4(),
        )
        payload = problem.response_payload()
        assert payload["code"] == "invalid-status"
        assert payload["status"] == _STATUS_422
        assert "command_id" in payload


class TestSpawnRecordLifecycle:
    """Valid and invalid lifecycle transitions."""

    def test_valid_transitions(self) -> None:
        """Every valid_from -> valid_to pair is allowed."""
        assert "requested" in VALID_TRANSITIONS
        assert "accepted" in VALID_TRANSITIONS["requested"]
        assert "failed" in VALID_TRANSITIONS["requested"]
        assert "running" in VALID_TRANSITIONS["accepted"]
        assert "failed" in VALID_TRANSITIONS["accepted"]
        assert "completed" in VALID_TRANSITIONS["running"]
        assert "failed" in VALID_TRANSITIONS["running"]
        assert "reaped" in VALID_TRANSITIONS["running"]

    def test_terminal_states(self) -> None:
        """completed, failed, and reaped are terminal (no outgoing transitions)."""
        for status in ("completed", "failed", "reaped"):
            assert len(VALID_TRANSITIONS[status]) == 0, f"{status} should be terminal"

    def test_invalid_transition_not_in_mapping(self) -> None:
        """running -> requested is not a valid transition."""
        assert "requested" not in VALID_TRANSITIONS["running"]

    def test_invalid_status_not_in_mapping(self) -> None:
        """Unknown status raises KeyError in VALID_TRANSITIONS lookup."""
        with pytest.raises(KeyError):
            _ = VALID_TRANSITIONS["bogus"]

    def test_command_status_validation(self) -> None:
        """TransitionCommand validates to_status against VALID_STATUSES."""
        for valid in ("requested", "accepted", "running", "completed", "failed", "reaped"):
            assert valid in VALID_STATUSES
        assert "bogus" not in VALID_STATUSES


class TestSpawnRecordProblem:
    """SpawnRecordProblem error code contracts."""

    def test_tenant_not_found(self) -> None:
        problem = SpawnRecordProblem(
            code="tenant-not-found",
            detail="Tenant does not exist.",
            status=_STATUS_404,
            title="Tenant not found",
            command_id=uuid4(),
        )
        assert problem.status == _STATUS_404

    def test_spawn_not_found(self) -> None:
        problem = SpawnRecordProblem(
            code="spawn-not-found",
            detail="Spawn record not found.",
            status=_STATUS_404,
            title="Spawn record not found",
        )
        assert problem.status == _STATUS_404

    def test_invalid_transition(self) -> None:
        problem = SpawnRecordProblem(
            code="invalid-transition",
            detail="Cannot transition from running to requested.",
            status=_STATUS_422,
            title="Invalid lifecycle transition",
            command_id=uuid4(),
        )
        assert problem.status == _STATUS_422

    def test_transition_race(self) -> None:
        problem = SpawnRecordProblem(
            code="transition-race",
            detail="Spawn record no longer matches expected state.",
            status=_STATUS_409,
            title="Transition conflict",
            command_id=uuid4(),
        )
        assert problem.status == _STATUS_409

    def test_problem_no_command_id(self) -> None:
        """Some problems don't carry a command_id."""
        problem = SpawnRecordProblem(
            code="spawn-not-found",
            detail="Spawn record not found.",
            status=_STATUS_404,
            title="Spawn record not found",
        )
        assert problem.command_id is None
        payload = problem.response_payload()
        assert "command_id" not in payload
