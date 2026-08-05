"""Real PostgreSQL tests for attestation stability across a re-parse (gh#247).

PostgreSQL's raw deparse is not a fixed point. `0027` authors a CHECK whose first conjunct is a
`BETWEEN`, which the parser expands into its own nested `AND` node; deparsing renders that
faithfully, and re-parsing the rendered text flattens it. Any operation that re-creates schema
objects from generated SQL therefore rewrites the text of an object nobody touched — a restore
being the one that reached production. The attestation hashed that text, so the operator's shadow
instance came back from a `checkpoint` restore with its data intact, its schema semantically
identical, and `database-up` refusing at `ledger-schema-mismatch` before any DDL, permanently.

These tests reproduce that shape on a real database and hold the fix to it.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql

from ctower_kernel.record import _migration_ledger_sql
from ctower_kernel.record.postgres import apply_migrations

from ._ledger_support import (
    LEDGERED_TERMINAL,
    adoption_baseline_through,
    install_ledger_through,
    ledger_rows,
    record_used_instance_history,
    rewrite_terminal_attestation,
)
from ._postgres import Database

__all__: tuple[str, ...] = ()

# 0027 authors this one with `cardinality(...) BETWEEN 2 AND 8` leading a four-term AND chain.
REPARSED_TABLE = "project_delivery_checkpoint_definitions"
REPARSED_CONSTRAINT = "project_delivery_checkpoint_definitions_applicable_states_check"


def test_the_raw_deparse_is_not_a_fixed_point(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The premise. If PostgreSQL ever makes this stable, this test says so by name."""

    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)

    authored, restored = _replay_as_a_restore_would(migration_database)

    # The whole difference is one level of grouping: BETWEEN's own AND node survives the first
    # deparse and is flattened into the outer AND by the re-parse.
    assert authored != restored
    assert authored.startswith("CHECK ((((cardinality(applicable_states) >= 2)")
    assert restored.startswith("CHECK (((cardinality(applicable_states) >= 2)")


def test_a_reparsed_constraint_moves_the_raw_attestation_but_not_the_canonical_one(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)
    raw_before, canonical_before = _attestations(migration_database)

    _replay_as_a_restore_would(migration_database)

    raw_after, canonical_after = _attestations(migration_database)
    assert raw_after != raw_before
    assert canonical_after == canonical_before


def test_ledgered_instance_completes_the_pending_set_after_a_restore_reparse(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operator's instance, reproduced: history, a restore's re-parse, then the upgrade."""

    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)
    record_used_instance_history(migration_database)
    _replay_as_a_restore_would(migration_database)

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    recorded = ledger_rows(migration_database)
    assert recorded[-1][0] == adoption_baseline_through()


def test_an_attestation_recorded_before_canonical_rendering_still_verifies(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every instance ledgered before gh#247 holds a raw digest. It must keep verifying."""

    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)
    record_used_instance_history(migration_database)
    superseded, canonical = _attestations(migration_database)
    assert superseded != canonical
    rewrite_terminal_attestation(migration_database, superseded)

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    recorded = ledger_rows(migration_database)
    assert recorded[-1][0] == adoption_baseline_through()


def test_a_real_schema_change_still_fails_attestation(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tolerating two renderings must not tolerate an actual difference.

    A GENUINE schema difference still refuses, the refusal happens PRE-DDL (the dropped
    constraint is still absent after the refused apply), and the diagnostic names all three
    digests so the operator can diff the evidence.
    """

    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)
    record_used_instance_history(migration_database)
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute(
            sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                sql.Identifier(REPARSED_TABLE), sql.Identifier(REPARSED_CONSTRAINT)
            )
        )
        attested_row = connection.execute(
            "SELECT result_schema_sha256 FROM ctower_schema_migrations WHERE migration_id = %s",
            (LEDGERED_TERMINAL,),
        ).fetchone()
        assert attested_row is not None, f"{LEDGERED_TERMINAL} is missing from the ledger"
        attested = str(attested_row[0])

    with pytest.raises(_migration_ledger_sql.MigrationStateError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "ledger-schema-mismatch"
    detail = raised.value.detail
    # The diagnostic carries all three digests for an operator to diff.
    assert f"attested={attested}" in detail
    assert "live_canonical=" in detail
    assert "live_superseded_raw=" in detail
    canonical = detail.split("live_canonical=", 1)[1].split(" ", 1)[0]
    superseded_raw = detail.split("live_superseded_raw=", 1)[1]
    assert canonical != superseded_raw
    assert attested not in (canonical, superseded_raw)
    # PRE-DDL proof: the refusal happened before any migration DDL, so the dropped
    # constraint is still absent after the refused apply — nothing re-created it.
    with psycopg.connect(migration_database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = %s", (REPARSED_CONSTRAINT,)
        ).fetchone()
        assert row is None


def _attestations(database: Database) -> tuple[str, str]:
    """The superseded (raw) and current (canonical) fingerprints of the same live schema."""

    with psycopg.connect(database.admin_dsn) as connection:
        superseded = _migration_ledger_sql._schema_fingerprint(
            _migration_ledger_sql._schema_records(connection, canonical=False)
        )
        canonical = _migration_ledger_sql._schema_fingerprint(
            _migration_ledger_sql._schema_records(connection, canonical=True)
        )
    return superseded, canonical


def _replay_as_a_restore_would(database: Database) -> tuple[str, str]:
    """Re-create the constraint from its own deparsed text — exactly what pg_dump/psql does.

    Returns the definition before and after, so a caller can assert on the drift itself rather
    than trusting that the replay changed anything.
    """

    with psycopg.connect(database.admin_dsn) as connection:
        authored = _definition(connection)
        connection.execute(
            sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                sql.Identifier(REPARSED_TABLE), sql.Identifier(REPARSED_CONSTRAINT)
            )
        )
        connection.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} " + authored).format(
                sql.Identifier(REPARSED_TABLE), sql.Identifier(REPARSED_CONSTRAINT)
            )
        )
        return authored, _definition(connection)


def _definition(connection: psycopg.Connection[tuple[object, ...]]) -> str:
    row = connection.execute(
        "SELECT pg_get_constraintdef(oid, false) FROM pg_constraint WHERE conname = %s",
        (REPARSED_CONSTRAINT,),
    ).fetchone()
    assert row is not None, f"{REPARSED_CONSTRAINT} is missing from the catalog"
    return str(row[0])
