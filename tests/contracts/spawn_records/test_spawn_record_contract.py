"""Authored spawn-custody contract boundaries (CT-I1-034, AC-SPWN-01..04)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from ctower_client.models import DurabilityState, SpawnRecordResult

ROOT = Path(__file__).parents[3]
_SPAWN_OPERATIONS = {
    "createSpawnRecord",
    "listSpawnRecords",
    "getSpawnRecord",
    "appendSpawnTransition",
}
_IMMUTABLE_TABLES = 2


def test_spawn_http_surface_is_strict_and_append_only() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    operations = {
        operation["operationId"]: operation
        for path in document["paths"].values()
        for method, operation in path.items()
        if method in {"get", "post"} and isinstance(operation, dict)
    }

    assert {name for name in operations if "spawn" in name.casefold()} == _SPAWN_OPERATIONS
    create = operations["createSpawnRecord"]
    assert create["x-ctower-mutation"] is True
    assert create["x-ctower-spool"] == "allowed"
    assert create["x-ctower-cli"] == "spawn record"
    transition = operations["appendSpawnTransition"]
    assert transition["x-ctower-mutation"] is True
    assert transition["x-ctower-spool"] == "allowed"
    assert operations["listSpawnRecords"]["x-ctower-mutation"] is False

    for path in document["paths"]:
        if "spawn" in path:
            assert set(document["paths"][path]) <= {"get", "post", "parameters"}


def test_spawn_storage_is_append_only_with_derived_state() -> None:
    migration = (ROOT / "packages/ctower-kernel/migrations/0076_spawn_records.sql").read_text(
        encoding="utf-8"
    )

    assert "\n    status text" not in migration
    assert migration.upper().count("UPDATE") == _IMMUTABLE_TABLES
    assert migration.upper().count("BEFORE UPDATE OR DELETE") == _IMMUTABLE_TABLES
    assert "CREATE TABLE spawn_records" in migration
    assert "CREATE TABLE spawn_record_transitions" in migration
    assert "UNIQUE (spawn_id, tenant_id, transition_number)" in migration
    assert migration.count("refuse_immutable_control_fact_mutation") == _IMMUTABLE_TABLES
    assert migration.count("'spawn.recorded'") == 1
    assert migration.count("'spawn.transitioned'") == 1
    assert migration.count("'spawn_record'") == _IMMUTABLE_TABLES
    assert (
        "GRANT INSERT, SELECT ON spawn_records, spawn_record_transitions TO ctower_svc" in migration
    )
    assert (
        "GRANT SELECT ON spawn_records, spawn_record_transitions TO ctower_projection" in migration
    )


def test_spawn_event_catalog_sources_are_closed() -> None:
    events = (ROOT / "packages/ctower-kernel/src/ctower_kernel/record/events.py").read_text(
        encoding="utf-8"
    )
    spawn_events = (
        ROOT / "packages/ctower-kernel/src/ctower_kernel/record/spawn_events.py"
    ).read_text(encoding="utf-8")
    assert "EventKind.SPAWN_RECORDED" in events
    assert "EventKind.SPAWN_TRANSITIONED" in events
    assert "def spawn_transition_allowed" in spawn_events


def test_generated_client_covers_spawn_operations() -> None:
    operations = (ROOT / "generated/python/ctower_client/operations.py").read_text(encoding="utf-8")
    assert all(name in operations for name in _SPAWN_OPERATIONS)


def test_generated_response_accepts_an_appended_transition_fact() -> None:
    spawn_id = uuid4()
    principal_id = uuid4()
    result = SpawnRecordResult.model_validate(
        {
            "spawn_id": spawn_id,
            "project_key": "ctower",
            "seat_key": "engineer",
            "crew_name": "mc-engineer-contract",
            "task_file_ref": "coordination/contract.md",
            "worktree_path": "/srv/worktrees/contract",
            "harness": "codex-crew",
            "model": "gpt-5-codex",
            "status": "accepted",
            "principal_id": principal_id,
            "created_at": "2026-08-15T00:00:00Z",
            "updated_at": "2026-08-15T00:01:00Z",
            "transitions": (
                {
                    "transition_id": uuid4(),
                    "spawn_id": spawn_id,
                    "from_status": "requested",
                    "to_status": "accepted",
                    "reason": "operator confirmed",
                    "principal_id": principal_id,
                    "transitioned_at": "2026-08-15T00:01:00Z",
                },
            ),
            "durability_state": DurabilityState.ACCEPTED,
            "accepted_position": 1,
        }
    )
    assert result.status == "accepted"
    assert result.transitions[0].to_status == "accepted"


def test_spawn_openapi_seat_key_matches_event_contract() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    expected_pattern = r"^[a-z][a-z0-9._-]{0,95}$"

    for schema_name in ("SpawnRecordCreateRequest", "SpawnRecord", "SpawnRecordResult"):
        schema = document["components"]["schemas"][schema_name]
        assert schema["properties"]["seat_key"]["pattern"] == expected_pattern
