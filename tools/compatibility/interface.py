from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

from tools.compatibility.contract import Candidate, CompatibilityError, CompatibilityMatrix
from tools.compatibility.execution import execute_candidate_matrix

_ROOT_KEYS = {
    "schema",
    "matrix_id",
    "uv_version",
    "requirements",
    "required_observations",
    "product_artifacts",
    "candidates",
}
_CANDIDATE_KEYS = {
    "version",
    "gil",
    "release_date",
    "release_url",
    "source_url",
    "source_sha256",
    "linux_image",
}
_RUN_KEYS = {
    "version",
    "environment",
    "status",
    "interpreter",
    "observations",
    "product_artifacts",
}
_VERSIONS = ("3.12.13", "3.13.14", "3.14.6")
_ENVIRONMENTS = ("macos-host", "linux-container")
_ARTIFACT_REASON = {"status": "not_exercised", "reason_code": "artifact_absent"}
_PRIVATE_PATH = re.compile(
    r"(?:/Users/[^/]+|/home/[^/]+|/var/folders/|/private/var/folders/|/tmp/)"
)
_SHA256_LENGTH = 64


def load_matrix(path: Path) -> CompatibilityMatrix:
    """Load and strictly validate one immutable compatibility input."""
    raw = _read_object(path)
    _require_exact_keys(raw, _ROOT_KEYS, "matrix")
    if raw["schema"] != "ctower.compatibility-input/v1":
        raise CompatibilityError("unsupported matrix schema")
    requirements = _string_tuple(raw["requirements"], "requirements")
    if any(item.count("==") != 1 for item in requirements):
        raise CompatibilityError("every compatibility requirement must be exactly pinned")
    observations = _string_tuple(raw["required_observations"], "required_observations")
    artifacts = _string_tuple(raw["product_artifacts"], "product_artifacts")
    candidates = _parse_candidates(raw["candidates"])
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return CompatibilityMatrix(
        matrix_id=_required_string(raw["matrix_id"], "matrix_id"),
        uv_version=_required_string(raw["uv_version"], "uv_version"),
        requirements=requirements,
        required_observations=observations,
        product_artifacts=artifacts,
        candidates=candidates,
        digest=f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
    )


def execute_matrix(
    matrix: CompatibilityMatrix,
    *,
    environments: tuple[str, ...] = _ENVIRONMENTS,
) -> dict[str, object]:
    """Execute the requested clean host/container matrix and return typed evidence."""
    _validate_environments(environments)
    report: dict[str, object] = {
        "schema": "ctower.compatibility-result/v1",
        "input_digest": matrix.digest,
        "matrix_id": matrix.matrix_id,
        "runs": execute_candidate_matrix(matrix, environments),
    }
    validate_report(matrix, report, environments=environments)
    return report


def validate_report(
    matrix: CompatibilityMatrix,
    report: dict[str, object],
    *,
    environments: tuple[str, ...] = ("macos-host",),
) -> None:
    """Reject incomplete, stale, malformed, skipped, or free-threaded evidence."""
    _validate_environments(environments)
    _validate_report_header(matrix, report)
    runs = report["runs"]
    if not isinstance(runs, list):
        raise CompatibilityError("runs must be an array")
    _validate_run_set(runs, environments)
    for run in runs:
        if not isinstance(run, dict):
            raise CompatibilityError("every run must be an object")
        _validate_run(matrix, run)


def write_report(path: Path, report: dict[str, object]) -> None:
    """Write canonical public report bytes without leaking private host paths."""
    if path.is_symlink():
        raise CompatibilityError("report path cannot be a symlink")
    encoded = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if _PRIVATE_PATH.search(encoded):
        raise CompatibilityError("public report contains a private host or temporary path")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_object(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CompatibilityError(f"invalid matrix JSON: {error}") from error
    if not isinstance(raw, dict):
        raise CompatibilityError("matrix root must be an object")
    return raw


def _parse_candidates(value: object) -> tuple[Candidate, ...]:
    if not isinstance(value, list):
        raise CompatibilityError("candidates must be an array")
    candidates = tuple(_parse_candidate(item) for item in value)
    if tuple(candidate.version for candidate in candidates) != _VERSIONS:
        raise CompatibilityError(f"candidate versions must be exactly {_VERSIONS!r}")
    return candidates


def _parse_candidate(value: object) -> Candidate:
    if not isinstance(value, dict):
        raise CompatibilityError("every candidate must be an object")
    _require_exact_keys(value, _CANDIDATE_KEYS, "candidate")
    strings = {key: _required_string(value[key], key) for key in _CANDIDATE_KEYS}
    if strings["gil"] != "required":
        raise CompatibilityError("every candidate must require the standard GIL")
    if "@sha256:" not in strings["linux_image"]:
        raise CompatibilityError("Linux image must use an immutable digest")
    if len(strings["source_sha256"]) != _SHA256_LENGTH:
        raise CompatibilityError("source SHA-256 must contain 64 hexadecimal characters")
    return Candidate(**strings)


def _validate_environments(environments: tuple[str, ...]) -> None:
    unknown = set(environments) - set(_ENVIRONMENTS)
    if unknown or not environments or len(set(environments)) != len(environments):
        raise CompatibilityError(f"unsupported environments: {sorted(unknown)!r}")


def _validate_report_header(matrix: CompatibilityMatrix, report: dict[str, object]) -> None:
    _require_exact_keys(report, {"schema", "input_digest", "matrix_id", "runs"}, "report")
    if report["schema"] != "ctower.compatibility-result/v1":
        raise CompatibilityError("unsupported result schema")
    if report["input_digest"] != matrix.digest:
        raise CompatibilityError("report input digest does not match current matrix")
    if report["matrix_id"] != matrix.matrix_id:
        raise CompatibilityError("report matrix ID does not match current matrix")


def _validate_run_set(runs: list[object], environments: tuple[str, ...]) -> None:
    expected = [(version, environment) for version in _VERSIONS for environment in environments]
    observed = [
        (run.get("version"), run.get("environment")) for run in runs if isinstance(run, dict)
    ]
    if sorted(observed) != sorted(expected):
        raise CompatibilityError("candidate runs do not exactly match the requested matrix")


def _validate_run(matrix: CompatibilityMatrix, run: dict[str, object]) -> None:
    allowed = _RUN_KEYS | {"image"}
    if set(run) - allowed or not _RUN_KEYS.issubset(run):
        raise CompatibilityError("malformed run fields")
    if run["status"] != "passed":
        raise CompatibilityError(f"candidate {run['version']} did not pass")
    _validate_interpreter(run)
    _validate_observations(matrix, run["observations"])
    _validate_artifacts(matrix, run["product_artifacts"])


def _validate_interpreter(run: dict[str, object]) -> None:
    interpreter = run["interpreter"]
    if not isinstance(interpreter, dict) or interpreter.get("version") != run["version"]:
        raise CompatibilityError("interpreter version does not match candidate")
    if interpreter.get("free_threaded") is not False:
        raise CompatibilityError("standard GIL evidence is required")
    if run["environment"] == "linux-container" and "@sha256:" not in str(run.get("image", "")):
        raise CompatibilityError("Linux evidence must name an immutable image")


def _validate_observations(matrix: CompatibilityMatrix, value: object) -> None:
    if not isinstance(value, list):
        raise CompatibilityError("observations must be an array")
    by_id = {item.get("id"): item for item in value if isinstance(item, dict)}
    if set(by_id) != set(matrix.required_observations):
        raise CompatibilityError("required observation set is incomplete or contains extras")
    failed = [
        name for name in matrix.required_observations if by_id[name].get("status") != "passed"
    ]
    if failed:
        raise CompatibilityError(f"required observation {failed[0]} was not passed")
    runtime = by_id["runtime"].get("details")
    if not isinstance(runtime, dict) or runtime.get("gil_enabled") is not True:
        raise CompatibilityError("standard GIL runtime observation is required")


def _validate_artifacts(matrix: CompatibilityMatrix, value: object) -> None:
    if not isinstance(value, dict) or set(value) != set(matrix.product_artifacts):
        raise CompatibilityError("product artifact evidence is incomplete")
    if any(artifact != _ARTIFACT_REASON for artifact in value.values()):
        raise CompatibilityError("absent product artifacts must be explicitly not_exercised")


def _require_exact_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise CompatibilityError(f"{label} fields must be exactly {sorted(expected)!r}")


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise CompatibilityError(f"{label} must be a non-empty string array")
    if not all(isinstance(item, str) and item for item in value):
        raise CompatibilityError(f"{label} must be a non-empty string array")
    result = tuple(value)
    if len(set(result)) != len(result):
        raise CompatibilityError(f"{label} must not contain duplicates")
    return result


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CompatibilityError(f"{label} must be a non-empty string")
    return value
