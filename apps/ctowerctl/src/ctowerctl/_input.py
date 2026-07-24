"""Bounded local text and YAML input without aliases, tags, or hidden I/O."""

from __future__ import annotations

import math
import os
import stat
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
)

__all__: tuple[str, ...] = ()

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None

_MAX_DOCUMENT_BYTES = 1024 * 1024
_MAX_DOCUMENT_NODES = 50_000
_MAX_DOCUMENT_DEPTH = 64


def load_yaml_json(path: Path, *, label: str) -> JsonValue:
    """Load one finite JSON-shaped YAML 1.2 document under hard resource bounds."""

    try:
        text = read_text(path, maximum_bytes=_MAX_DOCUMENT_BYTES, label=label)
        yaml = YAML(typ="safe", pure=True)
        yaml.version = (1, 2)
        yaml.allow_duplicate_keys = False
        _inspect_events(yaml, text)
        value = yaml.load(text)
        return _bounded_json(value)
    except (OSError, UnicodeError, ValueError, YAMLError) as error:
        raise ValueError(f"{label} is invalid or unsafe") from error


def read_text(path: Path, *, maximum_bytes: int, label: str) -> str:
    """Read one no-follow regular UTF-8 file and enforce its byte cap."""

    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum_bytes:
            raise ValueError(f"{label} is not a bounded regular file")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > maximum_bytes:
            raise ValueError(f"{label} exceeds its byte limit")
        return payload.decode("utf-8")
    finally:
        os.close(descriptor)


def _inspect_events(yaml: YAML, text: str) -> None:
    depth = 0
    for count, event in enumerate(yaml.parse(text), start=1):
        if count > _MAX_DOCUMENT_NODES:
            raise ValueError("structured input has too many nodes")
        _reject_unsafe_event(event)
        depth += _depth_delta(event)
        if depth > _MAX_DOCUMENT_DEPTH:
            raise ValueError("structured input is nested too deeply")


def _reject_unsafe_event(event: object) -> None:
    if isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None:
        raise ValueError("structured input aliases and anchors are forbidden")
    if getattr(event, "tag", None) is not None:
        raise ValueError("structured input tags are forbidden")


def _depth_delta(event: object) -> int:
    if isinstance(event, CollectionStartEvent):
        return 1
    if isinstance(event, CollectionEndEvent):
        return -1
    return 0


def _bounded_json(value: object) -> JsonValue:
    counter = [0]
    return _json_value(value, depth=0, counter=counter)


def _json_value(value: object, *, depth: int, counter: list[int]) -> JsonValue:
    counter[0] += 1
    if counter[0] > _MAX_DOCUMENT_NODES or depth > _MAX_DOCUMENT_DEPTH:
        raise ValueError("structured input exceeds its resource bounds")
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return _finite_number(value)
    return _json_collection(value, depth=depth, counter=counter)


def _finite_number(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("structured input contains a non-finite number")
    return value


def _json_collection(value: object, *, depth: int, counter: list[int]) -> JsonValue:
    if isinstance(value, list):
        return [_json_value(item, depth=depth + 1, counter=counter) for item in value]
    if isinstance(value, dict):
        return _json_mapping(value, depth=depth, counter=counter)
    raise ValueError("structured input contains a non-JSON scalar")


def _json_mapping(
    value: dict[object, object],
    *,
    depth: int,
    counter: list[int],
) -> dict[str, JsonValue]:
    converted: dict[str, JsonValue] = {}
    for raw_key, item in value.items():
        if not isinstance(raw_key, str) or raw_key == "<<":
            raise ValueError("structured input keys must be strings and not merge keys")
        converted[raw_key] = _json_value(item, depth=depth + 1, counter=counter)
    return converted
