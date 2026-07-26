"""Read-only allowlisted adapters with reviewed-closure enforcement."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from errno import ELOOP, ENOTDIR
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .canonical import JsonValue, sha256_digest, strict_json
from .refusal import MigrationRefusal, RefusalCode

__all__ = (
    "FileSnapshot",
    "OperationHint",
    "PositionedRecord",
    "ReadOnlySourceRoot",
    "SourceIdentity",
    "SourceRecord",
    "parse_jsonl",
    "validate_position_chain",
    "validate_relative_path",
)

_SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_ROW_BYTES = 256 * 1024


class SourceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    namespace: str = Field(min_length=1, max_length=128)
    immutable_source_id: str = Field(min_length=1, max_length=512)
    source_version: str = Field(min_length=1, max_length=256)
    source_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    def key(self) -> tuple[str, str, str]:
        return self.namespace, self.immutable_source_id, self.source_version


class OperationHint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    relation_kind: (
        Literal["parent_of", "depends_on", "blocks", "duplicates", "relates_to", "caused_by"] | None
    ) = None
    relation_target_ticket_id: str | None = None
    source_ticket_id: str | None = None
    relation_reason: str | None = Field(default=None, max_length=500)


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_id: Literal["ctower.synthetic-migration-source/v1"] = Field(alias="schema")
    identity: SourceIdentity
    candidate: bool
    review_decision: Literal["included", "excluded"] | None
    data_classes: list[str]
    title: str | None = Field(default=None, max_length=200)
    operation_hint: OperationHint | None = None
    checkpoint_criteria_digest: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    device: int
    inode: int
    data: bytes

    @property
    def digest(self) -> str:
        return sha256_digest(self.data)


@dataclass(frozen=True)
class PositionedRecord:
    record: SourceRecord
    path: str
    line_number: int
    byte_start: int
    byte_end: int
    slice_digest: str


class ReadOnlySourceRoot:
    """Opens regular files beneath one root without following any symlink."""

    def __init__(self, root: Path) -> None:
        root_stat = os.lstat(root)
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise MigrationRefusal(RefusalCode.SOURCE_SYMLINK, "allowlist root")
        self._root = root.resolve(strict=True)

    def read(self, relative_path: str) -> FileSnapshot:
        parts = _path_parts(relative_path)
        directory_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in parts[:-1]:
                next_fd = self._open_directory(directory_fd, component)
                os.close(directory_fd)
                directory_fd = next_fd
            return self._read_file(directory_fd, parts[-1], relative_path)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _open_directory(directory_fd: int, component: str) -> int:
        try:
            return os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except OSError as error:
            code = (
                RefusalCode.SOURCE_SYMLINK
                if error.errno in {ENOTDIR, ELOOP}
                else RefusalCode.SOURCE_UNREADABLE
            )
            raise MigrationRefusal(code, "source path component") from error

    @staticmethod
    def _read_file(directory_fd: int, name: str, relative_path: str) -> FileSnapshot:
        expected = _source_metadata(directory_fd, name, relative_path)
        fd = _open_source(directory_fd, name, relative_path)
        try:
            return _snapshot_from_fd(fd, expected, relative_path)
        finally:
            os.close(fd)


def _source_metadata(directory_fd: int, name: str, relative_path: str) -> os.stat_result:
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        raise MigrationRefusal(RefusalCode.SOURCE_UNREADABLE, relative_path) from error
    if stat.S_ISLNK(metadata.st_mode):
        raise MigrationRefusal(RefusalCode.SOURCE_SYMLINK, relative_path)
    if not stat.S_ISREG(metadata.st_mode):
        raise MigrationRefusal(RefusalCode.SOURCE_NOT_REGULAR, relative_path)
    return metadata


def _open_source(directory_fd: int, name: str, relative_path: str) -> int:
    try:
        return os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except OSError as error:
        code = RefusalCode.SOURCE_SYMLINK if error.errno == ELOOP else RefusalCode.SOURCE_UNREADABLE
        raise MigrationRefusal(code, relative_path) from error


def _snapshot_from_fd(fd: int, expected: os.stat_result, relative_path: str) -> FileSnapshot:
    metadata = os.fstat(fd)
    if not stat.S_ISREG(metadata.st_mode):
        raise MigrationRefusal(RefusalCode.SOURCE_NOT_REGULAR, relative_path)
    if (metadata.st_dev, metadata.st_ino) != (expected.st_dev, expected.st_ino):
        raise MigrationRefusal(RefusalCode.SOURCE_DRIFT, relative_path)
    if metadata.st_size > MAX_SOURCE_BYTES:
        raise MigrationRefusal(RefusalCode.SOURCE_TOO_LARGE, relative_path)
    data = _read_bounded(fd, metadata.st_size, relative_path)
    return FileSnapshot(relative_path, metadata.st_dev, metadata.st_ino, data)


def _path_parts(relative_path: str) -> tuple[str, ...]:
    if (
        not relative_path
        or relative_path.startswith("/")
        or "//" in relative_path
        or not _SAFE_PATH.fullmatch(relative_path)
    ):
        raise MigrationRefusal(RefusalCode.PATH_OUTSIDE_ALLOWLIST, "invalid relative path")
    parts = tuple(relative_path.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise MigrationRefusal(RefusalCode.PATH_OUTSIDE_ALLOWLIST, "path traversal")
    return parts


def validate_relative_path(relative_path: str) -> None:
    _path_parts(relative_path)


def _read_bounded(fd: int, expected_size: int, context: str) -> bytes:
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining:
        chunk = os.read(fd, min(remaining, 1024 * 1024))
        if not chunk:
            raise MigrationRefusal(RefusalCode.SOURCE_DRIFT, context)
        chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(fd, 1):
        raise MigrationRefusal(RefusalCode.SOURCE_DRIFT, context)
    return b"".join(chunks)


def parse_jsonl(snapshot: FileSnapshot) -> tuple[PositionedRecord, ...]:
    if snapshot.data and not snapshot.data.endswith(b"\n"):
        raise MigrationRefusal(RefusalCode.TRUNCATED_JSONL, snapshot.path)
    records: list[PositionedRecord] = []
    offset = 0
    for line_number, row in enumerate(snapshot.data.splitlines(keepends=True), start=1):
        if not row.endswith(b"\n"):
            raise MigrationRefusal(RefusalCode.TRUNCATED_JSONL, snapshot.path)
        payload = row[:-1]
        if not payload or len(payload) > MAX_ROW_BYTES:
            raise MigrationRefusal(RefusalCode.MALFORMED_JSON, snapshot.path)
        parsed = strict_json(payload, context=snapshot.path)
        record = _validate_record(parsed, snapshot.path)
        end = offset + len(row)
        records.append(
            PositionedRecord(
                record=record,
                path=snapshot.path,
                line_number=line_number,
                byte_start=offset,
                byte_end=end,
                slice_digest=sha256_digest(row),
            )
        )
        offset = end
    if offset != len(snapshot.data):
        raise MigrationRefusal(RefusalCode.NONCONTIGUOUS_POSITION, snapshot.path)
    validate_position_chain(records, len(snapshot.data), snapshot.path)
    return tuple(records)


def _validate_record(value: JsonValue, context: str) -> SourceRecord:
    try:
        return SourceRecord.model_validate(value)
    except ValidationError as error:
        raise MigrationRefusal(RefusalCode.MALFORMED_JSON, context) from error


def validate_position_chain(
    records: list[PositionedRecord], total_bytes: int, context: str
) -> None:
    next_offset = 0
    next_line = 1
    for item in records:
        if item.byte_start != next_offset or item.line_number != next_line:
            raise MigrationRefusal(RefusalCode.NONCONTIGUOUS_POSITION, context)
        next_offset = item.byte_end
        next_line += 1
    if next_offset != total_bytes:
        raise MigrationRefusal(RefusalCode.NONCONTIGUOUS_POSITION, context)
