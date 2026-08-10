"""Observed, signed source-writer fence for the Request authority cutover."""

from __future__ import annotations

import hashlib
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner

__all__ = ["observe_source_fence"]

_REFUSAL_MARKER = b"REQUEST_WRITES_REFUSED"


def observe_source_fence(
    ledger_path: Path,
    *,
    caller_root: Path,
    caller_paths: tuple[Path, ...],
    phase: str,
    signer: ArtifactSigner,
) -> dict[str, Any]:
    """Inspect the actual read-only boundary and every named legacy caller."""

    if phase not in {"freeze", "batch", "final"}:
        raise ValueError("source-fence-phase-invalid")
    ledger = _regular_metadata(ledger_path)
    if not _read_only_mount(ledger_path):
        raise ValueError("source-ledger-filesystem-not-read-only")
    callers = [
        _caller_observation(caller_root, relative, final=phase == "final")
        for relative in caller_paths
    ]
    if not callers:
        raise ValueError("source-fence-caller-inventory-empty")
    source = ledger_path.read_bytes()
    return signer.seal(
        {
            "schema": "ctower.request-source-fence/v1",
            "phase": phase,
            "ledger_sha256": _digest(source),
            "source_identity": {
                "device": ledger.st_dev,
                "inode": ledger.st_ino,
                "mode": ledger.st_mode,
                "mtime_ns": str(ledger.st_mtime_ns),
                "size": ledger.st_size,
            },
            "writer_refuses": True,
            "mutation_entrypoints_removed": phase == "final",
            "filesystem_read_only": True,
            "callers": callers,
            "observed_at": datetime.now(UTC).isoformat(),
        },
        "fence_digest",
    )


def _caller_observation(root: Path, relative: Path, *, final: bool) -> dict[str, str]:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("source-fence-caller-path-invalid")
    target = root / relative
    if final:
        if target.exists() or target.is_symlink():
            raise ValueError(f"source-fence-caller-still-present:{relative}")
        digest = _digest(f"removed:{relative.as_posix()}".encode())
        return {"path": relative.as_posix(), "sha256": digest, "state": "removed"}
    metadata = _regular_metadata(target)
    if stat.S_IMODE(metadata.st_mode) & 0o222:
        raise ValueError(f"source-fence-caller-writable:{relative}")
    content = target.read_bytes()
    if _REFUSAL_MARKER not in content:
        raise ValueError(f"source-fence-caller-refusal-unproved:{relative}")
    return {"path": relative.as_posix(), "sha256": _digest(content), "state": "refuses"}


def _regular_metadata(path: Path) -> os.stat_result:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("source-fence-path-not-regular")
    return metadata


def _read_only_mount(path: Path) -> bool:
    return bool(os.statvfs(path).f_flag & os.ST_RDONLY)


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"
