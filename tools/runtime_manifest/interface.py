"""Deterministic provenance binding for the unprivileged E2 runtime artifact."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

import tools.process_execution as process_execution  # noqa: PLR0402

__all__ = ["DevelopmentRuntimeManifest", "build_manifest", "verify_manifest"]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_GIT_TIMEOUT_SECONDS = 30.0
_INTERPRETER_TIMEOUT_SECONDS = 10.0


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ArtifactPin(_StrictModel):
    filename: str
    sha256: str

    @field_validator("sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("artifact pin must be a lowercase SHA-256 digest")
        return value


class PythonPin(_StrictModel):
    implementation: Literal["CPython"]
    version: Literal["3.14.6", "3.13.14"]
    gil: Literal["standard"]


class DevelopmentRuntimeManifest(_StrictModel):
    schema_id: Literal["ctower.development-runtime-artifact/v1"] = Field(alias="schema")
    label: Literal["SHADOW_ONLY_CP3_D_NOT_PROVEN"]
    source_commit: str
    source_tree: str
    python: PythonPin
    wheel: ArtifactPin
    migration_manifest_sha256: str
    generated_manifest_sha256: str
    packs_sha256: str

    @field_validator("source_commit", "source_tree")
    @classmethod
    def _git_object(cls, value: str) -> str:
        if _COMMIT.fullmatch(value) is None:
            raise ValueError("source provenance must be an exact Git object")
        return value

    @field_validator(
        "migration_manifest_sha256",
        "generated_manifest_sha256",
        "packs_sha256",
    )
    @classmethod
    def _bound_digest(cls, value: str) -> str:
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("runtime provenance must use lowercase SHA-256")
        return value


def build_manifest(
    source_root: Path,
    wheel: Path,
    output: Path,
    *,
    python_executable: Path,
) -> DevelopmentRuntimeManifest:
    """Bind one clean source tree, wheel, runtime, contracts, migrations, and packs."""

    if _git(source_root, "status", "--porcelain"):
        raise ValueError("runtime manifests require a clean source tree")
    version, gil = _python_identity(python_executable)
    manifest = DevelopmentRuntimeManifest.model_validate(
        {
            "schema": "ctower.development-runtime-artifact/v1",
            "label": "SHADOW_ONLY_CP3_D_NOT_PROVEN",
            "source_commit": _git(source_root, "rev-parse", "HEAD"),
            "source_tree": _git(source_root, "rev-parse", "HEAD^{tree}"),
            "python": {
                "implementation": "CPython",
                "version": version,
                "gil": gil,
            },
            "wheel": {"filename": wheel.name, "sha256": _digest_file(wheel)},
            "migration_manifest_sha256": _digest_file(
                source_root / "packages/ctower-kernel/migrations/manifest.json"
            ),
            "generated_manifest_sha256": _digest_file(
                source_root / "generated/.generated-manifest.json"
            ),
            "packs_sha256": _digest_tree(source_root / "packs"),
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(manifest.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(
    manifest_path: Path,
    wheel: Path,
    packs: Path,
    *,
    source_root: Path,
    python_executable: Path,
) -> DevelopmentRuntimeManifest:
    """Fail closed when installed bytes differ from any bound runtime fact."""

    manifest = DevelopmentRuntimeManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    version, gil = _python_identity(python_executable)
    observed = (
        _git(source_root, "rev-parse", "HEAD"),
        _git(source_root, "rev-parse", "HEAD^{tree}"),
        wheel.name,
        _digest_file(wheel),
        _digest_file(source_root / "packages/ctower-kernel/migrations/manifest.json"),
        _digest_file(source_root / "generated/.generated-manifest.json"),
        _digest_tree(packs),
        _digest_tree(source_root / "packs"),
        version,
        gil,
    )
    expected = (
        manifest.source_commit,
        manifest.source_tree,
        manifest.wheel.filename,
        manifest.wheel.sha256,
        manifest.migration_manifest_sha256,
        manifest.generated_manifest_sha256,
        manifest.packs_sha256,
        manifest.packs_sha256,
        manifest.python.version,
        manifest.python.gil,
    )
    if observed != expected:
        raise ValueError("runtime source, artifact, interpreter, or resources differ from manifest")
    return manifest


def _python_identity(executable: Path) -> tuple[str, str]:
    script = (
        "import platform,sys;"
        "print(platform.python_implementation());"
        "print(platform.python_version());"
        "print('standard' if not hasattr(sys,'_is_gil_enabled') "
        "or sys._is_gil_enabled() else 'free')"
    )
    resolved = executable.resolve(strict=True)
    result = process_execution.run(
        [str(resolved), "-c", script],
        timeout_seconds=_INTERPRETER_TIMEOUT_SECONDS,
        check=True,
        capture_output=True,
    )
    implementation, version, gil = result.stdout.splitlines()
    if implementation != "CPython" or version not in {"3.14.6", "3.13.14"} or gil != "standard":
        raise ValueError("runtime Python is not the approved exact standard-GIL interpreter")
    return version, gil


def _git(root: Path, *arguments: str) -> str:
    result = process_execution.run(
        ["/usr/bin/git", "-C", str(root), *arguments],
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
        check=True,
        capture_output=True,
    )
    return (result.stdout or "").strip()


def _digest_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"
