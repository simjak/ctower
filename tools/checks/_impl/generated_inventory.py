"""Filesystem authority for closed-world generated-output enumeration."""

from __future__ import annotations

import stat
from pathlib import Path, PurePosixPath


class GeneratedInventoryError(ValueError):
    """The configured generated output root cannot be enumerated safely."""


def enumerate_generated_outputs(root: Path, output_root: str, manifest_path: str) -> frozenset[str]:
    """Return regular files and symlinks below one confined generated root."""

    canonical_root = _resolved_directory(root, "repository root")
    output_relative = _normalized_relative(output_root, "generated output root")
    manifest_relative = _normalized_relative(manifest_path, "generated manifest")
    output = canonical_root.joinpath(*output_relative.parts)
    output_mode = _mode(output, output_relative)
    if stat.S_ISLNK(output_mode) or not stat.S_ISDIR(output_mode):
        raise GeneratedInventoryError("generated output root must be a real directory")
    resolved_output = _resolved_directory(output, "generated output root")
    if not resolved_output.is_relative_to(canonical_root):
        raise GeneratedInventoryError("generated output root escapes the repository")
    try:
        candidates = tuple(resolved_output.rglob("*"))
    except OSError as error:
        raise GeneratedInventoryError(
            f"generated output root cannot be enumerated: {error}"
        ) from error
    inventory: set[str] = set()
    for candidate in candidates:
        relative = PurePosixPath(candidate.relative_to(canonical_root).as_posix())
        _record_candidate(inventory, candidate, relative, manifest_relative)
    return frozenset(inventory)


def _record_candidate(
    inventory: set[str],
    candidate: Path,
    relative: PurePosixPath,
    manifest_relative: PurePosixPath,
) -> None:
    mode = _mode(candidate, relative)
    if stat.S_ISDIR(mode) or relative == manifest_relative:
        return
    if not (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
        raise GeneratedInventoryError(
            f"generated output has an unsupported filesystem type: {relative}"
        )
    inventory.add(relative.as_posix())


def _normalized_relative(value: str, label: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if (
        not relative.parts
        or relative.is_absolute()
        or ".." in relative.parts
        or str(relative) != value
    ):
        raise GeneratedInventoryError(f"{label} must be normalized and repository-relative")
    return relative


def _resolved_directory(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise GeneratedInventoryError(f"{label} cannot be resolved: {error}") from error
    if not resolved.is_dir():
        raise GeneratedInventoryError(f"{label} must be a directory")
    return resolved


def _mode(path: Path, relative: PurePosixPath) -> int:
    try:
        return path.lstat().st_mode
    except OSError as error:
        raise GeneratedInventoryError(
            f"generated output is missing or inaccessible: {relative}"
        ) from error
