"""RED-first unit tests for spawn record types and lifecycle transitions (R2982)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from ctower_kernel.record.spawn_events import (
    SpawnRecordedPayload,
    SpawnState,
    SpawnTransitionedPayload,
    spawn_payload_from_mapping,
    spawn_transition_allowed,
)
from ctower_kernel.runtime.spawn_driver import (
    SpawnDriveContext,
    SpawnDurabilityState,
    SpawnSpool,
    SpawnSpoolRefusalError,
    build_parity_proof,
    derive_initial_running_set,
    history_parity_report,
    latest_status_effective,
    reconcile_source,
    record_before_drive,
    record_parity_proof,
    replay_spool,
)
from ctower_kernel.runtime.spawn_records import (
    SpawnRecordCreate,
    SpawnRecordGet,
    SpawnRecordList,
    SpawnRecordProblem,
    SpawnRecordRow,
    SpawnRecordTransitionCommand,
    SpawnRecordTransitionRow,
)

__all__: tuple[str, ...] = ()

_STATUS_404 = 404
_STATUS_409 = 409
_STATUS_422 = 422
_SPOOL_MODE = 0o600
_PENDING_SPOOL_ENTRIES = 2
_SOURCE_ROWS = 3
_DISTINCT_SOURCE_IDS = 2


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
        """Every authored edge is allowed and no other edge is."""
        allowed = {
            (SpawnState.REQUESTED, SpawnState.ACCEPTED),
            (SpawnState.REQUESTED, SpawnState.FAILED),
            (SpawnState.ACCEPTED, SpawnState.RUNNING),
            (SpawnState.ACCEPTED, SpawnState.FAILED),
            (SpawnState.RUNNING, SpawnState.COMPLETED),
            (SpawnState.RUNNING, SpawnState.FAILED),
            (SpawnState.RUNNING, SpawnState.REAPED),
        }
        for from_state in SpawnState:
            for to_state in SpawnState:
                assert spawn_transition_allowed(from_state, to_state) == (
                    (from_state, to_state) in allowed
                )

    def test_terminal_states(self) -> None:
        """completed, failed, and reaped are terminal."""
        for status in (SpawnState.COMPLETED, SpawnState.FAILED, SpawnState.REAPED):
            assert all(not spawn_transition_allowed(status, target) for target in SpawnState)

    def test_authored_statuses_are_closed(self) -> None:
        assert {state.value for state in SpawnState} == {
            "requested",
            "accepted",
            "running",
            "completed",
            "failed",
            "reaped",
        }


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


_RUNNING_ONE = uuid4()
_TERMINATED = uuid4()
_TERMINAL_LATEST = uuid4()
_REVIVED = uuid4()


def _spawn_command(*, task_file_ref: str = "coordination/task.md") -> SpawnRecordCreate:
    return SpawnRecordCreate(
        client_command_id=uuid4(),
        project_key="ctower",
        seat_key="engineer",
        crew_name="mc-engineer-r3000-spawn",
        task_file_ref=task_file_ref,
        worktree_path="/srv/projects/ctower/.worktrees/r3000-spawn",
        harness="hermes",
        model="deepseek-v4-flash",
        effort=None,
        workspace_id=None,
    )


def _recorded_spawn(command: SpawnRecordCreate) -> SpawnRecordGet:
    now = datetime.now(UTC)
    return SpawnRecordGet(
        record=SpawnRecordRow(
            spawn_id=uuid4(),
            project_key=command.project_key,
            seat_key=command.seat_key,
            crew_name=command.crew_name,
            task_file_ref=command.task_file_ref,
            worktree_path=command.worktree_path,
            harness=command.harness,
            model=command.model,
            effort=command.effort,
            workspace_id=command.workspace_id,
            status="requested",
            principal_id=uuid4(),
            created_at=now,
            updated_at=now,
            transitions=(),
        )
    )


def test_spawn_event_accepts_the_authored_one_character_seat_key() -> None:
    SpawnRecordedPayload(
        spawn_id=uuid4(),
        project_key="ctower",
        seat_key="a",
        crew_name="crew",
        task_file_ref="coordination/task.md",
        worktree_path="/srv/worktrees/crew",
        harness="codex-crew",
        model="gpt-5-codex",
        effort=None,
        workspace_id=None,
    )


def test_spawn_record_mapping_rebuilds_the_authored_payload() -> None:
    payload = SpawnRecordedPayload(
        spawn_id=uuid4(),
        project_key="ctower",
        seat_key="engineer",
        crew_name="mc-engineer-r3000-spawn",
        task_file_ref="coordination/task.md",
        worktree_path="/srv/worktrees/crew",
        harness="codex-crew",
        model="gpt-5-codex",
        effort="high",
        workspace_id=uuid4(),
    )

    assert spawn_payload_from_mapping("spawn.recorded", payload.to_mapping()) == payload


def test_spawn_transition_mapping_rebuilds_the_authored_payload() -> None:
    payload = SpawnTransitionedPayload(
        spawn_id=uuid4(),
        from_state=SpawnState.REQUESTED,
        to_state=SpawnState.ACCEPTED,
        transition_number=1,
        reason="operator accepted dispatch",
    )

    assert spawn_payload_from_mapping("spawn.transitioned", payload.to_mapping()) == payload


@pytest.mark.parametrize(
    ("kind", "payload", "message"),
    [
        ("spawn.unknown", {}, "not a spawn-custody event"),
        ("spawn.recorded", {"spawn_id": str(uuid4())}, "fields do not match"),
        (
            "spawn.transitioned",
            {
                "spawn_id": str(uuid4()),
                "from_state": "requested",
                "to_state": "bogus",
                "transition_number": 1,
                "reason": None,
            },
            "outside the authored event contract",
        ),
    ],
)
def test_spawn_mapping_refuses_unknown_or_malformed_payload(
    kind: str,
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        spawn_payload_from_mapping(kind, payload)


def test_spool_discipline_is_mode_0600_and_ack_only_removal(tmp_path: Path) -> None:
    spool = SpawnSpool(tmp_path / "spawn-spool.jsonl")
    first = spool.append(_spawn_command())
    second = spool.append(_spawn_command())

    assert first.state == "durability_pending"
    assert second.state == "durability_pending"
    assert (tmp_path / "spawn-spool.jsonl").stat().st_mode & 0o777 == _SPOOL_MODE
    assert len(spool.pending()) == _PENDING_SPOOL_ENTRIES
    assert spool.remove_acked(()) == 0
    assert spool.remove_acked([first.entry_id]) == 1
    assert [entry.entry_id for entry in spool.pending()] == [second.entry_id]


def test_spool_does_not_follow_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "redirected.jsonl"
    path = tmp_path / "spawn-spool.jsonl"
    path.symlink_to(target)

    with pytest.raises(OSError):
        SpawnSpool(path).append(_spawn_command())
    assert not target.exists()


def test_spool_replay_removes_only_a_typed_create_ack(tmp_path: Path) -> None:
    spool = SpawnSpool(tmp_path / "spawn-spool.jsonl")
    spool.append(_spawn_command())

    replayed, refused = replay_spool(spool, lambda _command: None)

    assert (replayed, refused) == (0, 1)
    assert len(spool.pending()) == 1


def test_record_before_drive_orders_record_then_host_drive(tmp_path: Path) -> None:
    events: list[str] = []
    command = _spawn_command()

    def record(_command: SpawnRecordCreate) -> SpawnRecordGet:
        events.append("record")
        return _recorded_spawn(command)

    def drive(_context: SpawnDriveContext) -> None:
        events.append("drive")

    result = record_before_drive(
        command,
        record=record,
        drive=drive,
        spool=SpawnSpool(tmp_path / "spawn-spool.jsonl"),
    )

    assert result.context.durability_state is SpawnDurabilityState.RECORDED
    assert events == ["record", "drive"]


def test_unreachable_record_is_spooled_and_then_driven(tmp_path: Path) -> None:
    events: list[str] = []
    command = _spawn_command()
    spool = SpawnSpool(tmp_path / "spawn-spool.jsonl")

    def record(_command: SpawnRecordCreate) -> SpawnRecordProblem:
        events.append("record")
        raise ConnectionError("ctower unavailable")

    def drive(context: SpawnDriveContext) -> None:
        assert context.durability_state is SpawnDurabilityState.DURABILITY_PENDING
        assert context.spool_entry_id is not None
        events.append("drive")

    result = record_before_drive(command, record=record, drive=drive, spool=spool)

    assert result.context.durability_state is SpawnDurabilityState.DURABILITY_PENDING
    assert result.context.record is None
    assert len(spool.pending()) == 1
    assert events == ["record", "drive"]


def test_permanent_record_refusal_does_not_drive_host_session(tmp_path: Path) -> None:
    events: list[str] = []
    command = _spawn_command()
    refusal = SpawnRecordProblem(
        code="project-scope-denied",
        detail="project scope denied",
        status=403,
        title="Project scope denied",
        command_id=command.client_command_id,
    )

    def record(_command: SpawnRecordCreate) -> SpawnRecordProblem:
        events.append("record")
        return refusal

    def drive(_context: SpawnDriveContext) -> None:
        events.append("drive")

    result = record_before_drive(
        command,
        record=record,
        drive=drive,
        spool=SpawnSpool(tmp_path / "spawn-spool.jsonl"),
    )

    assert result.context.durability_state is SpawnDurabilityState.REFUSED
    assert result.problem is refusal
    assert events == ["record"]
    assert not (tmp_path / "spawn-spool.jsonl").exists()


def test_spool_refuses_prohibited_data_before_writing(tmp_path: Path) -> None:
    credential_label = "api" + "_key"
    path = tmp_path / "spawn-spool.jsonl"

    with pytest.raises(SpawnSpoolRefusalError):
        SpawnSpool(path).append(_spawn_command(task_file_ref=f"{credential_label} = {'a' * 8}"))
    assert not path.exists()


def test_import_derivation_is_latest_status_effective() -> None:
    rows = [
        {"uuid": str(_RUNNING_ONE), "status": "running"},
        {"uuid": str(_TERMINATED), "status": "completed"},
        {"uuid": str(_TERMINAL_LATEST), "status": "running"},
        {"uuid": str(_TERMINAL_LATEST), "status": "failed"},
        {"uuid": str(_REVIVED), "status": "failed"},
        {"uuid": str(_REVIVED), "status": "running"},
    ]

    effective = latest_status_effective(rows)
    assert effective[_TERMINAL_LATEST] == "failed"
    assert effective[_REVIVED] == "running"
    assert {row.uuid for row in derive_initial_running_set(rows)} == {_RUNNING_ONE, _REVIVED}


def test_history_parity_report_names_missing_and_duplicate_source_ids() -> None:
    rows = [
        {"uuid": str(_RUNNING_ONE), "status": "running"},
        {"uuid": str(_TERMINATED), "status": "completed"},
        {"uuid": str(_RUNNING_ONE), "status": "working"},
    ]

    report = history_parity_report(rows, imported_source_ids=(_RUNNING_ONE,))

    assert report.source_row_count == _SOURCE_ROWS
    assert report.distinct_source_count == _DISTINCT_SOURCE_IDS
    assert report.duplicate_source_row_count == 1
    assert report.imported_record_count == 1
    assert report.missing_source_ids == (_TERMINATED,)
    assert report.parity_ok is False
    assert report.initial_running_ids == (_RUNNING_ONE,)


def test_reconcile_reads_twin_until_recorded_parity_proof() -> None:
    assert reconcile_source() == "external-twin"
    twin = [{"uuid": str(_RUNNING_ONE), "status": "running"}]
    candidate = build_parity_proof(twin, twin, window="2026-08-15T00:00Z/2026-08-15T01:00Z")
    assert reconcile_source(parity_proof=candidate) == "external-twin"
    recorded = record_parity_proof(candidate)
    assert recorded.parity_ok is True
    assert reconcile_source(parity_proof=recorded) == "ctower-spawn-reads"
