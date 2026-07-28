"""Descriptor-confined, bounded document handling for the private-VPS packet."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Self, cast
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import BaseModel, ValidationError

__all__ = [
    "MAX_ARTIFACT_BYTES",
    "MAX_COMPOSE_BYTES",
    "MAX_CONFIGURATION_BYTES",
    "MAX_DOCUMENT_BYTES",
    "ConfinedRoot",
    "DirectorySnapshot",
    "FileSnapshot",
    "PacketError",
    "digest_file",
    "load_model",
    "load_snapshot",
    "verify_secret_free_text",
]

JsonObject = dict[str, Any]
MAX_DOCUMENT_BYTES = 256 * 1024
MAX_COMPOSE_BYTES = 256 * 1024
MAX_CONFIGURATION_BYTES = 64 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024
MAX_STRUCTURE_DEPTH = 64
MAX_STRUCTURE_TOKENS = 32_768
_READ_BLOCK_BYTES = 64 * 1024
_SCHEMA_ROOT = Path(__file__).parents[2] / "contracts/operations"
_MODEL_SCHEMAS: dict[str, tuple[str, str | None]] = {
    "DeploymentBindings": ("private-vps-deployment.schema.json", None),
    "EvidenceManifest": ("private-vps-evidence.schema.json", None),
    "CheckArtifact": ("private-vps-evidence.schema.json", "checkArtifact"),
    "SyntheticResult": ("private-vps-evidence.schema.json", "syntheticResult"),
    "SchedulerReceipt": ("private-vps-evidence.schema.json", "schedulerReceipt"),
}
_REFERENCE = re.compile(
    r"^(?:alert-owner|credential-file|file|identity|object-root|schedule|"
    r"telemetry)-ref://[A-Za-z0-9._~:/-]+$"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(?:password|passphrase|private[_-]?key|secret|token|access[_-]?key)\s*[:=]"
)
_INLINE_MARKERS = ("-----BEGIN ", "postgresql://", "postgres://", "Bearer ")
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW
if hasattr(os, "O_CLOEXEC"):
    _DIRECTORY_FLAGS |= os.O_CLOEXEC
    _FILE_FLAGS |= os.O_CLOEXEC


class PacketError(RuntimeError):
    """A sanitized fail-closed packet error."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(code)
        self.code = code
        self.field = field


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    """The exact bounded bytes and metadata read from one open descriptor."""

    data: bytes
    sha256: str
    size: int
    owner_uid: int
    owner_gid: int
    mode: str


@dataclass(frozen=True, slots=True)
class DirectorySnapshot:
    """Metadata observed from one descriptor-confined directory."""

    owner_uid: int
    owner_gid: int
    mode: str


@dataclass(slots=True)
class _JsonStructureGuard:
    depth: int = 0
    tokens: int = 0
    in_string: bool = False
    escaped: bool = False
    in_scalar: bool = False

    def consume(self, byte: int, *, field: str) -> None:
        if self.in_string:
            self._consume_string(byte)
        else:
            self._consume_unquoted(byte)
        if self.depth > MAX_STRUCTURE_DEPTH or self.tokens > MAX_STRUCTURE_TOKENS:
            raise PacketError("structure_limit_exceeded", field)

    def _consume_string(self, byte: int) -> None:
        if self.escaped:
            self.escaped = False
        elif byte == ord("\\"):
            self.escaped = True
        elif byte == ord('"'):
            self.in_string = False
            self.tokens += 1

    def _consume_unquoted(self, byte: int) -> None:
        if byte == ord('"'):
            self.in_string = True
            self.in_scalar = False
            return
        if byte in b"{[":
            self.depth += 1
            self.tokens += 1
            self.in_scalar = False
            return
        if byte in b"}]":
            self.depth -= 1
            self.tokens += 1
            self.in_scalar = False
            return
        if byte in b",:":
            self.tokens += 1
            self.in_scalar = False
            return
        if byte in b" \t\r\n":
            self.in_scalar = False
            return
        if not self.in_scalar:
            self.tokens += 1
            self.in_scalar = True


class ConfinedRoot:
    """Retain an opened directory authority and resolve children with openat."""

    def __init__(self, path: Path) -> None:
        self._descriptor = _open_absolute_directory(path)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1

    def read(self, relative: str, *, field: str, max_bytes: int) -> FileSnapshot:
        """Read one regular child exactly once under this retained root."""
        parts = _relative_parts(relative, field=field)
        parent = self._open_parent(parts, field=field)
        try:
            descriptor = os.open(parts[-1], _FILE_FLAGS, dir_fd=parent)
        except OSError as error:
            raise PacketError("missing_or_unsafe_file", field) from error
        finally:
            os.close(parent)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise PacketError("missing_or_unsafe_file", field)
            if before.st_size > max_bytes:
                raise PacketError("document_too_large", field)
            data = _read_bounded(descriptor, max_bytes=max_bytes, field=field)
            after = os.fstat(descriptor)
            if _identity(before) != _identity(after) or len(data) != after.st_size:
                raise PacketError("file_changed_during_read", field)
        except OSError as error:
            raise PacketError("unreadable_file", field) from error
        finally:
            os.close(descriptor)
        return FileSnapshot(
            data=data,
            sha256=f"sha256:{hashlib.sha256(data).hexdigest()}",
            size=len(data),
            owner_uid=after.st_uid,
            owner_gid=after.st_gid,
            mode=f"{stat.S_IMODE(after.st_mode):04o}",
        )

    def directory(self, relative: str, *, field: str) -> DirectorySnapshot:
        """Observe one directory without following any component symlink."""
        parts = _relative_parts(relative, field=field)
        parent = self._open_parent(parts, field=field)
        try:
            descriptor = os.open(parts[-1], _DIRECTORY_FLAGS, dir_fd=parent)
        except OSError as error:
            raise PacketError("missing_or_unsafe_directory", field) from error
        finally:
            os.close(parent)
        try:
            metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        return DirectorySnapshot(
            owner_uid=metadata.st_uid,
            owner_gid=metadata.st_gid,
            mode=f"{stat.S_IMODE(metadata.st_mode):04o}",
        )

    def _open_parent(self, parts: tuple[str, ...], *, field: str) -> int:
        try:
            current = os.dup(self._descriptor)
        except OSError as error:
            raise PacketError("closed_root", field) from error
        try:
            for component in parts[:-1]:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
                os.close(current)
                current = child
        except OSError as error:
            os.close(current)
            raise PacketError("missing_or_unsafe_directory", field) from error
        return current


def load_model[ModelT: BaseModel](
    path: Path,
    model: type[ModelT],
    *,
    field: str,
) -> ModelT:
    """Read one bounded document once, then schema- and model-validate those bytes."""
    absolute = _lexical_absolute(path)
    with ConfinedRoot(absolute.parent) as root:
        snapshot = root.read(absolute.name, field=field, max_bytes=MAX_DOCUMENT_BYTES)
    return load_snapshot(snapshot, model, field=field)


def load_snapshot[ModelT: BaseModel](
    snapshot: FileSnapshot,
    model: type[ModelT],
    *,
    field: str,
) -> ModelT:
    """Validate one retained byte snapshot against authored schema and its mirror."""
    raw = _json_object(snapshot.data, field=field)
    _reject_inline_material(raw, field=field)
    schema_file, definition = _MODEL_SCHEMAS[model.__name__]
    schema = _schema_document(schema_file)
    validation_schema = schema
    if definition is not None:
        validation_schema = {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{definition}",
        }
    try:
        Draft202012Validator(
            validation_schema,
            format_checker=FormatChecker(),
        ).validate(raw)
    except SchemaValidationError as error:
        raise PacketError("invalid_document", _schema_location(field, error)) from error
    except (MemoryError, RecursionError) as error:
        raise PacketError("invalid_document", field) from error
    try:
        return model.model_validate_json(snapshot.data)
    except ValidationError as error:
        location = _validation_location(error)
        raise PacketError("schema_model_divergence", f"{field}.{location}") from error
    except (MemoryError, RecursionError) as error:
        raise PacketError("invalid_document", field) from error


def digest_file(path: Path, *, field: str) -> str:
    """Hash a bounded regular file from the same safe snapshot primitive."""
    absolute = _lexical_absolute(path)
    with ConfinedRoot(absolute.parent) as root:
        return root.read(
            absolute.name,
            field=field,
            max_bytes=MAX_DOCUMENT_BYTES,
        ).sha256


def verify_secret_free_text(snapshot: FileSnapshot, *, field: str) -> None:
    """Apply the packet's bounded inline-material policy to retained text."""
    try:
        text = snapshot.data.decode("utf-8")
    except UnicodeError as error:
        raise PacketError("invalid_text", field) from error
    _reject_inline_text(text, field=field)


def _open_absolute_directory(path: Path) -> int:
    absolute = _lexical_absolute(path)
    parts = absolute.parts
    if not absolute.is_absolute() or not parts or parts[0] != "/":
        raise PacketError("unsafe_root", "root")
    current = -1
    try:
        current = os.open("/", _DIRECTORY_FLAGS)
        for component in parts[1:]:
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = child
    except OSError as error:
        if current >= 0:
            os.close(current)
        raise PacketError("missing_or_unsafe_directory", "root") from error
    return current


def _relative_parts(relative: str, *, field: str) -> tuple[str, ...]:
    path = PurePosixPath(relative)
    parts = path.parts
    if path.is_absolute() or not parts or any(part in {"", ".", ".."} for part in parts):
        raise PacketError("unsafe_path", field)
    return parts


def _lexical_absolute(path: Path) -> Path:
    raw = path if path.is_absolute() else Path.cwd() / path
    components: list[str] = []
    for component in raw.parts[1:]:
        if component in {"", "."}:
            continue
        if component == "..":
            if components:
                components.pop()
            continue
        components.append(component)
    return Path("/").joinpath(*components)


def _read_bounded(descriptor: int, *, max_bytes: int, field: str) -> bytes:
    encoded = bytearray()
    while block := os.read(descriptor, _READ_BLOCK_BYTES):
        encoded.extend(block)
        if len(encoded) > max_bytes:
            raise PacketError("document_too_large", field)
    return bytes(encoded)


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _json_object(data: bytes, *, field: str) -> JsonObject:
    _guard_json_structure(data, field=field)
    try:
        raw = json.loads(data)
    except (UnicodeError, json.JSONDecodeError, MemoryError, RecursionError) as error:
        raise PacketError("invalid_json", field) from error
    if not isinstance(raw, dict):
        raise PacketError("invalid_document", field)
    return cast("JsonObject", raw)


def _schema_document(name: str) -> JsonObject:
    try:
        raw = json.loads((_SCHEMA_ROOT / name).read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError, MemoryError, RecursionError) as error:
        raise PacketError("invalid_authored_schema", "schema") from error
    if not isinstance(raw, dict):
        raise PacketError("invalid_authored_schema", "schema")
    return cast("JsonObject", raw)


def _guard_json_structure(data: bytes, *, field: str) -> None:
    guard = _JsonStructureGuard()
    for byte in data:
        guard.consume(byte, field=field)


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


def _schema_location(field: str, error: SchemaValidationError) -> str:
    location = ".".join(str(item) for item in error.absolute_path)
    return field if not location else f"{field}.{location}"
