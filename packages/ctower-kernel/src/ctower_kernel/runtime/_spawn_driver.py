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

import json
import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ctower_kernel.runtime._spawn_record_types import (
    SpawnRecordCreate,
    SpawnRecordGet,
    SpawnRecordProblem,
)

__all__ = [
    "SpawnSpool",
    "SpawnSpoolEntry",
    "derive_initial_running_set",
    "latest_status_effective",
    "reconcile_source",
    "replay_spool",
]

_SPOOL_MODE = 0o600
_SPOOL_FILENAME = "spawn-spool.jsonl"
_PENDING = "durability_pending"
_ACKED = "acked"

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


def latest_status_effective(rows: list[dict[str, Any]]) -> dict[UUID, str]:
    """Latest status wins per source identity (AC-SPWN-03 truth table)."""

    effective: dict[UUID, str] = {}
    for row in rows:
        source_uuid = UUID(str(row["uuid"]))
        effective[source_uuid] = str(row["status"])
    return effective


def derive_initial_running_set(
    rows: list[dict[str, Any]],
) -> tuple[SourceSpawnRow, ...]:
    """The initial running set is exactly the never-terminated source rows."""

    effective = latest_status_effective(rows)
    return tuple(
        SourceSpawnRow(uuid=source_uuid, status=status)
        for source_uuid, status in sorted(effective.items())
        if status not in _TERMINAL_SOURCE_STATUSES
    )


def reconcile_source(*, parity_proof_recorded: bool = False) -> str:
    """AC-SPWN-04: the reconcile read path stays on the external twin pre-proof."""

    if parity_proof_recorded:
        return "ctower-spawn-reads"
    return "external-twin"
