from __future__ import annotations

import hashlib
from pathlib import Path

from tools.compatibility.models_core import CompatibilityMatrix
from tools.compatibility.schema import JsonObject

__all__ = ()

ROOT_DIGEST = "a" * 64
ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "contracts" / "compatibility" / "ct-l0-007-matrix.json"


def report_payload(matrix: CompatibilityMatrix) -> JsonObject:
    """Build closed, externally supplied fixture evidence for public boundary tests."""
    telemetry = matrix.telemetry.model_dump(mode="json", by_alias=True)
    runs = [
        _run(matrix, candidate.version, environment, telemetry)
        for candidate in matrix.candidates
        for environment in ("macos-host", "linux-container")
    ]
    return {
        "schema": "ctower.compatibility-result/v1",
        "evidence_scope": "external-runner-noncanonical",
        "input_digest": matrix.digest,
        "matrix_id": matrix.matrix_id,
        "telemetry": telemetry,
        "runs": runs,
    }


def _run(
    matrix: CompatibilityMatrix,
    version: str,
    environment: str,
    telemetry: dict[str, object],
) -> dict[str, object]:
    candidate = next(item for item in matrix.candidates if item.version == version)
    linux = environment == "linux-container"
    runtime = _runtime(version, linux=linux)
    lock_payload = ("\n".join(matrix.requirements) + "\n").encode()
    image = None
    if linux:
        image = {
            "requested": candidate.linux_image,
            "image_id": candidate.linux_image.rsplit("@", 1)[1],
            "os": "linux",
            "architecture": "arm64",
        }
    return {
        "version": version,
        "status": "passed",
        "interpreter": runtime,
        "observations": _observations(runtime, matrix.requirements),
        "telemetry": telemetry,
        "environment": environment,
        "host_identity": {"system": "Linux" if linux else "Darwin", "machine": "arm64"},
        "resolution": {
            "lock": list(matrix.requirements),
            "lock_sha256": hashlib.sha256(lock_payload).hexdigest(),
        },
        "product_artifacts": {
            "release_helper_wheel": {
                "status": "not_exercised",
                "reason_code": "artifact_absent",
            },
            "generated_clients": {
                "status": "not_exercised",
                "reason_code": "artifact_absent",
            },
        },
        "image_identity": image,
    }


def _runtime(version: str, *, linux: bool) -> dict[str, object]:
    parts = version.split(".")
    abi = f"{parts[0]}{parts[1]}"
    return {
        "version": version,
        "implementation": "CPython",
        "free_threaded": False,
        "gil_enabled": True,
        "system": "Linux" if linux else "Darwin",
        "platform": "linux-arm64" if linux else "macos-arm64",
        "machine": "arm64",
        "soabi": f"cpython-{abi}-aarch64-linux-gnu" if linux else f"cpython-{abi}-darwin",
        "cache_tag": f"cpython-{abi}",
        "py_gil_disabled": 0,
        "executable_sha256": ROOT_DIGEST,
    }


def _observations(
    runtime: dict[str, object], requirements: tuple[str, ...]
) -> list[dict[str, object]]:
    direct = [
        {"name": item.split("==", 1)[0], "version": item.split("==", 1)[1]} for item in requirements
    ]
    details: tuple[tuple[str, object], ...] = (
        ("runtime", runtime),
        ("dependency_resolution", {"direct_versions": direct}),
        ("pydantic", {"extra_fields": "forbidden", "frozen": True}),
        ("fastapi", {"version": "0.139.2", "openapi": "3.1.0", "schema_sha256": ROOT_DIGEST}),
        ("psycopg", {"psycopg": "3.3.4", "psycopg_pool": "3.3.1"}),
        ("opentelemetry", {"api": "1.44.0", "spans": 1}),
        ("ruff", {"exit_code": 0}),
        (
            "mypy_pydantic_plugin",
            {"valid": {"exit_code": 0}, "invalid_exit_code": 1, "extra_field_rejected": True},
        ),
        ("jsonschema", {"version": "4.26.0", "schema_sha256": ROOT_DIGEST}),
        (
            "wheel",
            {
                "wheel_sha256": ROOT_DIGEST,
                "build": {"exit_code": 0},
                "install": {"exit_code": 0},
                "imported": True,
            },
        ),
    )
    return [
        {"id": identifier, "status": "passed", "duration_ms": 1, "details": value}
        for identifier, value in details
    ]
