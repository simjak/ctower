"""Host-local, read-only checks for externally installed CP3-D references."""

from __future__ import annotations

import grp
import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tools.cp3d_packet.models import HostBinding, PacketBindings, RootOwnedFile

__all__ = [
    "FileObservation",
    "PreflightError",
    "observe_file",
    "validate_binding_document",
    "validate_local_role",
]

Role = Literal["primary", "standby"]


class PreflightError(RuntimeError):
    """A local operator-installed input failed closed."""


@dataclass(frozen=True, slots=True)
class FileObservation:
    """Non-sensitive metadata observed from one opened reference file."""

    regular: bool
    owner_uid: int
    group: str
    group_gid: int
    mode: str
    sha256: str


def validate_local_role(
    bindings: PacketBindings,
    role: Role,
    *,
    observer: Callable[[RootOwnedFile], FileObservation] | None = None,
) -> None:
    """Check one host's installed files without emitting or parsing their contents."""
    if bindings.binding_kind != "operator_bound":
        raise PreflightError("local preflight rejects synthetic mechanics bindings")
    if bindings.validation_context != "distinct_host_review":
        raise PreflightError("local preflight requires a distinct-host review context")
    host = bindings.primary if role == "primary" else bindings.standby
    inspect = observer or observe_file
    for reference in host.files():
        _validate_observation(reference, inspect(reference), expected_gid=bindings.postgres.gid)
    _validate_data_directory(host, bindings)


def validate_binding_document(path: Path) -> None:
    """Require the operator-bound authority document to be a narrow root-owned file."""
    try:
        metadata = path.lstat()
    except OSError as error:
        raise PreflightError("operator bindings document is missing") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise PreflightError("operator bindings document is not a regular file")
    if metadata.st_uid != 0:
        raise PreflightError("operator bindings document is not owned by root")
    if f"{stat.S_IMODE(metadata.st_mode):04o}" not in {"0400", "0440"}:
        raise PreflightError("operator bindings document permissions are too broad")


def observe_file(reference: RootOwnedFile) -> FileObservation:
    """Open without following symlinks, hash in memory, and return metadata only."""
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        descriptor = os.open(reference.path, flags)
    except OSError as error:
        raise PreflightError("root-owned input is missing or unsafe to open") from error
    try:
        metadata = os.fstat(descriptor)
        digest = hashlib.sha256()
        while block := os.read(descriptor, 64 * 1024):
            digest.update(block)
        try:
            group = grp.getgrgid(metadata.st_gid).gr_name
        except KeyError as error:
            raise PreflightError("root-owned input group is unknown") from error
    except OSError as error:
        raise PreflightError("root-owned input could not be inspected") from error
    finally:
        os.close(descriptor)
    return FileObservation(
        regular=stat.S_ISREG(metadata.st_mode),
        owner_uid=metadata.st_uid,
        group=group,
        group_gid=metadata.st_gid,
        mode=f"{stat.S_IMODE(metadata.st_mode):04o}",
        sha256=f"sha256:{digest.hexdigest()}",
    )


def _validate_observation(
    reference: RootOwnedFile,
    observed: FileObservation,
    *,
    expected_gid: int,
) -> None:
    if not observed.regular:
        raise PreflightError("root-owned input is not a regular file")
    if observed.owner_uid != 0:
        raise PreflightError("root-owned input is not owned by root")
    if observed.group != reference.group:
        raise PreflightError("root-owned input group does not match its binding")
    if observed.group_gid != expected_gid:
        raise PreflightError("root-owned input group ID does not match PostgreSQL")
    if observed.mode != reference.mode:
        raise PreflightError("root-owned input has weak or unexpected permissions")
    if observed.sha256 != reference.sha256:
        raise PreflightError("root-owned input digest does not match its binding")


def _validate_data_directory(
    host: HostBinding,
    bindings: PacketBindings,
) -> None:
    path = Path(host.data_directory)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise PreflightError("PostgreSQL data directory is missing") from error
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise PreflightError("PostgreSQL data path is not a real directory")
    if metadata.st_uid != bindings.postgres.uid:
        raise PreflightError("PostgreSQL data directory owner does not match the binding")
    if stat.S_IMODE(metadata.st_mode) & 0o027:
        raise PreflightError("PostgreSQL data directory permissions are too broad")
