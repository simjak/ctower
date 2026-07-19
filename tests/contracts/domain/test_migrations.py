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
    assert names == ["0001_roles.sql", "0002_ticket_slice.sql", "0003_privileges.sql"]
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


def test_development_composition_uses_postgres_17_without_a_password_value() -> None:
    compose = (ROOT / "deploy/development/compose.yaml").read_text(encoding="utf-8")

    assert "postgres:17" in compose
    assert "POSTGRES_HOST_AUTH_METHOD: trust" in compose
    assert "POSTGRES_PASSWORD" not in compose
