"""Append-only, hash-chained ledger of development-runtime database checkpoints."""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "CheckpointLedgerError",
    "CheckpointRecord",
    "append_record",
    "artifact_path",
    "checkpoint_root",
    "ledger_digest",
    "read_records",
    "serialize_checkpoints",
]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHECKPOINT_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}$")
_LEDGER_NAME = "ledger.jsonl"
_ARTIFACT_NAME = "database.sql.gpg"


class CheckpointLedgerError(RuntimeError):
    """The checkpoint ledger is absent, malformed, or no longer append-only."""


class CheckpointRecord(BaseModel):
    """One immutable, digest-bound development-runtime checkpoint entry."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_id: Literal["ctower.development-checkpoint/v1"] = Field(alias="schema")
    checkpoint_id: str
    captured_at: datetime
    database: str
    generation: str
    generation_migration_id: str
    artifact_sha256: str
    artifact_bytes: int = Field(ge=1)
    passphrase_ref: str
    previous_sha256: str

    @field_validator("checkpoint_id")
    @classmethod
    def _identifier(cls, value: str) -> str:
        if _CHECKPOINT_ID.fullmatch(value) is None:
            raise ValueError("a checkpoint id is one UTC timestamp and one content digest")
        return value

    @field_validator("generation", "artifact_sha256", "previous_sha256")
    @classmethod
    def _bound_digest(cls, value: str) -> str:
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("checkpoint provenance must use lowercase SHA-256")
        return value

    @field_validator("captured_at")
    @classmethod
    def _capture_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checkpoint capture time must be timezone-aware")
        return value


def checkpoint_root() -> Path:
    """Return the owner-only root holding checkpoint artifacts and their ledger."""

    return _state_home() / "ctower" / "development-checkpoints"


def artifact_path(checkpoint_id: str) -> Path:
    """Return the single encrypted artifact pathname owned by one checkpoint id."""

    return checkpoint_root() / checkpoint_id / _ARTIFACT_NAME


def ledger_digest() -> str:
    """Return the digest of the exact ledger bytes the next record must chain to."""

    ledger = checkpoint_root() / _LEDGER_NAME
    existing = ledger.read_bytes() if ledger.exists() else b""
    return f"sha256:{hashlib.sha256(existing).hexdigest()}"


@contextmanager
def serialize_checkpoints() -> Iterator[None]:
    """Block concurrent checkpoint-changing verbs until this operation exits."""

    root = checkpoint_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        yield
    finally:
        os.close(directory)


def read_records() -> tuple[CheckpointRecord, ...]:
    """Return every recorded checkpoint, refusing a ledger that was not appended to."""

    ledger = checkpoint_root() / _LEDGER_NAME
    if not ledger.exists():
        return ()
    lines = ledger.read_bytes().splitlines(keepends=True)
    records: list[CheckpointRecord] = []
    digest = hashlib.sha256()
    for number, line in enumerate(lines, start=1):
        expected = f"sha256:{digest.hexdigest()}"
        record = _parse_line(line, number)
        if record.previous_sha256 != expected:
            raise CheckpointLedgerError(
                f"the development checkpoint ledger is not append-only at line {number}"
            )
        records.append(record)
        digest.update(line)
    return tuple(records)


def append_record(record: CheckpointRecord) -> None:
    """Append one record whose chain link must match the exact current ledger."""

    root = checkpoint_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    ledger = root / _LEDGER_NAME
    if record.previous_sha256 != ledger_digest():
        raise CheckpointLedgerError(
            "the development checkpoint ledger advanced while this checkpoint was captured"
        )
    line = record.model_dump_json(by_alias=True) + "\n"
    descriptor = os.open(ledger, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def _parse_line(line: bytes, number: int) -> CheckpointRecord:
    if not line.endswith(b"\n"):
        raise CheckpointLedgerError(
            f"the development checkpoint ledger is truncated at line {number}"
        )
    try:
        return CheckpointRecord.model_validate_json(line)
    except ValueError as error:
        raise CheckpointLedgerError(
            f"the development checkpoint ledger is malformed at line {number}"
        ) from error


def _state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
