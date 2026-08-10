"""Strict physical-source boundary for the Request cutover analyzer."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

__all__ = [
    "SourceLine",
    "classification_blockers",
    "historical_values",
    "is_request",
    "optional_text",
    "parse_jsonl",
    "read_stable_regular",
    "recheck_source",
    "request_id",
    "request_number",
    "sha256",
    "source_timestamp",
    "status",
    "unique_object",
]

_SOURCE_REQUEST_ID = re.compile(r"^R(0*[1-9][0-9]*)$")
_ALIASES = {
    "ACK": "TRIAGED",
    "ACKNOWLEDGED": "TRIAGED",
    "ACTIVE": "WIP",
    "IN-PROGRESS": "WIP",
    "IN_PROGRESS": "WIP",
    "WORKING": "WIP",
}
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_REQUEST_KEYS = frozenset(
    {
        "action",
        "active",
        "blocker",
        "created",
        "cross_project_override",
        "decision",
        "history",
        "id",
        "merged_into",
        "note",
        "owner",
        "project",
        "project_bound",
        "record_type",
        "refines",
        "relationships",
        "split_brain_replay",
        "status",
        "text",
        "updated",
        "wont_do_reason",
    }
)
_DECISION_KEYS = frozenset(
    {"actor", "at", "id", "kind", "merged", "reason", "record_type", "requests", "target"}
)


class SourceLine:
    __slots__ = ("digest", "line_number", "value")

    def __init__(self, line_number: int, value: dict[str, object], digest: str) -> None:
        self.line_number = line_number
        self.value = value
        self.digest = digest


def read_stable_regular(path: Path) -> tuple[bytes, dict[str, object]]:
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("source-ledger-not-regular")
    if metadata.st_size > _MAX_SOURCE_BYTES:
        raise ValueError("source-ledger-too-large")
    data = _read_open_file(path, metadata.st_dev, metadata.st_ino)
    return data, {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mode": metadata.st_mode,
        "mtime_ns": str(metadata.st_mtime_ns),
        "size": metadata.st_size,
    }


def _read_open_file(path: Path, device: int, inode: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (device, inode):
            raise ValueError("source-ledger-identity-drift")
        return _read_bounded(fd)
    finally:
        os.close(fd)


def _read_bounded(fd: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := os.read(fd, 1024 * 1024):
        total += len(chunk)
        if total > _MAX_SOURCE_BYTES:
            raise ValueError("source-ledger-too-large")
        chunks.append(chunk)
    return b"".join(chunks)


def recheck_source(path: Path, identity: Mapping[str, object], digest: str) -> None:
    data, observed = read_stable_regular(path)
    if any(observed[key] != identity[key] for key in _identity_keys()):
        raise ValueError("source-ledger-drift")
    if sha256(data) != digest:
        raise ValueError("source-ledger-digest-drift")


def _identity_keys() -> tuple[str, ...]:
    return "device", "inode", "mode", "mtime_ns", "size"


def parse_jsonl(data: bytes) -> list[SourceLine]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("source-ledger-not-utf8") from error
    return [
        _parse_line(line_number, raw)
        for line_number, raw in enumerate(text.splitlines(), start=1)
        if raw.strip()
    ]


def _parse_line(line_number: int, raw: str) -> SourceLine:
    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"source-ledger-malformed-line:{line_number}") from error
    if not isinstance(value, dict):
        raise TypeError(f"source-ledger-nonobject-line:{line_number}")
    return SourceLine(line_number, cast(dict[str, object], value), sha256(raw.encode()))


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate-json-key")
        value[key] = item
    return value


def classification_blockers(lines: list[SourceLine]) -> list[str]:
    return [problem for item in lines if (problem := _classification_problem(item)) is not None]


def _classification_problem(item: SourceLine) -> str | None:
    record_type = str(item.value.get("record_type") or "request").strip().lower()
    if record_type not in {"request", "decision"}:
        return f"source-record-type-unknown:{item.line_number}"
    allowed = _REQUEST_KEYS if record_type == "request" else _DECISION_KEYS
    if not set(item.value) <= allowed:
        return f"source-record-schema-unknown:{item.line_number}"
    if record_type == "request" and _SOURCE_REQUEST_ID.fullmatch(request_id(item.value)) is None:
        return f"source-request-shape-invalid:{item.line_number}"
    if record_type == "decision" and not optional_text(item.value.get("id")):
        return f"source-decision-shape-invalid:{item.line_number}"
    return None


def historical_values(value: object) -> Iterable[str | None]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from historical_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from historical_values(item)


def is_request(value: Mapping[str, object]) -> bool:
    kind = str(value.get("record_type") or "request").strip().lower()
    return kind == "request" and _SOURCE_REQUEST_ID.fullmatch(request_id(value)) is not None


def request_id(value: Mapping[str, object]) -> str:
    return str(value.get("id") or "").strip().upper()


def status(value: object) -> str:
    normalized = str(value or "NEW").strip().upper()
    return _ALIASES.get(normalized, normalized)


def optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def source_timestamp(value: object) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def request_number(value: str) -> int:
    match = _SOURCE_REQUEST_ID.fullmatch(value)
    return int(match.group(1)) if match is not None else 2**63 - 1


def sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"
