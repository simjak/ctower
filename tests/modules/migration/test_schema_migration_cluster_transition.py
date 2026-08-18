"""Real PostgreSQL coverage for cluster changes between ledgered database migrations."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError

from ctower_kernel.record import _migration_ledger_sql, _setup_sql
from ctower_kernel.record.postgres import (
    MigrationBaseline,
    MigrationStateError,
    apply_migrations,
    provision_database_roles,
)

from . import _postgres
from ._ledger_support import schema_snapshot, use_migrations
from ._postgres import Database

__all__: tuple[str, ...] = ()

RECORDED_THROUGH = "0063_routine_revision_activation.sql"
RECORDED_SCHEMA_SHA256 = "sha256:cc7fffb7ce2f4fd55d3f5ed8746e42e8b6679847fc47de40d51262a9dad5423c"
TRANSITION_SCHEMA_SHA256 = "sha256:a0aad539aed6b65580daf16ac047856ef48fcbd72b82c396220e44ebe1a85d03"
RECORDED_OBJECT_SUM256 = "sum256:9496a4684ee94bb236c93cbab81d8a6e6cedf10555048665a594d717402e2644"
FINAL_SCHEMA_SHA256 = "sha256:6c6d47e90c4d25e8adc0a1e9eda449c4b613b44268e59b6265f1f6dd7510ec9c"
POSTGRES_16_SCHEMA_SHA256 = (
    "sha256:2ee604d20af64d52254e8c1e0d2b40ee4b28afa81b8cf85e09c047d66538c9d8"
)
RESTORED_RAW_SCHEMA_SHA256 = (
    "sha256:fbecf19934165e604468f49e21c3ee88a900b7333f4fb110b18a3aebeb59f6e5"
)
FRESH_TRANSITION_RAW_SCHEMA_SHA256 = (
    "sha256:1be72c6444fb8ae2fce8b35b5df395501b0557f1c1e5c95cc6c4966a693ea4b5"
)
POSTGRES_17_MAJOR = 17
POSTGRES_17_SERVER_VERSION_MIN = 170000
POSTGRES_18_SERVER_VERSION_MIN = 180000


def test_v3_manifest_has_no_compatibility_parser() -> None:
    resources = _setup_sql._migration_resources()
    manifest = json.loads(resources.joinpath("manifest.json").read_text(encoding="utf-8"))
    manifest["schema"] = "ctower.migrations/v3"

    with pytest.raises(ValidationError):
        _setup_sql._MigrationManifest.model_validate(manifest)


def test_declared_cluster_transition_advances_the_recorded_0063_instance(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_legacy_ledger_through_0063(migration_database, monkeypatch)
    recorded_before = _legacy_ledger_rows(migration_database)
    before_fingerprint, before_records = schema_snapshot(migration_database)

    provision_database_roles(migration_database.admin_dsn)

    transition_fingerprint, transition_records = schema_snapshot(migration_database)
    assert before_fingerprint == RECORDED_SCHEMA_SHA256
    assert transition_fingerprint == TRANSITION_SCHEMA_SHA256
    assert _object_sum256(before_records) == RECORDED_OBJECT_SUM256
    assert _object_sum256(transition_records) == RECORDED_OBJECT_SUM256
    assert _acl_delta(before_records, transition_records) == (
        (
            "removed",
            "schema.public.ctower_admin.CREATE",
            {"grantor": "pg_database_owner", "grantable": False},
        ),
        (
            "added",
            "schema.public.console_output_reader.USAGE",
            {"grantor": "pg_database_owner", "grantable": False},
        ),
        (
            "added",
            "schema.public.ctower_admin.CREATE",
            {"grantor": "pg_database_owner", "grantable": True},
        ),
    )

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    recorded_after = _versioned_ledger_rows(migration_database)
    assert [row[:5] for row in recorded_after[: len(recorded_before)]] == recorded_before
    assert all(row[5] is None for row in recorded_after[: len(recorded_before)])
    assert [row[0] for row in recorded_after[-6:]] == [
        "0072_estate_import_authority.sql",
        "0073_restore_request_proposal_constraints.sql",
        "0074_restore_routine_retirement_kind.sql",
        "0075_ticket_display_keys.sql",
        "0076_spawn_records.sql",
        "0077_inbox_message_severity.sql",
    ]
    assert all(
        isinstance(row[5], int)
        and POSTGRES_17_SERVER_VERSION_MIN <= row[5] < POSTGRES_18_SERVER_VERSION_MIN
        for row in recorded_after[-5:]
    )
    assert recorded_after[-1][3] == FINAL_SCHEMA_SHA256


def test_restored_shadow_shape_uses_canonical_transition_not_raw_digest(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_legacy_ledger_through_0063(migration_database, monkeypatch)
    provision_database_roles(migration_database.admin_dsn)
    canonical_before, _ = _fingerprints(migration_database)

    _dump_and_restore_with_postgres_17(migration_database)

    canonical_after, raw_after = _fingerprints(migration_database)
    assert canonical_before == TRANSITION_SCHEMA_SHA256
    assert canonical_after == TRANSITION_SCHEMA_SHA256
    assert raw_after == RESTORED_RAW_SCHEMA_SHA256

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    assert _versioned_ledger_rows(migration_database)[-1][3] == FINAL_SCHEMA_SHA256


def test_retry_after_cluster_phase_and_two_concurrent_callers_converge_once(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_legacy_ledger_through_0063(migration_database, monkeypatch)
    actual = _migration_ledger_sql.apply_database_migrations
    calls = 0

    def fail_once(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("forced failure after cluster transition")
        return actual(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_setup_sql, "apply_database_migrations", fail_once)
    with pytest.raises(RuntimeError, match="forced failure after cluster transition"):
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert schema_snapshot(migration_database)[0] == TRANSITION_SCHEMA_SHA256
    assert _versioned_ledger_rows(migration_database)[-1][0] == RECORDED_THROUGH
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            """
            SELECT to_regclass('public.console_view_grants'),
                   to_regclass('public.routine_retirements')
            """
        ).fetchone() == (None, None)

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

    rows = _versioned_ledger_rows(migration_database)
    assert [row[0] for row in rows[-6:]] == [
        "0072_estate_import_authority.sql",
        "0073_restore_request_proposal_constraints.sql",
        "0074_restore_routine_retirement_kind.sql",
        "0075_ticket_display_keys.sql",
        "0076_spawn_records.sql",
        "0077_inbox_message_severity.sql",
    ]
    assert len({row[0] for row in rows}) == len(rows)


def test_ledger_checksum_refuses_before_private_shape_upgrade(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_legacy_ledger_through_0063(migration_database, monkeypatch)
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("SET ROLE ctower_migration_ledger")
        connection.execute(
            """
            UPDATE ctower_schema_migrations
            SET sha256 = %s
            WHERE migration_id = %s
            """,
            ("sha256:" + ("0" * 64), RECORDED_THROUGH),
        )

    with pytest.raises(MigrationStateError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "ledger-checksum-mismatch"
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            """
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'ctower_schema_migrations'
              AND column_name = 'applied_server_version_num'
            """
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    ("case", "expected_code"),
    (
        ("wrong-recorded-digest", "ledger-schema-mismatch"),
        ("edited-recorded-raw-digest", "ledger-schema-mismatch"),
        ("wrong-cluster-checksum", "ledger-transition-declaration-mismatch"),
        ("wrong-pending-prefix", "ledger-schema-mismatch"),
        ("wrong-postgres-major", "ledger-schema-mismatch"),
        ("raw-digest-as-authority", "ledger-schema-mismatch"),
        ("extra-schema-object", "ledger-schema-mismatch"),
        ("extra-acl-record", "ledger-schema-mismatch"),
        ("missing-table-record", "ledger-schema-mismatch"),
        ("changed-constraint-record", "ledger-schema-mismatch"),
        ("changed-function-record", "ledger-schema-mismatch"),
        ("missing-trigger-record", "ledger-schema-mismatch"),
    ),
)
def test_unbound_transition_states_refuse_before_pending_database_ddl(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_code: str,
) -> None:
    _install_legacy_ledger_through_0063(migration_database, monkeypatch)
    provision_database_roles(migration_database.admin_dsn)
    loaded = _setup_sql._load_migrations()
    transition = _unbound_transition_case(
        migration_database,
        loaded.ledger_advance_transitions[0],
        case,
    )
    monkeypatch.setattr(
        _setup_sql,
        "_load_migrations",
        lambda: _setup_sql._LoadedMigrations(
            loaded.scripts,
            loaded.baseline,
            (transition,),
        ),
    )
    _assert_transition_refusal(migration_database, expected_code)


def _assert_transition_refusal(database: Database, expected_code: str) -> None:
    with pytest.raises(MigrationStateError) as raised:
        apply_migrations(
            database.migrator_dsn,
            role_admin_dsn=database.admin_dsn,
        )

    assert raised.value.code == expected_code
    with psycopg.connect(database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT max(migration_id) FROM ctower_schema_migrations"
        ).fetchone() == (RECORDED_THROUGH,)
        assert connection.execute(
            """
            SELECT to_regclass('public.console_view_grants'),
                   to_regclass('public.routine_retirements')
            """
        ).fetchone() == (None, None)


def test_fresh_ledger_rows_capture_database_server_version_without_caller_input(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        expected = connection.execute(
            "SELECT current_setting('server_version_num')::integer"
        ).fetchone()
        versions = connection.execute(
            "SELECT DISTINCT applied_server_version_num FROM ctower_schema_migrations"
        ).fetchall()
    assert expected is not None
    assert versions == [expected]

    with psycopg.connect(migration_database.migrator_dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("UPDATE ctower_schema_migrations SET applied_server_version_num = 1")


def test_0063_attestation_is_separated_between_postgres_16_and_17(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = {
        major: _attestation_on_image(image, major, monkeypatch)
        for image, major in (("postgres:16", 16), ("postgres:17-bookworm", 17))
    }

    assert results == {
        16: (POSTGRES_16_SCHEMA_SHA256, False),
        17: (RECORDED_SCHEMA_SHA256, True),
    }


def _unbound_transition_case(
    database: Database,
    transition: _migration_ledger_sql.MigrationAdvanceTransition,
    case: str,
) -> _migration_ledger_sql.MigrationAdvanceTransition:
    transition_mutations = {
        "wrong-cluster-checksum": _wrong_cluster_checksum,
        "wrong-pending-prefix": _wrong_pending_prefix,
        "wrong-postgres-major": _wrong_postgres_major,
        "raw-digest-as-authority": _raw_digest_authority,
    }
    mutation = transition_mutations.get(case)
    if mutation is not None:
        return mutation(transition)
    if case == "wrong-recorded-digest":
        _rewrite_recorded_digest(database, "sha256:" + ("0" * 64))
    if case == "edited-recorded-raw-digest":
        _rewrite_recorded_digest(database, FRESH_TRANSITION_RAW_SCHEMA_SHA256)
    if case in _SCHEMA_RECORD_MUTATIONS:
        with psycopg.connect(database.admin_dsn) as connection:
            connection.execute(_SCHEMA_RECORD_MUTATIONS[case])
    return transition


def _wrong_cluster_checksum(
    transition: _migration_ledger_sql.MigrationAdvanceTransition,
) -> _migration_ledger_sql.MigrationAdvanceTransition:
    return replace(transition, cluster_sha256="sha256:" + ("0" * 64))


def _wrong_pending_prefix(
    transition: _migration_ledger_sql.MigrationAdvanceTransition,
) -> _migration_ledger_sql.MigrationAdvanceTransition:
    return replace(
        transition,
        pending_database_from="0066_beat_routine_retirement.sql",
    )


def _wrong_postgres_major(
    transition: _migration_ledger_sql.MigrationAdvanceTransition,
) -> _migration_ledger_sql.MigrationAdvanceTransition:
    return replace(transition, postgres_major=16)


def _raw_digest_authority(
    transition: _migration_ledger_sql.MigrationAdvanceTransition,
) -> _migration_ledger_sql.MigrationAdvanceTransition:
    return replace(transition, result_schema_sha256=RESTORED_RAW_SCHEMA_SHA256)


_SCHEMA_RECORD_MUTATIONS = {
    "extra-schema-object": "CREATE TABLE transition_drift_probe (marker integer)",
    "extra-acl-record": "GRANT SELECT ON tenants TO postgres",
    "missing-table-record": "DROP TABLE routine_beat_dispatch_specs CASCADE",
    "changed-constraint-record": (
        "ALTER TABLE project_delivery_checkpoint_definitions "
        "DROP CONSTRAINT project_delivery_checkpoint_definitions_applicable_states_check"
    ),
    "changed-function-record": """
        CREATE OR REPLACE FUNCTION refuse_immutable_control_fact_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$
    """,
    "missing-trigger-record": (
        "DROP TRIGGER routine_beat_dispatch_specs_immutable ON routine_beat_dispatch_specs"
    ),
}


def _rewrite_recorded_digest(database: Database, digest: str) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("SET ROLE ctower_migration_ledger")
        connection.execute(
            """
            UPDATE ctower_schema_migrations
            SET result_schema_sha256 = %s
            WHERE migration_id = %s
            """,
            (digest, RECORDED_THROUGH),
        )


def _attestation_on_image(
    image: str,
    major: int,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, bool]:
    with _isolated_postgres_image(image) as admin_dsn:
        loaded = _setup_sql._load_migrations()
        stop = next(
            position
            for position, script in enumerate(loaded.scripts)
            if script.migration_id == RECORDED_THROUGH
        )
        baseline = MigrationBaseline(
            RECORDED_THROUGH,
            RECORDED_SCHEMA_SHA256,
            "ctower.pre-ledger/v1",
            RECORDED_OBJECT_SUM256,
        )
        with monkeypatch.context() as truncated:
            use_migrations(truncated, loaded.scripts[: stop + 1], baseline)
            _apply_or_refuse_attestation(admin_dsn, major)
        return _read_attestation_result(admin_dsn, major)


def _apply_or_refuse_attestation(admin_dsn: str, major: int) -> None:
    if major == POSTGRES_17_MAJOR:
        apply_migrations(admin_dsn, role_admin_dsn=admin_dsn)
        return
    with pytest.raises(MigrationStateError) as raised:
        apply_migrations(admin_dsn, role_admin_dsn=admin_dsn)
    assert raised.value.code == "ledger-attestation-mismatch"


def _read_attestation_result(admin_dsn: str, major: int) -> tuple[str, bool]:
    with psycopg.connect(admin_dsn) as connection:
        records = _migration_ledger_sql._schema_records(connection)
        fingerprint = _migration_ledger_sql._schema_fingerprint(records)
        ledger_exists = connection.execute(
            "SELECT to_regclass('public.ctower_schema_migrations') IS NOT NULL"
        ).fetchone()
        server_major = connection.execute(
            "SELECT current_setting('server_version_num')::integer / 10000"
        ).fetchone()
    assert server_major == (major,)
    assert ledger_exists is not None
    return fingerprint, bool(ledger_exists[0])


def _install_legacy_ledger_through_0063(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public AUTHORIZATION pg_database_owner")
        connection.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
        connection.execute("COMMENT ON SCHEMA public IS 'standard public schema'")
    loaded = _setup_sql._load_migrations()
    stop = next(
        position
        for position, script in enumerate(loaded.scripts)
        if script.migration_id == RECORDED_THROUGH
    )
    baseline = MigrationBaseline(
        RECORDED_THROUGH,
        RECORDED_SCHEMA_SHA256,
        "ctower.pre-ledger/v1",
        RECORDED_OBJECT_SUM256,
    )
    with monkeypatch.context() as truncated:
        use_migrations(truncated, loaded.scripts[: stop + 1], baseline)
        apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)
    # Recreate the exact five-column ledger shape deployed with 0063. New code
    # creates v4 directly, so the fixture removes only its new private column.
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("SET ROLE ctower_migration_ledger")
        connection.execute(
            "ALTER TABLE ctower_schema_migrations DROP COLUMN applied_server_version_num"
        )


def _legacy_ledger_rows(database: Database) -> list[tuple[str, str, str, str, datetime]]:
    with psycopg.connect(database.admin_dsn) as connection:
        return connection.execute(
            """
            SELECT migration_id, sha256, application_kind, result_schema_sha256, applied_at
            FROM ctower_schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()


def _versioned_ledger_rows(
    database: Database,
) -> list[tuple[str, str, str, str, datetime, int | None]]:
    with psycopg.connect(database.admin_dsn) as connection:
        return connection.execute(
            """
            SELECT migration_id, sha256, application_kind, result_schema_sha256, applied_at,
                   applied_server_version_num
            FROM ctower_schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()


def _fingerprints(database: Database) -> tuple[str, str]:
    with psycopg.connect(database.admin_dsn) as connection:
        canonical = _migration_ledger_sql._schema_fingerprint(
            _migration_ledger_sql._schema_records(connection, canonical=True)
        )
        raw = _migration_ledger_sql._schema_fingerprint(
            _migration_ledger_sql._schema_records(connection, canonical=False)
        )
    return canonical, raw


def _dump_and_restore_with_postgres_17(database: Database) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is required for PostgreSQL migration tests")
    dump = _run_command(
        docker,
        "run",
        "--rm",
        "--network",
        "host",
        "postgres:17-bookworm",
        "pg_dump",
        "--format=custom",
        database.admin_dsn,
    )
    _run_command(
        docker,
        "run",
        "--rm",
        "--interactive",
        "--network",
        "host",
        "postgres:17-bookworm",
        "pg_restore",
        "--clean",
        "--if-exists",
        "--exit-on-error",
        "--dbname",
        database.admin_dsn,
        input_bytes=dump,
    )


@contextmanager
def _isolated_postgres_image(image: str) -> Iterator[str]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is required for PostgreSQL migration tests")
    name = f"ctower-pg-major-{uuid4().hex[:12]}"
    port = _postgres._available_port()
    _run_command(
        docker,
        "run",
        "--detach",
        "--rm",
        "--name",
        name,
        "--publish",
        f"127.0.0.1:{port}:5432",
        "--env",
        "POSTGRES_DB=ctower",
        "--env",
        "POSTGRES_HOST_AUTH_METHOD=trust",
        "--env",
        "POSTGRES_USER=postgres",
        image,
    )
    admin_dsn = f"postgresql://postgres@127.0.0.1:{port}/ctower"
    try:
        _postgres._wait_for_postgres(admin_dsn)
        yield admin_dsn
    finally:
        _run_command(docker, "stop", name, check=False)


def _run_command(
    *command: str,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> bytes:
    return asyncio.run(_run_command_async(*command, input_bytes=input_bytes, check=check))


async def _run_command_async(
    *command: str,
    input_bytes: bytes | None,
    check: bool,
) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate(input_bytes)
    if check and process.returncode != 0:
        raise RuntimeError(f"command failed with status {process.returncode}")
    return stdout


def _object_sum256(records: tuple[tuple[str, str, str], ...]) -> str:
    return f"sum256:{_migration_ledger_sql._schema_object_sum(records):064x}"


def _acl_delta(
    before: tuple[tuple[str, str, str], ...],
    after: tuple[tuple[str, str, str], ...],
) -> tuple[tuple[str, str, dict[str, object]], ...]:
    removed = sorted(set(before) - set(after))
    added = sorted(set(after) - set(before))
    assert all(record[0] == "acl" for record in (*removed, *added))
    return tuple(
        (change, identity, json.loads(value))
        for change, records in (("removed", removed), ("added", added))
        for _, identity, value in records
    )
