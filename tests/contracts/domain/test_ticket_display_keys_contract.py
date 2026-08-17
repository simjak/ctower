"""Ticket display-key migration contract vectors."""

from __future__ import annotations

import re
from pathlib import Path

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
MIGRATION = ROOT / "packages/ctower-kernel/migrations/0075_ticket_display_keys.sql"


def test_ticket_display_key_migration_is_additive_and_backfills_by_creation_order() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE ticket_display_sequences" in sql
    assert re.search(r"ALTER TABLE tickets\s+ADD COLUMN display_key", sql)
    assert re.search(r"ORDER BY ticket\.created_at, ticket\.ticket_id", sql)
    assert "CREATE UNIQUE INDEX tickets_display_key" in sql
    assert "CREATE FUNCTION refuse_ticket_display_key_mutation" in sql
    assert "BEFORE UPDATE OF display_key ON tickets" in sql
    assert "GRANT INSERT, SELECT, UPDATE ON ticket_display_sequences TO ctower_svc" in sql


def test_ticket_display_key_migration_registers_project_prefix_materialization() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER TABLE catalog_component_revisions\s+ADD COLUMN(?: IF NOT EXISTS)? project_prefix",
        sql,
    )
    assert "^[A-Z]{2,5}$" in sql
    assert "GRANT SELECT (project_prefix) ON catalog_component_revisions TO ctower_svc" in sql
