"""Fault tests for the public fixed backup composition."""

from __future__ import annotations

import hashlib
import os
import shlex
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

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
    backup_id = uuid4()
    pgbackrest = _evidence_tool(tmp_path / "pgbackrest", tmp_path, backup_id)
    pg_dump = _logical_dump_tool(tmp_path / "pg_dump")
    config = _config(tmp_path, pgbackrest, pg_dump)

    manifest = LocalBackup(config).run_daily(uuid4(), backup_id, key_version="v1")

    assert manifest.repository_object_version == "version-1"
    assert manifest.base_backup_sha256 == _digest(config.base_manifest_path)
    assert manifest.verification.model_dump() == {
        "base": True,
        "wal": True,
        "logical_dump": True,
        "objects": True,
        "key_reference": True,
    }


def test_noop_tools_cannot_adopt_stale_evidence(tmp_path: Path) -> None:
    pgbackrest = _successful_tool(tmp_path / "pgbackrest")
    pg_dump = _successful_tool(tmp_path / "pg_dump")
    config = _config(tmp_path, pgbackrest, pg_dump)
    backup_id = uuid4()
    config.base_manifest_path.write_bytes(b"base")
    config.logical_dump_path.write_bytes(b"logical")
    config.object_manifest_path.write_bytes(b"objects")
    config.migration_manifest_path.write_bytes(b"migrations")
    config.wal_manifest_path.write_text(
        json_wal(backup_id),
        encoding="utf-8",
    )

    with pytest.raises(BackupError, match="not produced by this run"):
        LocalBackup(config).run_daily(uuid4(), backup_id, key_version="v1")


def test_timed_out_backup_process_group_is_killed_and_reaped(tmp_path: Path) -> None:
    pid_path = tmp_path / "backup.pid"
    pgbackrest = _successful_tool(
        tmp_path / "pgbackrest",
        f"printf '%s' \"$$\" > {shlex.quote(str(pid_path))}\nsleep 30",
    )
    pg_dump = _successful_tool(tmp_path / "pg_dump")
    config = _config(tmp_path, pgbackrest, pg_dump).model_copy(update={"timeout_seconds": 1})

    with pytest.raises(BackupError, match="timed out and was reaped"):
        LocalBackup(config).run_daily(uuid4(), uuid4(), key_version="v1")

    process_id = int(pid_path.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(process_id, 0)


def test_backup_config_rejects_untrusted_checksum_and_relative_path(tmp_path: Path) -> None:
    pgbackrest = _successful_tool(tmp_path / "pgbackrest")
    pg_dump = _successful_tool(tmp_path / "pg_dump")
    payload = _config(tmp_path, pgbackrest, pg_dump).model_dump(mode="python")
    payload["pgbackrest_sha256"] = "not-a-digest"
    with pytest.raises(ValidationError, match="tool checksum"):
        BackupAdapterConfig.model_validate(payload)
    payload["pgbackrest_sha256"] = _digest(pgbackrest)
    payload["logical_dump_path"] = Path("relative.dump")
    with pytest.raises(ValidationError, match="absolute"):
        BackupAdapterConfig.model_validate(payload)


def test_tool_checksum_and_nonzero_exit_fail_closed(tmp_path: Path) -> None:
    pgbackrest = _successful_tool(tmp_path / "pgbackrest")
    pg_dump = _successful_tool(tmp_path / "pg_dump")
    config = _config(tmp_path, pgbackrest, pg_dump)
    mismatched = config.model_copy(update={"pgbackrest_sha256": "sha256:" + "0" * 64})
    with pytest.raises(BackupError, match="checksum mismatch"):
        LocalBackup(mismatched).run_daily(uuid4(), uuid4(), key_version="v1")

    failed = _successful_tool(tmp_path / "failed-pgbackrest", "exit 7")
    with pytest.raises(BackupError, match="exit code 7"):
        LocalBackup(_config(tmp_path, failed, pg_dump)).run_daily(
            uuid4(),
            uuid4(),
            key_version="v1",
        )


@pytest.mark.parametrize(
    ("kind", "match"),
    [
        ("malformed", "malformed"),
        ("wrong_run", "another run"),
        ("regressed", "regressed"),
        ("invalid_lsn", "malformed"),
    ],
)
def test_wal_evidence_faults_fail_closed(
    tmp_path: Path,
    kind: str,
    match: str,
) -> None:
    backup_id = uuid4()
    payload = _faulty_wal(kind, backup_id)
    pgbackrest = _evidence_tool(
        tmp_path / "pgbackrest",
        tmp_path,
        backup_id,
        wal_payload=payload,
    )
    pg_dump = _logical_dump_tool(tmp_path / "pg_dump")

    with pytest.raises(BackupError, match=match):
        LocalBackup(_config(tmp_path, pgbackrest, pg_dump)).run_daily(
            uuid4(),
            backup_id,
            key_version="v1",
        )


def test_backup_command_output_is_bounded_at_the_source(tmp_path: Path) -> None:
    backup_id = uuid4()
    body = _evidence_body(tmp_path, json_wal(backup_id))
    pgbackrest = _successful_tool(
        tmp_path / "pgbackrest",
        f"{body}\nhead -c 10000 /dev/zero",
    )
    pg_dump = _logical_dump_tool(tmp_path / "pg_dump")

    manifest = LocalBackup(_config(tmp_path, pgbackrest, pg_dump)).run_daily(
        uuid4(),
        backup_id,
        key_version="v1",
    )

    assert manifest.backup_id == backup_id


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


def _successful_tool(path: Path, body: str = "") -> Path:
    path.write_text(f"#!/bin/sh\n{body}\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path.resolve()


def _evidence_tool(
    path: Path,
    root: Path,
    backup_id: object,
    *,
    wal_payload: str | None = None,
) -> Path:
    return _successful_tool(
        path,
        _evidence_body(root, wal_payload or json_wal(backup_id)),
    )


def _evidence_body(root: Path, wal_payload: str) -> str:
    body = "\n".join(
        (
            f"printf base > {shlex.quote(str(root / 'base.manifest'))}",
            f"printf objects > {shlex.quote(str(root / 'objects.manifest'))}",
            f"printf migrations > {shlex.quote(str(root / 'migrations.manifest'))}",
            f"printf %s {shlex.quote(wal_payload)} > {shlex.quote(str(root / 'wal.manifest'))}",
        )
    )
    return body


def _logical_dump_tool(path: Path) -> Path:
    return _successful_tool(
        path,
        'for argument in "$@"; do\n'
        '  case "$argument" in --file=*) printf logical > "${argument#--file=}";; esac\n'
        "done",
    )


def json_wal(backup_id: object) -> str:
    return (
        '{"backup_id":"'
        f'{backup_id}","repository_object_version":"version-1",'
        '"wal_start_lsn":"0/10","wal_stop_lsn":"0/20"}'
    )


def _faulty_wal(kind: str, backup_id: object) -> str:
    if kind == "malformed":
        return "not-json"
    if kind == "wrong_run":
        return json_wal(uuid4())
    if kind == "regressed":
        return json_wal(backup_id).replace('"0/20"', '"0/01"')
    return json_wal(backup_id).replace('"0/10"', '"invalid"')


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
