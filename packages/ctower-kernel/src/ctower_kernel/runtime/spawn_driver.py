"""AC-SPWN-02/03/04 driver-side spawn custody: spool, import derivation, parity.

The spawn driver (codex-crew under ctower custody, R2982/R3000) needs three
things beside the record API:

- a mode-0600 pending-durability spool so a spawn is never silently unrecorded
  when ctower is unreachable (AC-SPWN-02);
- pure derivation of the initial running set from external spawn history by
  source identity with latest-status-effective semantics (AC-SPWN-03);
- the reconcile-source discipline: the external registry twin remains the
  reconcile input until one RECORDED parity proof exists; the swap is a
  separately admitted act (AC-SPWN-04).
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.runtime._spawn_record_types import (
    SpawnRecordCreate,
    SpawnRecordGet,
    SpawnRecordProblem,
)

__all__ = [
    "SpawnDriveContext",
    "SpawnDriveResult",
    "SpawnDurabilityState",
    "SpawnHistoryParityReport",
    "SpawnParityProof",
    "SpawnSpool",
    "SpawnSpoolEntry",
    "SpawnSpoolRefusalError",
    "build_parity_proof",
    "derive_initial_running_set",
    "history_parity_report",
    "latest_status_effective",
    "reconcile_source",
    "record_before_drive",
    "record_parity_proof",
    "replay_spool",
]

_SPOOL_MODE = 0o600
_SPOOL_FILENAME = "spawn-spool.jsonl"
_PENDING = "durability_pending"
_ACKED = "acked"
_TEMPORARY_FAILURE_STATUS = 500

# Terminal statuses in the external crew-log vocabulary.
_TERMINAL_SOURCE_STATUSES = frozenset(
    {
        "blocked",
        "closed",
        "completed",
        "done",
        "failed",
        "idle",
        "reaped",
        "retired",
    }
)


class SpawnDurabilityState(StrEnum):
    """Whether the pre-dispatch spawn fact has durable ctower custody."""

    RECORDED = "recorded"
    DURABILITY_PENDING = "durability_pending"
    REFUSED = "refused"


class SpawnSpoolRefusalError(ValueError):
    """A local spool refused to persist a prohibited caller-authored value."""

    code = "prohibited-data-class"

    def __init__(self) -> None:
        super().__init__("spawn spool refused prohibited data")


@dataclass(frozen=True, slots=True)
class SpawnDriveContext:
    """The custody result passed to the host-session driver."""

    command: SpawnRecordCreate
    record: SpawnRecordGet | None
    durability_state: SpawnDurabilityState
    spool_entry_id: UUID | None


@dataclass(frozen=True, slots=True)
class SpawnDriveResult:
    """The explicit custody state returned after record-before-drive."""

    context: SpawnDriveContext
    problem: SpawnRecordProblem | None


@dataclass(frozen=True, slots=True)
class SpawnParityProof:
    """A candidate or recorded equality proof for the external reconcile twin."""

    proof_id: UUID
    window: str
    external_digest: str
    ctower_digest: str
    external_count: int
    ctower_count: int
    recorded_at: datetime | None = None

    @property
    def parity_ok(self) -> bool:
        return (
            self.external_count == self.ctower_count and self.external_digest == self.ctower_digest
        )

    @property
    def is_recorded(self) -> bool:
        return self.recorded_at is not None

    def response_payload(self) -> dict[str, object]:
        return {
            "proof_id": str(self.proof_id),
            "window": self.window,
            "external_digest": self.external_digest,
            "ctower_digest": self.ctower_digest,
            "external_count": self.external_count,
            "ctower_count": self.ctower_count,
            "parity_ok": self.parity_ok,
            "recorded_at": None if self.recorded_at is None else self.recorded_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class SpawnHistoryParityReport:
    """Parity evidence for an external spawn-history import."""

    source_row_count: int
    distinct_source_count: int
    duplicate_source_row_count: int
    imported_record_count: int
    duplicate_imported_record_count: int
    missing_source_ids: tuple[UUID, ...]
    unexpected_source_ids: tuple[UUID, ...]
    latest_statuses: tuple[tuple[UUID, str], ...]
    initial_running_ids: tuple[UUID, ...]

    @property
    def parity_ok(self) -> bool:
        return (
            self.duplicate_imported_record_count == 0
            and not self.missing_source_ids
            and not self.unexpected_source_ids
        )

    def response_payload(self) -> dict[str, object]:
        return {
            "source_row_count": self.source_row_count,
            "distinct_source_count": self.distinct_source_count,
            "duplicate_source_row_count": self.duplicate_source_row_count,
            "imported_record_count": self.imported_record_count,
            "duplicate_imported_record_count": self.duplicate_imported_record_count,
            "missing_source_ids": [str(item) for item in self.missing_source_ids],
            "unexpected_source_ids": [str(item) for item in self.unexpected_source_ids],
            "latest_statuses": [
                {"source_id": str(source_id), "status": status}
                for source_id, status in self.latest_statuses
            ],
            "initial_running_ids": [str(item) for item in self.initial_running_ids],
            "parity_ok": self.parity_ok,
        }


def _ensure_spool_command_safe(command: SpawnRecordCreate) -> None:
    refusal = prohibited_data_refusal(
        [
            command.project_key,
            command.seat_key,
            command.crew_name,
            command.task_file_ref,
            command.worktree_path,
            command.harness,
            command.model,
            command.effort,
        ],
        command_id=command.client_command_id,
    )
    if refusal is not None:
        raise SpawnSpoolRefusalError


@dataclass(frozen=True, slots=True)
class SpawnSpoolEntry:
    """One spooled spawn fact awaiting durable recording in ctower."""

    entry_id: UUID
    command: SpawnRecordCreate
    state: str

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> SpawnSpoolEntry:
        command = payload["command"]
        workspace_id = command.get("workspace_id")
        return cls(
            entry_id=UUID(str(payload["entry_id"])),
            command=SpawnRecordCreate(
                client_command_id=UUID(str(command["client_command_id"])),
                project_key=str(command["project_key"]),
                seat_key=str(command["seat_key"]),
                crew_name=str(command["crew_name"]),
                task_file_ref=str(command["task_file_ref"]),
                worktree_path=str(command["worktree_path"]),
                harness=str(command["harness"]),
                model=str(command["model"]),
                effort=None if command.get("effort") is None else str(command["effort"]),
                workspace_id=None if workspace_id is None else UUID(str(workspace_id)),
            ),
            state=str(payload["state"]),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "entry_id": str(self.entry_id),
            "command": {
                "client_command_id": str(self.command.client_command_id),
                "project_key": self.command.project_key,
                "seat_key": self.command.seat_key,
                "crew_name": self.command.crew_name,
                "task_file_ref": self.command.task_file_ref,
                "worktree_path": self.command.worktree_path,
                "harness": self.command.harness,
                "model": self.command.model,
                "effort": self.command.effort,
                "workspace_id": (
                    None if self.command.workspace_id is None else str(self.command.workspace_id)
                ),
            },
            "state": self.state,
        }


class SpawnSpool:
    """One mode-0600 local JSONL spool of pending-durability spawn facts.

    The driver appends the IDENTICAL fact it tried to record in ctower, surfaces
    ``durability_pending`` explicitly, and removes entries only after ctower
    acknowledged the replayed create.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, command: SpawnRecordCreate) -> SpawnSpoolEntry:
        """Append one pending fact; create the file 0600 on first write."""

        _ensure_spool_command_safe(command)
        entry = SpawnSpoolEntry(entry_id=uuid4(), command=command, state=_PENDING)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self._path, flags, _SPOOL_MODE)
        owned_descriptor = True
        try:
            os.fchmod(descriptor, _SPOOL_MODE)
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                owned_descriptor = False
                handle.write(json.dumps(entry.to_mapping()) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if owned_descriptor:
                os.close(descriptor)
        return entry

    def pending(self) -> tuple[SpawnSpoolEntry, ...]:
        """Surface every pending entry in append order."""

        return tuple(entry for entry in self._read_all() if entry.state == _PENDING)

    def remove_acked(self, entry_ids: list[UUID] | tuple[UUID, ...]) -> int:
        """Remove exactly the acknowledged entries; pending ones stay."""

        acked = set(entry_ids)
        entries = self._read_all()
        kept = [entry for entry in entries if entry.entry_id not in acked]
        removed = len(entries) - len(kept)
        if removed:
            self._rewrite(kept)
        return removed

    def _read_all(self) -> list[SpawnSpoolEntry]:
        try:
            mode = self._path.stat(follow_symlinks=False).st_mode
        except FileNotFoundError:
            return []
        if not stat.S_ISREG(mode):
            raise OSError(f"spawn spool is not a regular file: {self._path}")
        if stat.S_IMODE(mode) != _SPOOL_MODE:
            raise OSError(f"spawn spool must have mode 0600: {self._path}")
        with self._path.open(encoding="utf-8") as handle:
            return [
                SpawnSpoolEntry.from_mapping(json.loads(line)) for line in handle if line.strip()
            ]

    def _rewrite(self, entries: list[SpawnSpoolEntry]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent
        )
        temporary = Path(temporary_name)
        owned_descriptor = True
        try:
            os.fchmod(descriptor, _SPOOL_MODE)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                owned_descriptor = False
                handle.writelines(json.dumps(entry.to_mapping()) + "\n" for entry in entries)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self._path)
        finally:
            if owned_descriptor:
                os.close(descriptor)
            with suppress(FileNotFoundError):
                temporary.unlink()


def record_before_drive(
    command: SpawnRecordCreate,
    *,
    record: Callable[[SpawnRecordCreate], SpawnRecordGet | SpawnRecordProblem],
    drive: Callable[[SpawnDriveContext], None],
    spool: SpawnSpool,
) -> SpawnDriveResult:
    """Record custody before the host driver, degrading only with a durable fact."""

    try:
        outcome = record(command)
    except (ConnectionError, OSError):
        return _drive_pending(command, drive=drive, spool=spool, problem=None)

    if isinstance(outcome, SpawnRecordProblem):
        if outcome.status >= _TEMPORARY_FAILURE_STATUS:
            return _drive_pending(command, drive=drive, spool=spool, problem=outcome)
        return SpawnDriveResult(
            context=SpawnDriveContext(
                command=command,
                record=None,
                durability_state=SpawnDurabilityState.REFUSED,
                spool_entry_id=None,
            ),
            problem=outcome,
        )

    context = SpawnDriveContext(
        command=command,
        record=outcome,
        durability_state=SpawnDurabilityState.RECORDED,
        spool_entry_id=None,
    )
    drive(context)
    return SpawnDriveResult(context=context, problem=None)


def _drive_pending(
    command: SpawnRecordCreate,
    *,
    drive: Callable[[SpawnDriveContext], None],
    spool: SpawnSpool,
    problem: SpawnRecordProblem | None,
) -> SpawnDriveResult:
    entry = spool.append(command)
    context = SpawnDriveContext(
        command=command,
        record=None,
        durability_state=SpawnDurabilityState.DURABILITY_PENDING,
        spool_entry_id=entry.entry_id,
    )
    drive(context)
    return SpawnDriveResult(context=context, problem=problem)


def replay_spool(
    spool: SpawnSpool,
    create: Callable[[SpawnRecordCreate], SpawnRecordGet | SpawnRecordProblem | None],
) -> tuple[int, int]:
    """Replay every pending entry through ``create``; ACK-verified removal.

    ``create`` is any callable with the PostgresSpawnRecords.create signature.
    Returns (replayed, refused). Entries whose create returns a problem stay
    pending — a spawn is never silently unrecorded.
    """

    replayed: list[UUID] = []
    refused = 0
    for entry in spool.pending():
        outcome = create(entry.command)
        if isinstance(outcome, SpawnRecordProblem):
            refused += 1
        elif isinstance(outcome, SpawnRecordGet):
            replayed.append(entry.entry_id)
        else:
            refused += 1
    if replayed:
        spool.remove_acked(replayed)
    return len(replayed), refused


@dataclass(frozen=True, slots=True)
class SourceSpawnRow:
    """One external spawn-history row, identified by source identity."""

    uuid: UUID
    status: str


def latest_status_effective(rows: Sequence[Mapping[str, Any]]) -> dict[UUID, str]:
    """Latest status wins per source identity (AC-SPWN-03 truth table)."""

    effective: dict[UUID, str] = {}
    for row in rows:
        source_uuid = UUID(str(row["uuid"]))
        effective[source_uuid] = str(row["status"])
    return effective


def derive_initial_running_set(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[SourceSpawnRow, ...]:
    """The initial running set is exactly the never-terminated source rows."""

    effective = latest_status_effective(rows)
    return tuple(
        SourceSpawnRow(uuid=source_uuid, status=status)
        for source_uuid, status in sorted(effective.items())
        if status not in _TERMINAL_SOURCE_STATUSES
    )


def history_parity_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    imported_source_ids: Iterable[UUID],
) -> SpawnHistoryParityReport:
    """Compare imported source identities with the effective external history."""

    effective = latest_status_effective(rows)
    source_ids = set(effective)
    imported_values = tuple(imported_source_ids)
    imported_ids = set(imported_values)
    running = derive_initial_running_set(rows)
    return SpawnHistoryParityReport(
        source_row_count=len(rows),
        distinct_source_count=len(source_ids),
        duplicate_source_row_count=len(rows) - len(source_ids),
        imported_record_count=len(imported_values),
        duplicate_imported_record_count=len(imported_values) - len(imported_ids),
        missing_source_ids=tuple(sorted(source_ids - imported_ids)),
        unexpected_source_ids=tuple(sorted(imported_ids - source_ids)),
        latest_statuses=tuple(sorted(effective.items())),
        initial_running_ids=tuple(item.uuid for item in running),
    )


def build_parity_proof(
    external_rows: Sequence[Mapping[str, Any]],
    ctower_rows: Sequence[Mapping[str, Any]],
    *,
    window: str,
) -> SpawnParityProof:
    """Build an unrecorded equality candidate for one reconcile window."""

    if not window.strip():
        raise ValueError("parity proof window must be non-empty")
    return SpawnParityProof(
        proof_id=uuid4(),
        window=window,
        external_digest=_rows_digest(external_rows),
        ctower_digest=_rows_digest(ctower_rows),
        external_count=len(external_rows),
        ctower_count=len(ctower_rows),
    )


def record_parity_proof(
    proof: SpawnParityProof,
    *,
    recorded_at: datetime | None = None,
) -> SpawnParityProof:
    """Record only an equal candidate; a mismatch cannot authorize the swap."""

    if not proof.parity_ok:
        raise ValueError("unequal spawn reconcile inputs cannot be recorded as parity")
    timestamp = recorded_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("parity proof timestamp must be timezone-aware")
    return replace(proof, recorded_at=timestamp)


def _rows_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    canonical_rows = sorted(
        json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=str) for row in rows
    )
    return hashlib.sha256("\n".join(canonical_rows).encode("utf-8")).hexdigest()


def reconcile_source(*, parity_proof: SpawnParityProof | None = None) -> str:
    """Keep the external twin authoritative until recorded equal parity exists."""

    if parity_proof is not None and parity_proof.is_recorded and parity_proof.parity_ok:
        return "ctower-spawn-reads"
    return "external-twin"
