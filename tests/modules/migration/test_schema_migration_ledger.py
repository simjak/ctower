"""Real PostgreSQL tests for migration ledger state."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest

from ctower_kernel.record import _setup_sql
from ctower_kernel.record.postgres import (
    MigrationAdoptionError,
    MigrationBaseline,
    MigrationExecutionError,
    MigrationScript,
    MigrationStateError,
    apply_database_migrations,
    apply_migrations,
    provision_database_roles,
)

from ._postgres import Database

__all__: tuple[str, ...] = ()
ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "packages/ctower-kernel/migrations/manifest.json"
MAXIMUM_SAFE_MIGRATION_ERROR_DETAIL = 180


def test_fresh_empty_database_migrates_once_and_repeat_is_noop(
    migration_database: Database,
) -> None:
    _reset_to_empty_public_schema(migration_database)

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )
    first = _ledger_rows(migration_database)
    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    assert len(first) == _database_migration_count()
    assert all(row[2] == "applied" for row in first)
    assert _ledger_rows(migration_database) == first
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute("SELECT to_regclass('public.tenants')").fetchone() == ("tenants",)


def test_matching_preledger_database_is_adopted_and_repeat_is_noop(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )
    first = _ledger_rows(migration_database)
    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    assert len(first) == _database_migration_count()
    assert all(row[2] == "baseline" for row in first)
    assert _ledger_rows(migration_database) == first


def test_valid_looking_ledger_without_migrations_is_refused(
    migration_database: Database,
) -> None:
    _reset_to_empty_public_schema(migration_database)
    _manufacture_admin_owned_ledger(migration_database)

    with pytest.raises(MigrationStateError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "ledger-shape-mismatch"
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute("SELECT to_regclass('public.tenants')").fetchone() == (None,)


def test_existing_ledger_requires_exact_application_state(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE tenants CASCADE")

    with pytest.raises(MigrationStateError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "ledger-schema-mismatch"


def test_role_reconciliation_failure_cannot_commit_adoption(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")

    def refuse_role_reconciliation(_dsn: str) -> None:
        raise psycopg.OperationalError("forced role reconciliation failure")

    monkeypatch.setattr(
        "ctower_kernel.record._setup_sql._reconcile_database_roles_locked",
        refuse_role_reconciliation,
    )
    with pytest.raises(psycopg.OperationalError, match="forced role reconciliation failure"):
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    _assert_no_migration_ledger(migration_database)


def test_post_schema_role_closure_failure_leaves_explicit_resumable_state(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
    actual = _setup_sql._reconcile_database_roles_locked
    calls = 0

    def fail_second_reconciliation(dsn: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            actual(dsn)
            return
        raise psycopg.OperationalError("forced post-schema role closure failure")

    monkeypatch.setattr(
        "ctower_kernel.record._setup_sql._reconcile_database_roles_locked",
        fail_second_reconciliation,
    )
    with pytest.raises(psycopg.OperationalError, match="post-schema role closure failure"):
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    _assert_no_migration_ledger(migration_database)


def test_migration_execution_role_cannot_write_or_assume_ledger_authority(
    migration_database: Database,
) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    first = next(
        entry for entry in manifest["migrations"] if entry.get("scope", "database") == "database"
    )
    with psycopg.connect(migration_database.migrator_dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                """
                INSERT INTO ctower_schema_migrations (
                    migration_id, sha256, application_kind, result_schema_sha256
                ) VALUES (%s, %s, 'applied', %s)
                """,
                (first["path"], first["sha256"], "sha256:" + ("0" * 64)),
            )
    with psycopg.connect(migration_database.migrator_dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("SET ROLE ctower_migration_ledger")


def test_rewrite_rule_probe_is_typed_refusal_naming_the_mismatch(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        connection.execute(
            "CREATE RULE ctower_review_probe AS ON INSERT TO tenants DO INSTEAD NOTHING"
        )

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-schema-mismatch"
    assert "rule:public.tenants.ctower_review_probe" in raised.value.detail
    _assert_no_migration_ledger(migration_database)


def test_row_security_policy_probe_is_typed_refusal_naming_the_mismatch(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        connection.execute("CREATE POLICY ctower_policy_probe ON tenants USING (true)")

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-schema-mismatch"
    assert "policy:public.tenants.ctower_policy_probe" in raised.value.detail
    _assert_no_migration_ledger(migration_database)


def test_collation_probe_is_typed_refusal_naming_the_mismatch(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        connection.execute('CREATE COLLATION ctower_collation_probe FROM "C"')

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-schema-mismatch"
    assert "collation:public.ctower_collation_probe" in raised.value.detail
    _assert_no_migration_ledger(migration_database)


@pytest.mark.parametrize(
    "probe_sql",
    (
        "CREATE SCHEMA ctower_shadow_probe",
        "ALTER TABLE tenants SET (fillfactor = 70)",
        "CREATE TYPE ctower_composite_probe AS (value integer, label text)",
        """
        CREATE TYPE ctower_range_probe AS RANGE (
            subtype = integer,
            multirange_type_name = ctower_multirange_probe
        )
        """,
        "CREATE STATISTICS ctower_statistics_probe ON slug, name FROM tenants",
        "COMMENT ON TABLE tenants IS 'ctower-comment-probe'",
        "CREATE PUBLICATION ctower_publication_probe FOR TABLE tenants",
    ),
    ids=(
        "non-public-schema",
        "relation-storage-options",
        "composite-type-shape",
        "multirange-type-shape",
        "extended-statistics",
        "comment",
        "publication-membership",
    ),
)
def test_each_additional_cso_catalog_class_changes_the_canonical_fingerprint(
    migration_database: Database,
    probe_sql: str,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        connection.execute(probe_sql)

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-schema-mismatch"
    _assert_no_migration_ledger(migration_database)


def test_dependency_discovery_catches_an_object_kind_without_a_dedicated_query(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        connection.execute(
            """
            CREATE TEXT SEARCH CONFIGURATION ctower_search_probe
            (COPY = pg_catalog.simple)
            """
        )

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-schema-mismatch"
    _assert_no_migration_ledger(migration_database)


def test_non_public_schema_is_a_typed_adoption_refusal(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        connection.execute("CREATE SCHEMA ctower_shadow_probe")

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-schema-mismatch"
    assert "schema:ctower_shadow_probe" in raised.value.detail
    _assert_no_migration_ledger(migration_database)


def test_preledger_schema_mismatch_is_typed_refusal_without_ledger(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE IF EXISTS ctower_schema_migrations")
        connection.execute("ALTER TABLE tenants ADD COLUMN unreviewed_marker text")

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-schema-mismatch"
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.ctower_schema_migrations')"
        ).fetchone() == (None,)


def test_preledger_semantic_mismatch_is_typed_refusal_without_ledger(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE IF EXISTS ctower_schema_migrations")
        connection.execute("UPDATE record_position_ledger SET last_position = last_position + 1")

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-semantic-mismatch"
    assert "record-position-ledger" in raised.value.detail
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.ctower_schema_migrations')"
        ).fetchone() == (None,)


def test_preledger_record_position_reassignment_is_refused(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        _insert_probe_events(connection, migration_database, count=2)
        connection.execute("UPDATE events SET record_position = 3 WHERE record_position = 1")
        connection.execute("UPDATE events SET record_position = 1 WHERE record_position = 2")
        connection.execute("UPDATE events SET record_position = 2 WHERE record_position = 3")

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-semantic-mismatch"
    assert "record-position-history-unprovable" in raised.value.detail
    _assert_no_migration_ledger(migration_database)


def test_preledger_extra_event_link_is_refused_bidirectionally(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        event_ids = _insert_probe_events(connection, migration_database, count=1)
        connection.execute(
            """
            INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
            VALUES (%s, %s, 'ticket', %s)
            """,
            (event_ids[0], migration_database.tenant_id, uuid4()),
        )

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-semantic-mismatch"
    assert "event-link-backfill" in raised.value.detail
    _assert_no_migration_ledger(migration_database)


def test_preledger_workflow_start_fact_requires_exact_contents(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        _insert_mismatched_workflow_start_fact(connection, migration_database)

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-semantic-mismatch"
    assert "workflow-start-fact-backfill" in raised.value.detail
    _assert_no_migration_ledger(migration_database)


def test_existing_ledger_checksum_drift_is_typed_refusal(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE ctower_schema_migrations
            SET sha256 = %s
            WHERE migration_id = (
                SELECT min(migration_id) FROM ctower_schema_migrations
            )
            """,
            ("sha256:" + ("f" * 64),),
        )

    with pytest.raises(MigrationStateError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "ledger-checksum-mismatch"


def test_failed_migration_rolls_back_schema_and_ledger(
    migration_database: Database,
) -> None:
    _reset_to_empty_public_schema(migration_database)
    sha256 = "sha256:" + ("a" * 64)
    migrations = (
        MigrationScript(
            "9000_transaction_probe.sql",
            sha256,
            "database",
            "CREATE TABLE transaction_probe (marker integer)",
        ),
        MigrationScript(
            "9001_broken_probe.sql",
            sha256,
            "database",
            "CREATE TABLE broken_probe (",
        ),
    )
    baseline = MigrationBaseline(
        "9001_broken_probe.sql",
        "sha256:" + ("0" * 64),
        "ctower.pre-ledger/v1",
        "sum256:" + ("0" * 64),
    )

    with (
        pytest.raises(MigrationExecutionError) as raised,
        psycopg.connect(migration_database.migrator_dsn) as connection,
    ):
        connection.execute("SET ROLE ctower_admin")
        apply_database_migrations(connection, migrations, baseline)

    assert raised.value.code == "migration-execution-failed"
    assert raised.value.detail.startswith("9001_broken_probe.sql failed with SQLSTATE 42601;")
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            """
            SELECT to_regclass('public.transaction_probe'),
                   to_regclass('public.ctower_schema_migrations')
            """
        ).fetchone() == (None, None)


def test_migration_sql_failure_is_typed_and_does_not_disclose_row(
    migration_database: Database,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    _reset_to_empty_public_schema(migration_database)
    marker = "ctower-sensitive-row-marker"
    sha256 = "sha256:" + ("b" * 64)
    migrations = (
        MigrationScript(
            "9000_sensitive_probe.sql",
            sha256,
            "database",
            "CREATE TABLE sensitive_probe (value text CHECK (value = 'safe'))",
        ),
        MigrationScript(
            "9001_constraint_probe.sql",
            sha256,
            "database",
            "INSERT INTO sensitive_probe VALUES ('ctower-sensitive-row-marker')",
        ),
    )
    baseline = MigrationBaseline(
        "9001_constraint_probe.sql",
        "sha256:" + ("0" * 64),
        "ctower.pre-ledger/v1",
        "sum256:" + ("0" * 64),
    )

    with (
        pytest.raises(MigrationStateError) as raised,
        psycopg.connect(migration_database.migrator_dsn) as connection,
    ):
        connection.execute("SET ROLE ctower_admin")
        apply_database_migrations(connection, migrations, baseline)

    captured = capsys.readouterr()
    assert raised.value.code == "migration-execution-failed"
    assert "9001_constraint_probe.sql" in raised.value.detail
    assert "23514" in raised.value.detail
    assert marker not in str(raised.value)
    assert marker not in repr(raised.value)
    assert marker not in captured.out
    assert marker not in captured.err
    assert marker not in caplog.text
    assert len(raised.value.detail) < MAXIMUM_SAFE_MIGRATION_ERROR_DETAIL


def test_two_concurrent_fresh_callers_apply_every_migration_once(
    migration_database: Database,
) -> None:
    _reset_to_empty_public_schema(migration_database)
    start = Barrier(2)

    def migrate() -> None:
        start.wait()
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = (workers.submit(migrate), workers.submit(migrate))
        for future in futures:
            future.result(timeout=60)

    rows = _ledger_rows(migration_database)
    assert len(rows) == _database_migration_count()
    assert len({row[0] for row in rows}) == len(rows)
    assert all(row[2] == "applied" for row in rows)


def _reset_to_empty_public_schema(database: Database) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public AUTHORIZATION pg_database_owner")
        connection.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
        connection.execute("COMMENT ON SCHEMA public IS 'standard public schema'")
    provision_database_roles(database.admin_dsn)


def _ledger_rows(database: Database) -> list[tuple[object, ...]]:
    with psycopg.connect(database.admin_dsn) as connection:
        return connection.execute(
            """
            SELECT migration_id, sha256, application_kind, applied_at
            FROM ctower_schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()


def _assert_no_migration_ledger(database: Database) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.ctower_schema_migrations')"
        ).fetchone() == (None,)


def _manufacture_admin_owned_ledger(database: Database) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = [
        (entry["path"], entry["sha256"], "applied")
        for entry in manifest["migrations"]
        if entry.get("scope", "database") == "database"
    ]
    with psycopg.connect(database.migrator_dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        connection.execute(
            """
            CREATE TABLE ctower_schema_migrations (
                migration_id text PRIMARY KEY
                    CHECK (migration_id ~ '^[0-9]{4}_[a-z0-9_]+[.]sql$'),
                sha256 text NOT NULL
                    CHECK (sha256 ~ '^sha256:[0-9a-f]{64}$'),
                application_kind text NOT NULL
                    CHECK (application_kind IN ('applied', 'baseline')),
                applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
            )
            """
        )
        connection.cursor().executemany(
            """
            INSERT INTO ctower_schema_migrations (
                migration_id, sha256, application_kind
            ) VALUES (%s, %s, %s)
            """,
            rows,
        )
        connection.execute(
            """
            REVOKE ALL ON ctower_schema_migrations
            FROM PUBLIC, ctower_svc, ctower_projection, ctower_runtime,
                 ctower_projection_runtime
            """
        )


def _database_migration_count() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return sum(entry.get("scope", "database") == "database" for entry in manifest["migrations"])


def _insert_probe_events(
    connection: psycopg.Connection[tuple[object, ...]],
    database: Database,
    *,
    count: int,
) -> tuple[UUID, ...]:
    now = datetime.now(UTC)
    event_ids = tuple(uuid4() for _ in range(count))
    connection.cursor().executemany(
        """
        INSERT INTO events (
            event_id, tenant_id, stream_id, aggregate_id, sequence, kind, schema_version,
            actor_principal_id, client_command_id, request_sha256, correlation_id,
            causation_id, origin, server_time, payload, prev_hash, event_hash,
            record_position
        ) VALUES (
            %s, %s, %s, %s, 1, 'routine.occurrence_recorded', 1,
            %s, %s, %s, %s, NULL, 'api', %s, '{}'::jsonb, %s, %s, %s
        )
        """,
        tuple(
            (
                event_id,
                database.tenant_id,
                f"probe:{index}",
                uuid4(),
                database.operator_id,
                uuid4(),
                bytes(32),
                uuid4(),
                now,
                bytes(32),
                bytes([index]) * 32,
                index,
            )
            for index, event_id in enumerate(event_ids, start=1)
        ),
    )
    connection.execute(
        "UPDATE record_position_ledger SET last_position = %s WHERE singleton",
        (count,),
    )
    return event_ids


def _insert_mismatched_workflow_start_fact(
    connection: psycopg.Connection[tuple[object, ...]],
    database: Database,
) -> None:
    now = datetime.now(UTC)
    ticket_id, workflow_run_id, event_id = uuid4(), uuid4(), uuid4()
    connection.execute(
        """
        INSERT INTO tickets (
            ticket_id, tenant_id, title, source_kind, source_ref, priority,
            custodian_principal_id, version, durability_state, created_by, created_at
        ) VALUES (%s, %s, 'Probe', 'test', 'probe', 'P1', %s, 1,
                  'durability_pending', %s, %s)
        """,
        (
            ticket_id,
            database.tenant_id,
            database.operator_id,
            database.operator_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO workflow_runs (
            workflow_run_id, ticket_id, tenant_id, workflow_key, workflow_revision,
            initial_stage, current_stage, activity_class, version, created_at, started_by
        ) VALUES (%s, %s, %s, 'probe', 1, 'start', 'start', 'work', 1, %s, %s)
        """,
        (
            workflow_run_id,
            ticket_id,
            database.tenant_id,
            now,
            database.operator_id,
        ),
    )
    connection.execute(
        """
        INSERT INTO events (
            event_id, tenant_id, stream_id, aggregate_id, sequence, kind, schema_version,
            actor_principal_id, client_command_id, request_sha256, correlation_id,
            causation_id, origin, server_time, payload, prev_hash, event_hash,
            record_position
        ) VALUES (
            %s, %s, %s, %s, 1, 'workflow.changed', 1, %s, %s, %s, %s,
            NULL, 'api', %s, '{"operation":"start"}'::jsonb, %s, %s, 1
        )
        """,
        (
            event_id,
            database.tenant_id,
            f"workflow:{workflow_run_id}",
            workflow_run_id,
            database.operator_id,
            uuid4(),
            bytes(32),
            uuid4(),
            now,
            bytes(32),
            bytes([1]) * 32,
        ),
    )
    connection.cursor().executemany(
        """
        INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
        VALUES (%s, %s, %s, %s)
        """,
        (
            (event_id, database.tenant_id, "workflow", workflow_run_id),
            (event_id, database.tenant_id, "ticket", ticket_id),
        ),
    )
    connection.execute(
        """
        INSERT INTO workflow_start_facts (
            event_id, tenant_id, workflow_run_id, ticket_id, activity_class, recorded_at
        ) VALUES (%s, %s, %s, %s, 'verification', %s)
        """,
        (event_id, database.tenant_id, workflow_run_id, ticket_id, now),
    )
    connection.execute("UPDATE record_position_ledger SET last_position = 1 WHERE singleton")
