from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from contextlib import suppress
from pathlib import Path
from typing import cast

from tools.compatibility.confidentiality import validate_public_report_bytes
from tools.compatibility.models_core import (
    CompatibilityError,
    CompatibilityMatrix,
    TelemetryContext,
)
from tools.compatibility.models_report import CompatibilityReport
from tools.compatibility.schema import (
    JsonObject,
    parse_matrix,
    parse_report,
    read_json_object,
    validate_report_schema,
    validate_telemetry,
)

__all__ = [
    "load_matrix",
    "validate_report",
    "write_report",
]


def load_matrix(path: Path) -> CompatibilityMatrix:
    """Validate raw JSON, then return the frozen fixed-L0 matrix value."""
    raw = read_json_object(path, label="matrix")
    source = parse_matrix(raw)
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    telemetry = _new_telemetry(digest)
    return CompatibilityMatrix(
        source=source,
        digest=digest,
        telemetry=telemetry,
    )


def validate_report(
    matrix: CompatibilityMatrix,
    report: JsonObject | CompatibilityReport,
) -> CompatibilityReport:
    """Accept evidence only after exact schema, model, topology, and input binding checks."""
    raw = (
        cast("JsonObject", report.model_dump(mode="json", by_alias=True))
        if isinstance(report, CompatibilityReport)
        else report
    )
    accepted = parse_report(raw)
    if accepted.input_digest != matrix.digest:
        raise CompatibilityError("report input digest does not match the current matrix")
    if accepted.matrix_id != matrix.matrix_id:
        raise CompatibilityError("report matrix ID does not match the current matrix")
    if accepted.telemetry != matrix.telemetry:
        raise CompatibilityError("report telemetry does not match matrix intake telemetry")
    for candidate, host_run, linux_run in zip(
        matrix.candidates, accepted.runs[::2], accepted.runs[1::2], strict=True
    ):
        if host_run.version != candidate.version or linux_run.version != candidate.version:
            raise CompatibilityError("report candidate identity does not bind to matrix input")
        image = linux_run.image_identity
        if image is None or image.requested != candidate.linux_image:
            raise CompatibilityError("report image identity does not bind to matrix input")
        _validate_resolution(host_run.resolution.lock, host_run.resolution.lock_sha256)
        _validate_resolution(linux_run.resolution.lock, linux_run.resolution.lock_sha256)
    return accepted


def write_report(
    path: Path,
    matrix: CompatibilityMatrix,
    report: JsonObject | CompatibilityReport,
) -> None:
    """Bind, validate, and atomically publish sanitized bytes without following symlinks."""
    accepted = validate_report(matrix, report)
    raw = cast("JsonObject", accepted.model_dump(mode="json", by_alias=True))
    validate_report_schema(raw)
    encoded = (json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    validate_public_report_bytes(encoded)
    path = _canonical_system_path(path)
    parent_descriptor = _open_parent_without_symlinks(path)
    temporary_name = f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        _reject_symlink_destination(parent_descriptor, path.name)
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_descriptor,
        )
        try:
            _write_all(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        os.fsync(parent_descriptor)
    except (OSError, UnicodeError) as error:
        raise CompatibilityError(f"unable to publish compatibility report: {error}") from error
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=parent_descriptor)
        os.close(parent_descriptor)


def _new_telemetry(input_digest: str) -> TelemetryContext:
    telemetry = TelemetryContext.for_matrix(input_digest)
    validate_telemetry(telemetry)
    return telemetry


def _validate_resolution(lock: tuple[str, ...], declared_sha256: str) -> None:
    payload = ("\n".join(lock) + "\n").encode()
    if hashlib.sha256(payload).hexdigest() != declared_sha256:
        raise CompatibilityError("dependency resolution digest does not match its lock evidence")


def _open_parent_without_symlinks(path: Path) -> int:
    if path.name in {"", ".", ".."} or ".." in path.parts:
        raise CompatibilityError("report path contains a parent-path escape")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open("/" if path.is_absolute() else ".", flags)
    components = path.parent.parts[1:] if path.is_absolute() else path.parent.parts
    try:
        for component in components:
            if component in {"", "."}:
                continue
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        os.close(descriptor)
        raise CompatibilityError(
            f"report parent is not a safe existing directory: {error}"
        ) from error
    return descriptor


def _canonical_system_path(path: Path) -> Path:
    absolute = path.absolute()
    if os.uname().sysname == "Darwin" and len(absolute.parts) > 1:
        if absolute.parts[1] == "var":
            return Path("/private", *absolute.parts[1:])
        if absolute.parts[1] == "tmp":
            return Path("/private/tmp", *absolute.parts[2:])
    return absolute


def _reject_symlink_destination(parent_descriptor: int, name: str) -> None:
    try:
        metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode):
        raise CompatibilityError("report destination cannot be a symlink")


def _write_all(descriptor: int, value: bytes) -> None:
    remaining = memoryview(value)
    while remaining:
        written = os.write(descriptor, remaining)
        if written == 0:
            raise OSError("report write returned zero bytes")
        remaining = remaining[written:]
