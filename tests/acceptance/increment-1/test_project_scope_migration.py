"""Disposable pre-0038 upgrade evidence for project-scoped ticket authority."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from support.postgres import DatabaseFixture

from ctower_kernel.record.postgres import provision_database_roles

__all__: tuple[str, ...] = ()
ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "packages/ctower-kernel/migrations"
UNBOUND_TICKETS = 2


def test_0038_reports_two_unbound_tickets_derived_from_the_binding_domain(
    database: DatabaseFixture,
) -> None:
    provision_database_roles(database.admin_dsn)
    notices: list[str] = []
    tenant_id, commander_id = uuid4(), uuid4()
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        _apply_pre_0038(connection)
        now = datetime.now(UTC)
        connection.execute(
            """
            INSERT INTO tenants (tenant_id, slug, name, created_at)
            VALUES (%s, 'probe', 'Probe', %s)
            """,
            (tenant_id, now),
        )
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, 'commander', 'Probe Commander', false, %s)
            """,
            (commander_id, tenant_id, now),
        )
        connection.cursor().executemany(
            """
            INSERT INTO tickets (
                ticket_id, tenant_id, title, source_kind, source_ref, priority,
                custodian_principal_id, version, durability_state, created_by, created_at
            ) VALUES (%s, %s, %s, 'probe', %s, 'P2', %s, 1,
                'durability_pending', %s, %s)
            """,
            tuple(
                (
                    uuid4(),
                    tenant_id,
                    f"Unbound ticket {ordinal}",
                    f"probe:{ordinal}",
                    commander_id,
                    commander_id,
                    now,
                )
                for ordinal in range(1, UNBOUND_TICKETS + 1)
            ),
        )
        connection.add_notice_handler(
            lambda diagnostic: notices.append(str(diagnostic.message_primary))
        )
        connection.execute(
            (MIGRATIONS / "0038_project_scoped_reads.sql").read_text(encoding="utf-8")
        )
        rows = connection.execute(
            "SELECT title, project_key FROM tickets ORDER BY title"
        ).fetchall()

    assert notices == [
        "0038_project_scoped_reads: defaulted_ticket_count=2 authoritative_project_key=ctower"
    ]
    assert rows == [("Unbound ticket 1", "ctower"), ("Unbound ticket 2", "ctower")]


def _apply_pre_0038(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["migrations"]:
        path = str(entry["path"])
        if path == "0038_project_scoped_reads.sql":
            return
        if entry.get("scope", "database") == "database":
            connection.execute((MIGRATIONS / path).read_text(encoding="utf-8"))
    raise AssertionError("0038 migration is absent from the authored manifest")
