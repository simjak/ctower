"""Typed authority for generated manifests, digests, notices, and writes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import cast

from tools.checks._impl.generated_inventory import (
    GeneratedInventoryError,
    enumerate_generated_outputs,
)
from tools.checks._impl.model import GeneratedPathPolicy
from tools.checks.report import Finding, Severity

GENERATED_NOTICE = "DO NOT EDIT: generated file; regenerate from declared inputs."
GENERATED_NOTICE_FIELD = "_notice"
_MANIFEST_SCHEMA = "ctower.generated-manifest/v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_GENERATED_ROOT = PurePosixPath("generated")


class GeneratedManifestError(ValueError):
    """A generated manifest or declared generated artifact is malformed."""


class _ManifestCollection(StrEnum):
    INPUTS = "inputs"
    OUTPUTS = "outputs"


@dataclass(frozen=True, slots=True)
class GeneratedDigest:
    """One normalized repository-relative content digest."""

    path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class GeneratedArtifact:
    """One generator declaration with typed input and output digests."""

    artifact_id: str
    generator: str
    tool_version: str
    command: str
    inputs: tuple[GeneratedDigest, ...]
    outputs: tuple[GeneratedDigest, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.artifact_id,
            "generator": self.generator,
            "tool_version": self.tool_version,
            "command": self.command,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
        }


@dataclass(frozen=True, slots=True)
class GeneratedManifest:
    """Strict generated-artifact inventory with deterministic rendering."""

    artifacts: tuple[GeneratedArtifact, ...]

    def upsert(self, artifact: GeneratedArtifact) -> GeneratedManifest:
        retained = tuple(
            item for item in self.artifacts if item.artifact_id != artifact.artifact_id
        )
        return GeneratedManifest(
            tuple(sorted((*retained, artifact), key=lambda item: item.artifact_id))
        )

    def to_dict(self) -> dict[str, object]:
        return {
            GENERATED_NOTICE_FIELD: GENERATED_NOTICE,
            "schema": _MANIFEST_SCHEMA,
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


def load_generated_manifest(root: Path, manifest_name: str | Path) -> GeneratedManifest:
    """Load external JSON only after exact structural and scalar validation."""

    relative = _normalized_relative(str(manifest_name), "generated manifest")
    try:
        path = _regular_repository_file(root, relative, "generated manifest")
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeneratedManifestError(f"generated manifest cannot be loaded: {error}") from error
    return _parse_manifest(payload)


def render_generated_manifest(manifest: GeneratedManifest) -> str:
    """Render the canonical manifest bytes."""

    return json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n"


def digest_file(root: Path, relative: Path) -> GeneratedDigest:
    """Hash one declared input from the source repository."""

    normalized = _normalized_relative(relative.as_posix(), "digest input")
    try:
        content = _regular_repository_file(root, normalized, "digest input").read_bytes()
    except OSError as error:
        raise GeneratedManifestError(f"cannot hash {relative.as_posix()}: {error}") from error
    return digest_bytes(Path(normalized.as_posix()), content)


def digest_bytes(relative: Path, content: bytes) -> GeneratedDigest:
    """Hash deterministic bytes before they are committed to a destination."""

    return GeneratedDigest(relative.as_posix(), f"sha256:{hashlib.sha256(content).hexdigest()}")


def atomic_write_generated_text(root: Path, relative: Path, content: str) -> None:
    """Replace one repository-confined generated file without following symlinks."""

    normalized = _normalized_relative(relative.as_posix(), "generated output")
    if normalized == _GENERATED_ROOT or not normalized.is_relative_to(_GENERATED_ROOT):
        raise GeneratedManifestError("generated output must be strictly below generated/")
    canonical_root = _canonical_repository_root(root, "generated output")
    destination = canonical_root.joinpath(*normalized.parts)
    parent = _prepare_output_parent(canonical_root, normalized.parent)
    parent_identity = _directory_identity(parent)
    _validate_output_leaf(destination, normalized)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        current_parent = _prepare_output_parent(canonical_root, normalized.parent)
        if _directory_identity(current_parent) != parent_identity:
            raise GeneratedManifestError("generated output parent changed during atomic write")
        _validate_output_leaf(destination, normalized)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _prepare_output_parent(canonical_root: Path, parent: PurePosixPath) -> Path:
    current = canonical_root
    for part in parent.parts:
        current /= part
        mode = _existing_or_created_directory(current, parent)
        if stat.S_ISLNK(mode):
            raise GeneratedManifestError(f"generated output parent contains a symlink: {parent}")
        if not stat.S_ISDIR(mode):
            raise GeneratedManifestError(f"generated output parent is not a directory: {parent}")
    resolved = _resolve_existing(current, parent, "generated output parent")
    if not resolved.is_relative_to(canonical_root):
        raise GeneratedManifestError(f"generated output parent escapes repository: {parent}")
    return resolved


def _existing_or_created_directory(path: Path, relative: PurePosixPath) -> int:
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        with suppress(FileExistsError):
            path.mkdir()
        return _lstat_mode(path, relative, "generated output parent")
    except OSError as error:
        raise GeneratedManifestError(
            f"generated output parent is inaccessible: {relative}"
        ) from error


def _validate_output_leaf(destination: Path, relative: PurePosixPath) -> None:
    try:
        mode = destination.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as error:
        raise GeneratedManifestError(
            f"generated output leaf is inaccessible: {relative}"
        ) from error
    if stat.S_ISLNK(mode):
        raise GeneratedManifestError(f"generated output leaf is a symlink: {relative}")
    if not stat.S_ISREG(mode):
        raise GeneratedManifestError(f"generated output leaf is not a regular file: {relative}")


def _directory_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino


def verify_generated_manifest(root: Path, policy: GeneratedPathPolicy) -> tuple[Finding, ...]:
    """Verify exact generated ownership, declared digests, and JSON notices."""

    try:
        manifest = load_generated_manifest(root, policy.manifest_path)
        inventory_findings = _verify_output_inventory(root, policy, manifest)
    except GeneratedManifestError as error:
        return (_manifest_finding(policy.manifest_path, str(error)),)
    findings = [
        finding
        for artifact in manifest.artifacts
        for collection, entries in (
            (_ManifestCollection.INPUTS, artifact.inputs),
            (_ManifestCollection.OUTPUTS, artifact.outputs),
        )
        for entry in entries
        for finding in _verify_digest(root, policy, collection, entry)
    ]
    return (*inventory_findings, *findings)


def _verify_output_inventory(
    root: Path, policy: GeneratedPathPolicy, manifest: GeneratedManifest
) -> tuple[Finding, ...]:
    declared = tuple(output.path for artifact in manifest.artifacts for output in artifact.outputs)
    if len(declared) != len(set(declared)):
        raise GeneratedManifestError("manifest output paths must be globally unique")
    try:
        actual = enumerate_generated_outputs(root, policy.output_root, policy.manifest_path)
    except GeneratedInventoryError as error:
        raise GeneratedManifestError(str(error)) from error
    findings = [
        _manifest_finding(
            policy.manifest_path,
            f"generated output is not declared by exactly one artifact: {path}",
        )
        for path in sorted(actual - set(declared))
    ]
    findings.extend(
        _manifest_finding(
            policy.manifest_path,
            f"declared generated output is absent from the output root: {path}",
        )
        for path in sorted(set(declared) - actual)
    )
    return tuple(findings)


def _parse_manifest(value: object) -> GeneratedManifest:
    payload = _exact_object(
        value,
        "manifest",
        {GENERATED_NOTICE_FIELD, "schema", "artifacts"},
    )
    _require_exact(payload, GENERATED_NOTICE_FIELD, GENERATED_NOTICE, "manifest")
    _require_exact(payload, "schema", _MANIFEST_SCHEMA, "manifest")
    raw_artifacts = payload["artifacts"]
    if not isinstance(raw_artifacts, list):
        raise GeneratedManifestError("manifest artifacts must be a list")
    artifacts = tuple(_parse_artifact(item, index) for index, item in enumerate(raw_artifacts))
    identifiers = tuple(item.artifact_id for item in artifacts)
    if len(identifiers) != len(set(identifiers)):
        raise GeneratedManifestError("manifest artifact ids must be unique")
    return GeneratedManifest(artifacts)


def _parse_artifact(value: object, index: int) -> GeneratedArtifact:
    context = f"artifacts[{index}]"
    payload = _exact_object(
        value,
        context,
        {"id", "generator", "tool_version", "command", "inputs", "outputs"},
    )
    return GeneratedArtifact(
        artifact_id=_required_string(payload, "id", context),
        generator=_required_string(payload, "generator", context),
        tool_version=_required_string(payload, "tool_version", context),
        command=_required_string(payload, "command", context),
        inputs=_parse_digests(payload["inputs"], f"{context}.inputs"),
        outputs=_parse_digests(payload["outputs"], f"{context}.outputs"),
    )


def _parse_digests(value: object, context: str) -> tuple[GeneratedDigest, ...]:
    if not isinstance(value, list):
        raise GeneratedManifestError(f"{context} must be a list")
    entries = tuple(_parse_digest(item, f"{context}[{index}]") for index, item in enumerate(value))
    paths = tuple(item.path for item in entries)
    if len(paths) != len(set(paths)):
        raise GeneratedManifestError(f"{context} paths must be unique")
    return entries


def _parse_digest(value: object, context: str) -> GeneratedDigest:
    payload = _exact_object(value, context, {"path", "sha256"})
    path = _required_string(payload, "path", context)
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts or str(relative) != path:
        raise GeneratedManifestError(f"{context}.path must be normalized and repository-relative")
    sha256 = _required_string(payload, "sha256", context)
    if _DIGEST.fullmatch(sha256) is None:
        raise GeneratedManifestError(f"{context}.sha256 must be one lowercase sha256 digest")
    return GeneratedDigest(path, sha256)


def _exact_object(value: object, context: str, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise GeneratedManifestError(f"{context} fields must be exactly {sorted(fields)}")
    return cast(dict[str, object], value)


def _required_string(payload: dict[str, object], field: str, context: str) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value:
        raise GeneratedManifestError(f"{context}.{field} must be a non-empty string")
    return value


def _require_exact(payload: dict[str, object], field: str, expected: str, context: str) -> None:
    if payload[field] != expected:
        raise GeneratedManifestError(f"{context}.{field} must be {expected!r}")


def _verify_digest(
    root: Path,
    policy: GeneratedPathPolicy,
    collection: _ManifestCollection,
    entry: GeneratedDigest,
) -> tuple[Finding, ...]:
    try:
        path = _authorized_manifest_file(root, policy, collection, entry.path)
        content = path.read_bytes()
    except GeneratedManifestError as error:
        return (_manifest_finding(policy.manifest_path, str(error)),)
    except OSError:
        return (_drift_finding(entry.path, collection.value),)
    if digest_bytes(Path(entry.path), content).sha256 != entry.sha256:
        return (_drift_finding(entry.path, collection.value),)
    if collection is _ManifestCollection.OUTPUTS and path.suffix == ".json":
        notice_error = _generated_notice_error(content)
        if notice_error is not None:
            return (
                Finding(
                    rule_id="generated.notice",
                    path=entry.path,
                    message=notice_error,
                    severity=Severity.ERROR,
                    observed=1,
                    limit=0,
                ),
            )
    return ()


def _authorized_manifest_file(
    root: Path,
    policy: GeneratedPathPolicy,
    collection: _ManifestCollection,
    entry_path: str,
) -> Path:
    relative = _normalized_relative(entry_path, f"manifest {collection.value} path")
    if collection is _ManifestCollection.OUTPUTS:
        output_root = PurePosixPath(policy.output_root)
        if relative == output_root or not relative.is_relative_to(output_root):
            raise GeneratedManifestError(
                f"manifest outputs path must be strictly below {policy.output_root}/: {entry_path}"
            )
    elif not _is_allowed_input(relative, policy):
        raise GeneratedManifestError(
            f"manifest inputs path is outside explicit authored roots/files: {entry_path}"
        )
    return _regular_repository_file(root, relative, f"manifest {collection.value} path")


def _is_allowed_input(relative: PurePosixPath, policy: GeneratedPathPolicy) -> bool:
    if relative.as_posix() in policy.input_files:
        return True
    return any(
        relative != PurePosixPath(root) and relative.is_relative_to(PurePosixPath(root))
        for root in policy.input_roots
    )


def _normalized_relative(value: str, label: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if (
        not relative.parts
        or relative.is_absolute()
        or ".." in relative.parts
        or str(relative) != value
    ):
        raise GeneratedManifestError(f"{label} must be normalized and repository-relative")
    return relative


def _regular_repository_file(root: Path, relative: PurePosixPath, label: str) -> Path:
    canonical_root = _canonical_repository_root(root, label)
    current, mode = _walk_without_symlinks(canonical_root, relative, label)
    if not stat.S_ISREG(mode):
        raise GeneratedManifestError(f"{label} must be a regular file: {relative}")
    resolved = _resolve_existing(current, relative, label)
    if not resolved.is_relative_to(canonical_root):
        raise GeneratedManifestError(f"{label} resolves outside the repository: {relative}")
    return resolved


def _canonical_repository_root(root: Path, label: str) -> Path:
    try:
        return root.resolve(strict=True)
    except OSError as error:
        raise GeneratedManifestError(
            f"{label} repository root cannot be resolved: {error}"
        ) from error


def _walk_without_symlinks(
    canonical_root: Path, relative: PurePosixPath, label: str
) -> tuple[Path, int]:
    current = canonical_root
    mode = 0
    for index, part in enumerate(relative.parts):
        current /= part
        mode = _lstat_mode(current, relative, label)
        if stat.S_ISLNK(mode):
            raise GeneratedManifestError(f"{label} contains a symlink component: {relative}")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(mode):
            raise GeneratedManifestError(f"{label} parent is not a directory: {relative}")
    return current, mode


def _lstat_mode(path: Path, relative: PurePosixPath, label: str) -> int:
    try:
        return path.lstat().st_mode
    except OSError as error:
        raise GeneratedManifestError(f"{label} is missing or inaccessible: {relative}") from error


def _resolve_existing(path: Path, relative: PurePosixPath, label: str) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise GeneratedManifestError(f"{label} cannot be resolved: {relative}") from error


def _generated_notice_error(content: bytes) -> str | None:
    try:
        value: object = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "generated JSON output must be valid UTF-8 JSON with a do-not-edit notice"
    if not isinstance(value, dict) or value.get(GENERATED_NOTICE_FIELD) != GENERATED_NOTICE:
        return f"generated JSON output must contain exact {GENERATED_NOTICE_FIELD!r} notice"
    return None


def _manifest_finding(manifest_name: str, message: str) -> Finding:
    return Finding(
        rule_id="generated.manifest",
        path=manifest_name,
        message=message,
        severity=Severity.ERROR,
        observed=1,
        limit=0,
    )


def _drift_finding(path: str, collection: str) -> Finding:
    return Finding(
        rule_id="generated.drift",
        path=path,
        message=f"{collection} digest does not match generated manifest",
        severity=Severity.ERROR,
        observed=1,
        limit=0,
    )
