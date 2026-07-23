"""Fault tests for the public fixed backup composition."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from ctower_api.backup import BackupAdapterConfig, BackupError, LocalBackup

__all__: tuple[str, ...] = ()


def test_zero_exit_without_complete_evidence_is_not_a_backup(tmp_path: Path) -> None:
    pgbackrest = _successful_tool(tmp_path / "pgbackrest")
    pg_dump = _successful_tool(tmp_path / "pg_dump")
    config = _config(tmp_path, pgbackrest, pg_dump)

    with pytest.raises(BackupError, match="missing or empty"):
        LocalBackup(config).run_daily(uuid4(), uuid4(), key_version="v1")


def test_complete_fixed_backup_evidence_produces_verified_manifest(
    tmp_path: Path,
) -> None:
    pgbackrest = _successful_tool(tmp_path / "pgbackrest")
    pg_dump = _successful_tool(tmp_path / "pg_dump")
    config = _config(tmp_path, pgbackrest, pg_dump)
    config.base_manifest_path.write_bytes(b"base")
    config.logical_dump_path.write_bytes(b"logical")
    config.object_manifest_path.write_bytes(b"objects")
    config.migration_manifest_path.write_bytes(b"migrations")
    config.wal_manifest_path.write_text(
        '{"repository_object_version":"version-1","wal_start_lsn":"0/10","wal_stop_lsn":"0/20"}',
        encoding="utf-8",
    )

    manifest = LocalBackup(config).run_daily(uuid4(), uuid4(), key_version="v1")

    assert manifest.repository_object_version == "version-1"
    assert manifest.base_backup_sha256 == _digest(config.base_manifest_path)
    assert manifest.verification.model_dump() == {
        "base": True,
        "wal": True,
        "logical_dump": True,
        "objects": True,
        "key_reference": True,
    }


def _config(
    tmp_path: Path,
    pgbackrest: Path,
    pg_dump: Path,
) -> BackupAdapterConfig:
    return BackupAdapterConfig(
        pgbackrest_path=pgbackrest,
        pgbackrest_sha256=_digest(pgbackrest),
        pg_dump_path=pg_dump,
        pg_dump_sha256=_digest(pg_dump),
        pgbackrest_config_path=(tmp_path / "pgbackrest.conf").resolve(),
        stanza="ctower",
        database_service="ctower-backup",
        repository_ref="backup-ref:test/repository",
        key_reference="kms-ref:test/backup",
        logical_dump_path=(tmp_path / "logical.dump").resolve(),
        base_manifest_path=(tmp_path / "base.manifest").resolve(),
        wal_manifest_path=(tmp_path / "wal.manifest").resolve(),
        object_manifest_path=(tmp_path / "objects.manifest").resolve(),
        migration_manifest_path=(tmp_path / "migrations.manifest").resolve(),
    )


def _successful_tool(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path.resolve()


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
