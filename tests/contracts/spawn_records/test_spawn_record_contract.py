"""Authored spawn-custody contract boundaries (CT-I1-034, AC-SPWN-01..04).

Checks the authored HTTP surface, the append-only migration, the event catalog,
and the AC-SPWN-02..04 driver disciplines against their authored sources — the
same boundary-test style as the Phase-1 Request candidate.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from ctower_api._spawn_record_routes import (
    SpawnRecordCreateRequest,
    SpawnRecordTransitionRequest,
    _list_payload,
)
from ctower_client.models import SpawnRecordResult
from ctower_kernel.record.events import EventKind, event_catalog
from ctower_kernel.record.spawn_events import (
    SpawnRecordedPayload,
    SpawnState,
    spawn_transition_allowed,
)
from ctower_kernel.runtime import (
    SpawnRecordList,
    SpawnRecordRow,
    SpawnRecordTransitionRow,
    SpawnSpool,
    derive_initial_running_set,
    latest_status_effective,
    reconcile_source,
    replay_spool,
)
from ctower_kernel.runtime._spawn_record_types import SpawnRecordCreate

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()

_SPAWN_OPERATIONS = {
    "createSpawnRecord",
    "listSpawnRecords",
    "getSpawnRecord",
    "appendSpawnTransition",
}
_IMMUTABLE_TABLES = 2
_SPOOL_MODE = 0o600
_NEVER_TERMINATED = 2

_RUNNING_ONE = UUID("11111111-1111-1111-1111-111111111111")
_TERMINATED = UUID("22222222-2222-2222-2222-222222222222")
_TERMINAL_LATEST = UUID("33333333-3333-3333-3333-333333333333")
_REVIVED = UUID("44444444-4444-4444-4444-444444444444")


def test_spawn_http_surface_is_strict_and_append_only() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    operations = {
        cast(str, operation["operationId"]): operation
        for path in cast(dict[str, dict[str, object]], document["paths"]).values()
        for method, operation in path.items()
        if method in {"get", "post"} and isinstance(operation, dict)
    }

    spawn = {name for name in operations if "spawn" in name.casefold()}
    assert spawn == _SPAWN_OPERATIONS

    create = operations["createSpawnRecord"]
    assert create["x-ctower-mutation"] is True
    assert create["x-ctower-spool"] == "allowed"
    assert create["x-ctower-cli"] == "spawn record"

    transition = operations["appendSpawnTransition"]
    assert transition["x-ctower-mutation"] is True
    assert transition["x-ctower-spool"] == "allowed"

    listing = operations["listSpawnRecords"]
    assert listing["x-ctower-mutation"] is False
    assert listing["x-ctower-spool"] == "forbidden"

    # No PATCH/PUT anywhere in the spawn surface: lifecycle moves are POST facts.
    for path in document["paths"]:
        if "spawn" in path:
            assert set(document["paths"][path]) <= {"get", "post", "parameters"}


def test_spawn_storage_is_append_only_with_derived_state() -> None:
    migration = (ROOT / "packages/ctower-kernel/migrations/0068_spawn_records.sql").read_text(
        encoding="utf-8"
    )

    # No mutable status column: state derives from the latest transition fact.
    assert "\n    status text" not in migration
    # UPDATE appears only inside the immutability triggers that refuse it.
    assert migration.upper().count("UPDATE") == _IMMUTABLE_TABLES
    assert migration.upper().count("BEFORE UPDATE OR DELETE") == _IMMUTABLE_TABLES

    assert "CREATE TABLE spawn_records" in migration
    assert "CREATE TABLE spawn_record_transitions" in migration
    assert "UNIQUE (spawn_id, tenant_id, transition_number)" in migration
    # Immutability triggers on both tables.
    assert migration.count("refuse_immutable_control_fact_mutation") == _IMMUTABLE_TABLES
    # Event stream kinds + subject kinds extended exactly once.
    assert migration.count("'spawn.recorded'") == 1
    assert migration.count("'spawn.transitioned'") == 1
    assert migration.count("'spawn_record'") == _IMMUTABLE_TABLES  # event_links + durability heads
    # Runtime role gets append+read only; projection read only.
    assert (
        "GRANT INSERT, SELECT ON spawn_records, spawn_record_transitions TO ctower_svc" in migration
    )
    assert (
        "GRANT SELECT ON spawn_records, spawn_record_transitions TO ctower_projection" in migration
    )


def test_spawn_events_are_in_the_closed_catalog() -> None:
    catalog = {entry.kind for entry in event_catalog()}
    assert EventKind.SPAWN_RECORDED in catalog
    assert EventKind.SPAWN_TRANSITIONED in catalog


def test_spawn_transition_lifecycle_is_authored_linear() -> None:
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
            ), f"{from_state} -> {to_state}"


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


def test_generated_client_covers_spawn_operations() -> None:
    operations = (ROOT / "generated/python/ctower_client/operations.py").read_text(encoding="utf-8")
    for name in _SPAWN_OPERATIONS:
        assert name in operations, f"generated client lost {name}"


def test_spawn_list_response_contains_every_required_spawn_record_field() -> None:
    """The list response must satisfy the authored SpawnRecord schema, not a reduced view."""
    principal_id = uuid4()
    now = datetime.now(UTC)
    record = SpawnRecordRow(
        spawn_id=uuid4(),
        project_key="ctower",
        seat_key="engineer",
        crew_name="mc-engineer-contract",
        task_file_ref="coordination/contract.md",
        worktree_path="/srv/worktrees/contract",
        harness="codex-crew",
        model="gpt-5-codex",
        effort=None,
        workspace_id=None,
        status="requested",
        principal_id=principal_id,
        created_at=now,
        updated_at=now,
        transitions=(),
    )

    payload = _list_payload(SpawnRecordList(records=(record,)))
    listed = cast("list[dict[str, object]]", payload["records"])[0]

    assert listed["principal_id"] == str(principal_id)
    assert listed["transitions"] == []


def test_generated_response_accepts_an_appended_transition_fact() -> None:
    principal_id = uuid4()
    spawn_id = uuid4()
    now = datetime.now(UTC)
    record = SpawnRecordRow(
        spawn_id=spawn_id,
        project_key="ctower",
        seat_key="engineer",
        crew_name="mc-engineer-contract",
        task_file_ref="coordination/contract.md",
        worktree_path="/srv/worktrees/contract",
        harness="codex-crew",
        model="gpt-5-codex",
        effort=None,
        workspace_id=None,
        status="accepted",
        principal_id=principal_id,
        created_at=now,
        updated_at=now,
        transitions=(
            SpawnRecordTransitionRow(
                transition_id=uuid4(),
                spawn_id=spawn_id,
                from_status="requested",
                to_status="accepted",
                reason="operator confirmed",
                principal_id=principal_id,
                transitioned_at=now,
            ),
        ),
    )

    assert (
        SpawnRecordResult.model_validate_json(json.dumps(record.response_payload())).status
        == "accepted"
    )


def test_transition_http_model_excludes_initial_requested_state() -> None:
    """POST transition facts may append only authored successor states."""
    with pytest.raises(ValidationError):
        SpawnRecordTransitionRequest.model_validate({"to_status": "requested"})


def test_http_models_reject_empty_optional_text_facts() -> None:
    """Optional text is omitted or non-empty, matching the append-only DDL."""
    with pytest.raises(ValidationError):
        SpawnRecordCreateRequest.model_validate(
            {
                "project_key": "ctower",
                "seat_key": "engineer",
                "crew_name": "mc-engineer-contract",
                "task_file_ref": "coordination/contract.md",
                "worktree_path": "/srv/worktrees/contract",
                "harness": "codex-crew",
                "model": "gpt-5-codex",
                "effort": "",
            }
        )
    with pytest.raises(ValidationError):
        SpawnRecordTransitionRequest.model_validate({"to_status": "running", "reason": ""})


def test_spool_discipline_is_mode_0600_and_ack_only_removal(tmp_path: Path) -> None:
    """AC-SPWN-02 boundary: pending state surfaced; removal only after ACK."""
    command = SpawnRecordCreate(
        client_command_id=uuid4(),
        project_key="ctower",
        seat_key="engineer",
        crew_name="mc-engineer-contract",
        task_file_ref="coordination/contract.md",
        worktree_path="/srv/worktrees/contract",
        harness="codex-crew",
        model="gpt-5-codex",
        effort=None,
        workspace_id=None,
    )
    spool = SpawnSpool(tmp_path / "spawn-spool.jsonl")
    first = spool.append(command)
    second = spool.append(command)

    assert first.state == "durability_pending"
    assert second.state == "durability_pending"
    assert (tmp_path / "spawn-spool.jsonl").stat().st_mode & 0o777 == _SPOOL_MODE
    assert len(spool.pending()) == _NEVER_TERMINATED

    # Unacknowledged removal attempts remove nothing.
    assert spool.remove_acked(()) == 0
    assert len(spool.pending()) == _NEVER_TERMINATED
    assert spool.remove_acked([first.entry_id]) == 1
    remaining = spool.pending()
    assert [entry.entry_id for entry in remaining] == [second.entry_id]


def test_spool_does_not_follow_a_symlink(tmp_path: Path) -> None:
    """The mode-0600 spool path cannot redirect spawn facts elsewhere."""
    command = SpawnRecordCreate(
        client_command_id=uuid4(),
        project_key="ctower",
        seat_key="engineer",
        crew_name="mc-engineer-contract",
        task_file_ref="coordination/contract.md",
        worktree_path="/srv/worktrees/contract",
        harness="codex-crew",
        model="gpt-5-codex",
        effort=None,
        workspace_id=None,
    )
    target = tmp_path / "redirected.jsonl"
    path = tmp_path / "spawn-spool.jsonl"
    path.symlink_to(target)

    with pytest.raises(OSError):
        SpawnSpool(path).append(command)
    assert not target.exists()


def test_spool_replay_removes_only_a_typed_create_ack(tmp_path: Path) -> None:
    command = SpawnRecordCreate(
        client_command_id=uuid4(),
        project_key="ctower",
        seat_key="engineer",
        crew_name="mc-engineer-contract",
        task_file_ref="coordination/contract.md",
        worktree_path="/srv/worktrees/contract",
        harness="codex-crew",
        model="gpt-5-codex",
        effort=None,
        workspace_id=None,
    )
    spool = SpawnSpool(tmp_path / "spawn-spool.jsonl")
    spool.append(command)

    replayed, refused = replay_spool(spool, lambda _command: None)

    assert (replayed, refused) == (0, 1)
    assert len(spool.pending()) == 1


def test_import_derivation_is_latest_status_effective() -> None:
    """AC-SPWN-03 boundary: latest status wins; running set = never-terminated."""
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

    running = derive_initial_running_set(rows)
    assert [row.uuid for row in running] == [_RUNNING_ONE, _REVIVED]


def test_reconcile_reads_twin_until_recorded_parity_proof() -> None:
    """AC-SPWN-04 boundary: the swap needs one recorded proof, nothing less."""
    assert reconcile_source() == "external-twin"
    assert reconcile_source(parity_proof_recorded=False) == "external-twin"
    assert reconcile_source(parity_proof_recorded=True) == "ctower-spawn-reads"
