"""Bounded JSON and artifact helpers for the private-VPS packet."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

__all__ = ["PacketError", "digest_file", "load_model", "resolve_artifact"]

JsonObject = dict[str, Any]
MAX_DOCUMENT_BYTES = 1_000_000
_REFERENCE = re.compile(
    r"^(?:alert-owner|credential-file|file|identity|object-root|schedule|"
    r"telemetry)-ref://[A-Za-z0-9._~:/-]+$"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(?:password|passphrase|private[_-]?key|secret|token|access[_-]?key)\s*[:=]"
)
_INLINE_MARKERS = ("-----BEGIN ", "postgresql://", "postgres://", "Bearer ")


class PacketError(RuntimeError):
    """A sanitized fail-closed packet error."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(code)
        self.code = code
        self.field = field


def load_model[ModelT: BaseModel](path: Path, model: type[ModelT], *, field: str) -> ModelT:
    """Read one bounded regular JSON file and strictly parse it."""
    raw = _read_json(path, field=field)
    _reject_inline_material(raw, field=field)
    try:
        return model.model_validate_json(json.dumps(raw))
    except ValidationError as error:
        location = _validation_location(error)
        raise PacketError("invalid_document", f"{field}.{location}") from error


def digest_file(path: Path, *, field: str) -> str:
    """Hash a regular non-symlink file without exposing its bytes."""
    descriptor = _open_regular(path, field=field)
    digest = hashlib.sha256()
    try:
        while block := os.read(descriptor, 64 * 1024):
            digest.update(block)
    except OSError as error:
        raise PacketError("unreadable_file", field) from error
    finally:
        os.close(descriptor)
    return f"sha256:{digest.hexdigest()}"


def resolve_artifact(base: Path, relative: str, *, field: str) -> Path:
    """Resolve one traversal-free path relative to its declaring document."""
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PacketError("unsafe_path", field)
    resolved_base = base.resolve()
    resolved = (resolved_base / candidate).resolve(strict=False)
    if not resolved.is_relative_to(resolved_base):
        raise PacketError("unsafe_path", field)
    return resolved


def _read_json(path: Path, *, field: str) -> JsonObject:
    descriptor = _open_regular(path, field=field)
    try:
        encoded = _read_bounded(descriptor, field=field)
        raw = json.loads(encoded)
    except PacketError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PacketError("invalid_json", field) from error
    finally:
        os.close(descriptor)
    if not isinstance(raw, dict):
        raise PacketError("invalid_document", field)
    return cast("JsonObject", raw)


def _open_regular(path: Path, *, field: str) -> int:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
    except OSError as error:
        raise PacketError("missing_or_unsafe_file", field) from error
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise PacketError("missing_or_unsafe_file", field)
    return descriptor


def _read_bounded(descriptor: int, *, field: str) -> bytes:
    encoded = bytearray()
    while block := os.read(descriptor, 64 * 1024):
        encoded.extend(block)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise PacketError("document_too_large", field)
    return bytes(encoded)


def _reject_inline_material(value: object, *, field: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_inline_key(str(key), child, field=field)
        return
    if isinstance(value, list):
        for child in value:
            _reject_inline_material(child, field=field)
        return
    if isinstance(value, str):
        _reject_inline_text(value, field=field)


def _reject_inline_key(key: str, value: object, *, field: str) -> None:
    normalized = key.lower()
    sensitive = any(
        part in normalized for part in ("password", "private_key", "secret", "token", "dsn")
    )
    if sensitive and not isinstance(value, dict) and value is not None:
        raise PacketError("inline_secret_material", field)
    _reject_inline_material(value, field=field)


def _reject_inline_text(value: str, *, field: str) -> None:
    if _REFERENCE.fullmatch(value):
        return
    if any(marker.lower() in value.lower() for marker in _INLINE_MARKERS):
        raise PacketError("inline_secret_material", field)
    if _CREDENTIAL_ASSIGNMENT.search(value):
        raise PacketError("inline_secret_material", field)
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise PacketError("inline_secret_material", field)


def _validation_location(error: ValidationError) -> str:
    first = error.errors(include_url=False, include_context=False, include_input=False)[0]
    if first["type"] == "extra_forbidden":
        return "root"
    return ".".join(str(item) for item in first["loc"]) or "root"
