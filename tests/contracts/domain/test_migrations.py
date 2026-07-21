"""Ordered migration, privilege, and development-Postgres contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "packages/ctower-kernel/migrations"


def test_migration_manifest_is_ordered_and_checksum_exact() -> None:
    manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    entries = cast(list[dict[str, str]], manifest["migrations"])
    names = [entry["path"] for entry in entries]

    assert manifest["schema"] == "ctower.migrations/v1"
    assert names == sorted(names)
    assert names == [
        "0001_roles.sql",
        "0002_ticket_slice.sql",
        "0003_privileges.sql",
        "0004_proof_workflow.sql",
        "0005_proof_verdict_sequence.sql",
        "0006_narrow_head_update_privileges.sql",
        "0007_task_management_facts.sql",
        "0008_board_projection.sql",
        "0009_transactional_record_positions.sql",
        "0010_custody_episode_intervals.sql",
        "0011_persisted_command_refusals.sql",
        "0012_projection_runtime_role.sql",
    ]
    for entry in entries:
        digest = hashlib.sha256((MIGRATIONS / entry["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == f"sha256:{digest}"


def test_service_and_projection_roles_are_least_privilege() -> None:
    roles = (MIGRATIONS / "0001_roles.sql").read_text(encoding="utf-8")
    grants = (MIGRATIONS / "0003_privileges.sql").read_text(encoding="utf-8")

    assert "ctower_admin" in roles
    assert "ctower_svc" in roles
    assert "ctower_projection" in roles
    assert "GRANT INSERT, SELECT ON events, command_results, outbox TO ctower_svc" in grants
    assert "GRANT UPDATE" not in grants
    assert "GRANT DELETE" not in grants
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA public TO ctower_projection" in grants


def test_verdict_sequence_migration_backfills_from_authoritative_events() -> None:
    migration = (MIGRATIONS / "0005_proof_verdict_sequence.sql").read_text(encoding="utf-8")

    assert "SET proof_sequence = event.sequence" in migration
    assert "event.actor_principal_id = verdict.reviewer_id" in migration
    assert "event.client_command_id = verdict.client_command_id" in migration
    assert "proof_verdicts_sequence_unique" in migration
    assert "ALTER COLUMN proof_sequence SET NOT NULL" in migration


def test_cp2_migrations_separate_authority_from_disposable_projection() -> None:
    facts = (MIGRATIONS / "0007_task_management_facts.sql").read_text(encoding="utf-8")
    projection = (MIGRATIONS / "0008_board_projection.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE admission_facts" in facts
    assert "CREATE TABLE blocker_facts" in facts
    assert "CREATE TABLE ticket_relations" in facts
    assert "workflow_digest" in facts
    assert "CREATE TABLE event_links" in projection
    assert "record_position" in projection
    assert "CREATE TABLE board_projection_rows" in projection
    assert "GRANT INSERT, UPDATE, DELETE ON board_projection_rows" in projection
    assert "TO ctower_projection" in projection
    assert "GRANT INSERT, UPDATE, DELETE ON board_projection_rows TO ctower_svc" not in projection


def test_runtime_and_migrator_use_distinct_one_way_login_roles() -> None:
    roles = (MIGRATIONS / "0001_roles.sql").read_text(encoding="utf-8")

    assert "CREATE ROLE ctower_runtime LOGIN" in roles
    assert "CREATE ROLE ctower_migrator LOGIN" in roles
    assert "GRANT ctower_svc TO ctower_runtime" in roles
    assert "GRANT ctower_admin TO ctower_migrator" in roles
    assert "REVOKE ctower_admin FROM ctower_runtime" in roles
    assert "GRANT ctower_admin TO ctower_runtime" not in roles


def test_projection_runtime_login_can_assume_only_projection_role() -> None:
    role = (MIGRATIONS / "0012_projection_runtime_role.sql").read_text(encoding="utf-8")

    assert "CREATE ROLE ctower_projection_runtime" in role
    assert "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in role
    assert "GRANT ctower_projection TO ctower_projection_runtime" in role
    assert "REVOKE ctower_svc, ctower_admin FROM ctower_projection_runtime" in role


def test_development_composition_uses_postgres_17_without_a_password_value() -> None:
    compose = (ROOT / "deploy/development/compose.yaml").read_text(encoding="utf-8")

    assert "postgres:17" in compose
    assert "POSTGRES_HOST_AUTH_METHOD: trust" in compose
    assert "POSTGRES_PASSWORD" not in compose
