"""Byte-consistent checkpoint and restore proof on one disposable PostgreSQL instance."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

import tools.development_runtime.checkpoint as checkpoint  # noqa: PLR0402
from ctower_api.development_config import DevelopmentConfig
from development_runtime._disposable_instance import DisposableInstance
from tools.development_runtime.checkpoint_ledger import artifact_path
from tools.development_runtime.host_commands import docker_path

__all__: tuple[str, ...] = ()

_IMAGE = "postgres@sha256:4f736ae292687621d4dbe0d499ffd024a36bd2ee7d8ca6f2ccd4c800f047b394"
_ARTIFACT_KEY = "disposable-development-checkpoint-key"
# A fixed psql restrict key makes two dumps of identical content byte-comparable. The
# captured artifact keeps pg_dump's random key, so this never relaxes the product path.
_RESTRICT_KEY = "ctowerCheckpointRoundTripProof"
_DUMP_TIMEOUT_SECONDS = 120.0
_ARTIFACT_MODE = 0o400
_ADMIN_REF = "secret-service:ctower-development/postgres-admin"


def test_checkpoint_then_mutation_then_restore_recovers_byte_consistent_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    disposable_instance: DisposableInstance,
) -> None:
    """Restore returns every data byte, every relation, and the recorded generation."""

    instance = disposable_instance
    _bind_checkpoint_verbs(monkeypatch, tmp_path, instance)
    _insert_tenant(instance, "kept-before-checkpoint")

    record = checkpoint.create_checkpoint()
    captured_data = _dump(instance, data_only=True)
    captured_relations = _relations(instance)
    # PostgreSQL re-parses CHECK expressions when it recreates them, so a schema dump
    # taken before any restore differs from every later one by parenthesisation alone.
    # The whole-database comparison therefore uses the first restore as its baseline,
    # while the data comparison stays against the true pre-checkpoint bytes.
    checkpoint.restore_checkpoint(record.checkpoint_id)
    captured_database = _dump(instance)
    assert _dump(instance, data_only=True) == captured_data

    discarded = _insert_tenant(instance, "written-after-checkpoint")
    _execute(instance, "CREATE TABLE stray_after_checkpoint (value text)")
    _execute(instance, "DELETE FROM tenants WHERE slug = 'kept-before-checkpoint'")
    assert _dump(instance, data_only=True) != captured_data

    restored = checkpoint.restore_checkpoint(record.checkpoint_id)

    assert restored.checkpoint_id == record.checkpoint_id
    assert _dump(instance) == captured_database
    assert _dump(instance, data_only=True) == captured_data
    assert _relations(instance) == captured_relations
    assert _tenant_slugs(instance) == ("kept-before-checkpoint",)
    assert discarded not in _tenant_ids(instance)
    assert _terminal_generation(instance) == record.generation


def test_checkpoint_artifact_is_encrypted_and_bound_to_the_serving_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    disposable_instance: DisposableInstance,
) -> None:
    """The retained artifact is unreadable ciphertext the ledger addresses by digest."""

    _bind_checkpoint_verbs(monkeypatch, tmp_path, disposable_instance)

    record = checkpoint.create_checkpoint()

    artifact = artifact_path(record.checkpoint_id)
    payload = artifact.read_bytes()
    assert artifact.stat().st_mode & 0o777 == _ARTIFACT_MODE
    assert record.artifact_bytes == len(payload)
    assert b"CREATE TABLE" not in payload
    assert b"tenants" not in payload
    assert record.checkpoint_id.endswith(record.artifact_sha256.removeprefix("sha256:"))
    assert record.generation == _terminal_generation(disposable_instance)
    assert record.passphrase_ref == _ADMIN_REF
    assert checkpoint.list_checkpoints() == (record,)


def _bind_checkpoint_verbs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    instance: DisposableInstance,
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(checkpoint, "_PRIMARY_CONTAINER", instance.container)
    monkeypatch.setattr(checkpoint, "load_config", _config)
    monkeypatch.setattr(checkpoint, "load_secret", lambda _reference: _ARTIFACT_KEY)
    monkeypatch.setattr(
        checkpoint,
        "development_dsn",
        lambda _config, _role, **_options: instance.admin_dsn,
    )
    monkeypatch.setattr(checkpoint, "unit_state", lambda _name: "inactive")


def _config() -> DevelopmentConfig:
    return DevelopmentConfig.model_validate(
        {
            "schema": "ctower.development-runtime/v1",
            "label": "SHADOW_ONLY_CP3_D_NOT_PROVEN",
            "api_host": "127.0.0.1",
            "api_port": 8091,
            "database_host": "127.0.0.1",
            "database_name": "ctower",
            "primary_port": 55432,
            "standby_port": 55433,
            "postgres_image": _IMAGE,
            "postgres_admin_secret_ref": _ADMIN_REF,
            "migrator_secret_ref": "secret-service:ctower-development/migrator",
            "runtime_secret_ref": "secret-service:ctower-development/runtime",
            "projection_secret_ref": "secret-service:ctower-development/projection",
            "operator_secret_ref": "secret-service:ctower-development/operator",
            "commander_secret_ref": "secret-service:ctower-development/commander",
        }
    )


def _dump(instance: DisposableInstance, *, data_only: bool = False) -> bytes:
    selection = ["--data-only"] if data_only else ["--create", "--clean", "--if-exists"]
    result = subprocess.run(  # noqa: S603 - fixture-owned container and resolved binary
        [
            docker_path(),
            "exec",
            "--user",
            "postgres",
            instance.container,
            "pg_dump",
            *selection,
            "--quote-all-identifiers",
            f"--restrict-key={_RESTRICT_KEY}",
            "--dbname",
            "ctower",
        ],
        check=True,
        capture_output=True,
        timeout=_DUMP_TIMEOUT_SECONDS,
    )
    return result.stdout


def _insert_tenant(instance: DisposableInstance, slug: str) -> str:
    tenant_id = uuid4()
    _execute(
        instance,
        "INSERT INTO tenants (tenant_id, slug, name, created_at) VALUES (%s, %s, %s, %s)",
        (tenant_id, slug, slug, datetime.now(UTC)),
    )
    return str(tenant_id)


def _execute(
    instance: DisposableInstance,
    statement: str,
    parameters: tuple[object, ...] = (),
) -> None:
    with psycopg.connect(instance.admin_dsn, autocommit=True) as connection:
        connection.execute(statement, parameters)


def _query(instance: DisposableInstance, statement: str) -> tuple[str, ...]:
    with psycopg.connect(instance.admin_dsn) as connection:
        rows = connection.execute(statement).fetchall()
    return tuple(str(row[0]) for row in rows)


def _tenant_slugs(instance: DisposableInstance) -> tuple[str, ...]:
    return _query(instance, "SELECT slug FROM tenants ORDER BY slug")


def _tenant_ids(instance: DisposableInstance) -> tuple[str, ...]:
    return _query(instance, "SELECT tenant_id FROM tenants")


def _relations(instance: DisposableInstance) -> tuple[str, ...]:
    return _query(
        instance,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
    )


def _terminal_generation(instance: DisposableInstance) -> str:
    generations = _query(
        instance,
        """
        SELECT result_schema_sha256 FROM ctower_schema_migrations
        ORDER BY migration_id DESC LIMIT 1
        """,
    )
    assert len(generations) == 1
    return generations[0]
