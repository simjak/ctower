"""Checksum-pinned fixed pgBackRest and pg_dump Adapter."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import signal
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

__all__: tuple[str, ...] = ()

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_LSN = re.compile(r"^[0-9A-F]+/[0-9A-F]+$")
_OUTPUT_LIMIT = 4_000
type _FileFingerprint = tuple[int, int, int, str]


class BackupError(RuntimeError):
    """A fixed backup invocation lacked complete verified evidence."""


class BackupAdapterConfig(BaseModel):
    """Secret-free fixed tool and output references."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pgbackrest_path: Path
    pgbackrest_sha256: str
    pg_dump_path: Path
    pg_dump_sha256: str
    pgbackrest_config_path: Path
    stanza: str
    database_service: str
    repository_ref: str
    key_reference: str
    logical_dump_path: Path
    base_manifest_path: Path
    wal_manifest_path: Path
    object_manifest_path: Path
    migration_manifest_path: Path
    timeout_seconds: int = 7200

    @field_validator("pgbackrest_sha256", "pg_dump_sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("tool checksum must be lowercase SHA-256")
        return value

    @field_validator(
        "pgbackrest_path",
        "pg_dump_path",
        "pgbackrest_config_path",
        "logical_dump_path",
        "base_manifest_path",
        "wal_manifest_path",
        "object_manifest_path",
        "migration_manifest_path",
    )
    @classmethod
    def _absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("backup paths must be absolute")
        return value


class CommandResult(BaseModel):
    """Bounded output from one fixed argv execution."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    returncode: int
    stdout: str
    stderr: str


class BackupManifest(BaseModel):
    """Complete local evidence required before recording backup success."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_id: Literal["ctower.backup-manifest/v1"] = "ctower.backup-manifest/v1"
    backup_id: UUID
    tenant_id: UUID
    repository_ref: str
    repository_object_version: str
    base_backup_sha256: str
    wal_start_lsn: str
    wal_stop_lsn: str
    logical_dump_sha256: str
    object_manifest_sha256: str
    migration_manifest_sha256: str
    key_reference: str
    key_version: str
    started_at: datetime
    completed_at: datetime
    verification: BackupVerification


class BackupVerification(BaseModel):
    """Every independent success fact required for a usable backup."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    base: Literal[True]
    wal: Literal[True]
    logical_dump: Literal[True]
    objects: Literal[True]
    key_reference: Literal[True]


class _Runner(Protocol):
    def __call__(self, argv: Sequence[str], *, timeout: int) -> CommandResult: ...


class FixedBackupAdapter:
    """Execute only the authored backup sequence; no caller supplies a command."""

    def __init__(
        self,
        config: BackupAdapterConfig,
        *,
        runner: _Runner | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._runner = runner or _run
        self._clock = clock or (lambda: datetime.now(UTC))

    def run_daily(
        self,
        tenant_id: UUID,
        backup_id: UUID,
        *,
        key_version: str,
    ) -> BackupManifest:
        """Run physical and logical backup steps and require all evidence."""

        self._verify_tools()
        started_at = self._clock()
        before = _evidence_fingerprints(self._config)
        self._execute(
            (
                str(self._config.pgbackrest_path),
                f"--config={self._config.pgbackrest_config_path}",
                f"--stanza={self._config.stanza}",
                "--type=full",
                f"--annotation=ctower-backup-id={backup_id}",
                "backup",
            )
        )
        self._execute(
            (
                str(self._config.pg_dump_path),
                "--format=custom",
                "--no-password",
                f"--dbname=service={self._config.database_service}",
                f"--file={self._config.logical_dump_path}",
            )
        )
        evidence = _read_evidence(self._config, backup_id=backup_id, before=before)
        completed_at = self._clock()
        return BackupManifest(
            backup_id=backup_id,
            tenant_id=tenant_id,
            repository_ref=self._config.repository_ref,
            repository_object_version=evidence.repository_object_version,
            base_backup_sha256=_file_digest(self._config.base_manifest_path),
            wal_start_lsn=evidence.wal_start_lsn,
            wal_stop_lsn=evidence.wal_stop_lsn,
            logical_dump_sha256=_file_digest(self._config.logical_dump_path),
            object_manifest_sha256=_file_digest(self._config.object_manifest_path),
            migration_manifest_sha256=_file_digest(self._config.migration_manifest_path),
            key_reference=self._config.key_reference,
            key_version=key_version,
            started_at=started_at,
            completed_at=completed_at,
            verification=BackupVerification(
                base=True,
                wal=True,
                logical_dump=True,
                objects=True,
                key_reference=True,
            ),
        )

    def _verify_tools(self) -> None:
        for path, expected in (
            (self._config.pgbackrest_path, self._config.pgbackrest_sha256),
            (self._config.pg_dump_path, self._config.pg_dump_sha256),
        ):
            if not path.is_file() or _file_digest(path) != expected:
                raise BackupError(f"backup tool checksum mismatch: {path.name}")

    def _execute(self, argv: Sequence[str]) -> None:
        result = self._runner(argv, timeout=self._config.timeout_seconds)
        if result.returncode != 0:
            raise BackupError(f"fixed backup command failed with exit code {result.returncode}")


class _WalEvidence(BaseModel):
    """Strict evidence emitted beside checksum-addressed backup outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    backup_id: UUID
    repository_object_version: str
    wal_start_lsn: str
    wal_stop_lsn: str

    @field_validator("wal_start_lsn", "wal_stop_lsn")
    @classmethod
    def _lsn(cls, value: str) -> str:
        if _LSN.fullmatch(value) is None:
            raise ValueError("backup WAL evidence must use canonical PostgreSQL LSN")
        return value


def _read_evidence(
    config: BackupAdapterConfig,
    *,
    backup_id: UUID,
    before: dict[Path, _FileFingerprint | None],
) -> _WalEvidence:
    for path in _evidence_paths(config):
        if not path.is_file() or path.stat().st_size == 0:
            raise BackupError(f"backup evidence is missing or empty: {path.name}")
        if _file_fingerprint(path) == before[path]:
            raise BackupError(f"backup evidence was not produced by this run: {path.name}")
    try:
        evidence = _WalEvidence.model_validate_json(
            config.wal_manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise BackupError("backup WAL evidence is malformed") from error
    if evidence.backup_id != backup_id:
        raise BackupError("backup WAL evidence belongs to another run")
    if _lsn_value(evidence.wal_stop_lsn) < _lsn_value(evidence.wal_start_lsn):
        raise BackupError("backup WAL evidence regressed")
    return evidence


def _run(argv: Sequence[str], *, timeout: int) -> CommandResult:
    return asyncio.run(_run_async(argv, deadline_seconds=timeout))


async def _run_async(argv: Sequence[str], *, deadline_seconds: int) -> CommandResult:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:
        raise BackupError("backup command output pipes are unavailable")
    stdout_task = asyncio.create_task(_read_tail(process.stdout))
    stderr_task = asyncio.create_task(_read_tail(process.stderr))
    try:
        await asyncio.wait_for(process.wait(), timeout=deadline_seconds)
    except TimeoutError as error:
        await _terminate_and_reap(process)
        raise BackupError("fixed backup command timed out and was reaped") from error
    finally:
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
    return CommandResult(
        returncode=process.returncode or 0,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


async def _read_tail(stream: asyncio.StreamReader) -> bytes:
    tail = bytearray()
    while chunk := await stream.read(4096):
        tail.extend(chunk)
        if len(tail) > _OUTPUT_LIMIT:
            del tail[:-_OUTPUT_LIMIT]
    return bytes(tail)


async def _terminate_and_reap(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        await process.wait()
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
    else:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)


def _evidence_paths(config: BackupAdapterConfig) -> tuple[Path, ...]:
    return (
        config.base_manifest_path,
        config.wal_manifest_path,
        config.logical_dump_path,
        config.object_manifest_path,
        config.migration_manifest_path,
    )


def _evidence_fingerprints(
    config: BackupAdapterConfig,
) -> dict[Path, _FileFingerprint | None]:
    return {
        path: _file_fingerprint(path) if path.is_file() else None
        for path in _evidence_paths(config)
    }


def _file_fingerprint(path: Path) -> _FileFingerprint:
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, _file_digest(path))


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _lsn_value(value: str) -> int:
    high, low = value.split("/")
    return (int(high, 16) << 32) + int(low, 16)
