"""Build, write, and compare deterministic authored-contract traceability."""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from tools.checks._impl.generated import (
    GENERATED_NOTICE,
    GENERATED_NOTICE_FIELD,
    GeneratedArtifact,
    GeneratedManifestError,
    atomic_write_generated_text,
    digest_bytes,
    digest_file,
    load_generated_manifest,
    render_generated_manifest,
)

_SOURCE_PATH = "contracts/traceability/sources.json"
_OUTPUT_PATH = Path("generated/traceability-index.json")
_MANIFEST_PATH = Path("generated/.generated-manifest.json")
_ARTIFACT_ID = "contract-traceability-index"
_INPUT_PATHS = (
    Path("SPEC.md"),
    Path("contracts/traceability/sources.json"),
    Path("contracts/traceability/traceability-sources.schema.json"),
    Path("tools/checks/_impl/generated.py"),
    Path("tools/checks/_impl/traceability.py"),
    Path("tools/checks/traceability.py"),
)
_COVERAGE_EXEMPT = frozenset(
    {
        _SOURCE_PATH,
        "contracts/traceability/traceability-sources.schema.json",
    }
)
_REFERENCE = re.compile(r"^(?:SPEC#[a-z0-9][a-z0-9-]*|INV-[0-9]{2}|AC-[A-Z0-9]+-[0-9]{2})$")
_INVARIANT = re.compile(r"\*\*(INV-[0-9]{2})\s+—")
_ACCEPTANCE = re.compile(r"</a>(AC-[A-Z0-9]+-[0-9]{2})\s+\|")
_HEADING = re.compile(r"^#{2,6}\s+(.+?)\s*$", re.MULTILINE)


class TraceabilityError(ValueError):
    """Authored traceability or its generated representation is invalid."""


@dataclass(frozen=True, slots=True)
class TraceabilityIndex:
    """Stable reverse mapping from canonical reference to authored artifacts."""

    references: tuple[tuple[str, tuple[str, ...]], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            GENERATED_NOTICE_FIELD: GENERATED_NOTICE,
            "schema": "ctower.traceability-index/v1",
            "source": _SOURCE_PATH,
            "references": {reference: list(paths) for reference, paths in self.references},
        }


@dataclass(frozen=True, slots=True)
class _RenderedTraceability:
    index: str
    manifest: str


def write_traceability_artifacts(root: Path) -> None:
    """Atomically replace the committed index and manifest with canonical bytes."""

    resolved = root.resolve()
    _write_rendered(resolved, _render_artifacts(resolved))


def check_traceability_artifacts(root: Path) -> None:
    """Regenerate elsewhere and compare both committed generated files literally."""

    resolved = root.resolve()
    rendered = _render_artifacts(resolved)
    with tempfile.TemporaryDirectory(prefix="ctower-traceability-") as name:
        destination = Path(name)
        _write_rendered(destination, rendered)
        for relative in (_OUTPUT_PATH, _MANIFEST_PATH):
            _compare_generated_bytes(resolved, destination, relative)


def build_traceability_index(root: Path) -> TraceabilityIndex:
    """Validate the one authored source map and reverse it deterministically."""

    data = _load_source(root)
    known = _known_references(root)
    paths_seen: set[str] = set()
    reverse: dict[str, set[str]] = {}
    for index, raw_entry in enumerate(data):
        path, references = _parse_entry(raw_entry, index)
        if path in paths_seen:
            raise TraceabilityError(f"artifacts[{index}].path duplicates {path}")
        paths_seen.add(path)
        _validate_artifact(root, path, index)
        for reference in references:
            if reference not in known:
                raise TraceabilityError(f"artifacts[{index}] names unknown reference {reference}")
            reverse.setdefault(reference, set()).add(path)
    _validate_normative_coverage(root, paths_seen)
    return TraceabilityIndex(
        tuple((reference, tuple(sorted(paths))) for reference, paths in sorted(reverse.items()))
    )


def _render_artifacts(root: Path) -> _RenderedTraceability:
    index = json.dumps(build_traceability_index(root).to_dict(), indent=2, sort_keys=True) + "\n"
    try:
        manifest = load_generated_manifest(root, _MANIFEST_PATH)
        entry = GeneratedArtifact(
            artifact_id=_ARTIFACT_ID,
            generator="tools.checks.traceability",
            tool_version="2",
            command="python3 -m tools.checks.traceability --root . --write",
            inputs=tuple(digest_file(root, path) for path in _INPUT_PATHS),
            outputs=(digest_bytes(_OUTPUT_PATH, index.encode("utf-8")),),
        )
    except GeneratedManifestError as error:
        raise TraceabilityError(str(error)) from error
    return _RenderedTraceability(
        index=index, manifest=render_generated_manifest(manifest.upsert(entry))
    )


def _write_rendered(destination: Path, rendered: _RenderedTraceability) -> None:
    atomic_write_generated_text(destination, _OUTPUT_PATH, rendered.index)
    atomic_write_generated_text(destination, _MANIFEST_PATH, rendered.manifest)


def _compare_generated_bytes(source: Path, generated: Path, relative: Path) -> None:
    try:
        current = (source / relative).read_bytes()
        expected = (generated / relative).read_bytes()
    except OSError as error:
        raise TraceabilityError(f"cannot compare {relative.as_posix()}: {error}") from error
    if current != expected:
        raise TraceabilityError(f"{relative.as_posix()} is stale")


def _load_source(root: Path) -> list[object]:
    path = root / _SOURCE_PATH
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TraceabilityError(f"cannot load {_SOURCE_PATH}: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {"schema", "artifacts"}:
        raise TraceabilityError("traceability source needs exactly schema and artifacts")
    if payload["schema"] != "ctower.traceability-sources/v1":
        raise TraceabilityError("traceability source schema must be ctower.traceability-sources/v1")
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise TraceabilityError("traceability source artifacts must be a non-empty list")
    return artifacts


def _parse_entry(value: object, index: int) -> tuple[str, tuple[str, ...]]:
    if not isinstance(value, dict) or set(value) != {"path", "references"}:
        raise TraceabilityError(f"artifacts[{index}] needs exactly path and references")
    path = value["path"]
    if not isinstance(path, str):
        raise TraceabilityError(f"artifacts[{index}].path must be a string")
    return path, _parse_references(value["references"], index)


def _parse_references(value: object, index: int) -> tuple[str, ...]:
    references = value
    if not isinstance(references, list) or not references:
        raise TraceabilityError(f"artifacts[{index}].references must be non-empty")
    if not all(isinstance(item, str) and _REFERENCE.fullmatch(item) for item in references):
        raise TraceabilityError(f"artifacts[{index}].references contains an invalid stable ID")
    if len(references) != len(set(references)):
        raise TraceabilityError(f"artifacts[{index}].references contains a duplicate")
    return tuple(references)


def _validate_artifact(root: Path, value: str, index: int) -> None:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or str(path) != value
        or not path.parts
        or path.parts[0] not in {"contracts", "packs"}
    ):
        raise TraceabilityError(f"artifacts[{index}].path is not an authored contract path")
    if not (root / path).is_file():
        raise TraceabilityError(f"artifacts[{index}].path does not exist: {value}")


def _validate_normative_coverage(root: Path, mapped: set[str]) -> None:
    missing = tuple(path for path in _discover_normative_artifacts(root) if path not in mapped)
    if missing:
        raise TraceabilityError(f"unowned normative artifact: {', '.join(missing)}")


def _discover_normative_artifacts(root: Path) -> tuple[str, ...]:
    candidates = {
        path.relative_to(root).as_posix()
        for path in (root / "contracts").rglob("*.schema.json")
        if path.is_file()
    }
    for pattern in ("*.yaml", "*.yml"):
        candidates.update(
            path.relative_to(root).as_posix()
            for path in (root / "packs").rglob(pattern)
            if path.is_file()
        )
    return tuple(sorted(candidates - _COVERAGE_EXEMPT))


def _known_references(root: Path) -> set[str]:
    try:
        source = (root / "SPEC.md").read_text(encoding="utf-8")
    except OSError as error:
        raise TraceabilityError(f"cannot read SPEC.md: {error}") from error
    headings = {f"SPEC#{_heading_slug(title)}" for title in _HEADING.findall(source)}
    return headings | set(_INVARIANT.findall(source)) | set(_ACCEPTANCE.findall(source))


def _heading_slug(title: str) -> str:
    plain = re.sub(r"[`*_\[\]()]", "", title.lower())
    plain = re.sub(r"[^a-z0-9 -]", "", plain)
    return re.sub(r"-+", "-", re.sub(r"\s+", "-", plain)).strip("-")
