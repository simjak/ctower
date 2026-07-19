from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import sysconfig
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

Observation = dict[str, object]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    requirements = tuple(json.loads(arguments.requirements))
    observations = [
        _observe("runtime", lambda: _runtime(arguments.version)),
        _observe("dependency_resolution", lambda: _dependencies(requirements)),
        _observe("pydantic", _pydantic),
        _observe("fastapi", _fastapi),
        _observe("psycopg", _psycopg),
        _observe("opentelemetry", _opentelemetry),
        _observe("ruff", _ruff),
        _observe("mypy_pydantic_plugin", _mypy),
        _observe("jsonschema", _jsonschema),
        _observe("wheel", _wheel),
    ]
    runtime = observations[0]["details"]
    report = {
        "version": arguments.version,
        "status": "passed"
        if all(item["status"] == "passed" for item in observations)
        else "failed",
        "interpreter": runtime,
        "observations": observations,
    }
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if report["status"] == "passed" else 1


def _observe(observation_id: str, operation: Callable[[], dict[str, object]]) -> Observation:
    started = time.monotonic()
    try:
        details = operation()
        return {
            "id": observation_id,
            "status": "passed",
            "duration_ms": round((time.monotonic() - started) * 1000),
            "details": details,
        }
    except (
        AttributeError,
        ImportError,
        KeyError,
        OSError,
        RuntimeError,
        StopIteration,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        return {
            "id": observation_id,
            "status": "failed",
            "duration_ms": round((time.monotonic() - started) * 1000),
            "details": {"error_type": type(error).__name__, "error": str(error)},
        }


def _runtime(expected_version: str) -> dict[str, object]:
    version = platform.python_version()
    if version != expected_version:
        raise RuntimeError(f"expected Python {expected_version}, observed {version}")
    gil_enabled = _gil_enabled()
    if not gil_enabled:
        raise RuntimeError("free-threaded interpreter is forbidden")
    executable = Path(sys.executable)
    return {
        "version": version,
        "implementation": platform.python_implementation(),
        "free_threaded": not gil_enabled,
        "gil_enabled": gil_enabled,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "soabi": sysconfig.get_config_var("SOABI"),
        "cache_tag": sys.implementation.cache_tag,
        "py_gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED") or 0,
        "executable_sha256": _file_sha256(executable),
    }


def _gil_enabled() -> bool:
    probe = getattr(sys, "_is_gil_enabled", None)
    if probe is not None:
        return bool(probe())
    return sysconfig.get_config_var("Py_GIL_DISABLED") in (None, 0)


def _dependencies(requirements: tuple[str, ...]) -> dict[str, object]:
    expected = {
        item.split("==", 1)[0].split("[", 1)[0].lower(): item.split("==", 1)[1]
        for item in requirements
    }
    observed = {name: importlib.metadata.version(name) for name in expected}
    mismatches = {
        name: {"expected": expected[name], "observed": observed[name]}
        for name in expected
        if expected[name] != observed[name]
    }
    if mismatches:
        raise RuntimeError(f"dependency version mismatches: {mismatches}")
    return {"direct_versions": observed}


def _pydantic() -> dict[str, object]:
    return _python_json(
        """
import json
from pydantic import BaseModel, ConfigDict, ValidationError

class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    ticket_id: str
    attempts: int

accepted = Payload.model_validate({"ticket_id": "CT-L0-007", "attempts": 1})
try:
    Payload.model_validate({"ticket_id": "CT-L0-007", "attempts": 1, "unknown": True})
except ValidationError as error:
    if error.errors()[0]["type"] != "extra_forbidden":
        raise RuntimeError("wrong rejection reason") from error
else:
    raise RuntimeError("unknown field accepted")
print(json.dumps({"extra_fields": "forbidden", "frozen": accepted.model_config["frozen"]}))
"""
    )


def _fastapi() -> dict[str, object]:
    return _python_json(
        """
import fastapi
import hashlib
import json
from fastapi import FastAPI

application = FastAPI()
@application.get("/health", operation_id="compatibility_health")
def health() -> dict[str, str]:
    return {"status": "ok"}
schema = application.openapi()
if schema["paths"]["/health"]["get"]["operationId"] != "compatibility_health":
    raise RuntimeError("explicit operation ID was not preserved")
encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
print(json.dumps({
    "version": fastapi.__version__,
    "openapi": schema["openapi"],
    "schema_sha256": hashlib.sha256(encoded).hexdigest(),
}))
"""
    )


def _psycopg() -> dict[str, object]:
    return _python_json(
        """
import importlib.metadata
import json
import psycopg
import psycopg_pool

if not hasattr(psycopg, "Connection") or not hasattr(psycopg_pool, "ConnectionPool"):
    raise RuntimeError("public imports are incomplete")
print(json.dumps({
    "psycopg": importlib.metadata.version("psycopg"),
    "psycopg_pool": importlib.metadata.version("psycopg-pool"),
}))
"""
    )


def _opentelemetry() -> dict[str, object]:
    return _python_json(
        """
import importlib.metadata
import json
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
tracer = provider.get_tracer("ctower.compatibility")
with tracer.start_as_current_span("probe") as span:
    span.set_attribute("ctower.compatibility", True)
spans = exporter.get_finished_spans()
if len(spans) != 1:
    raise RuntimeError("expected exactly one exported span")
print(json.dumps({"api": importlib.metadata.version("opentelemetry-api"), "spans": len(spans)}))
"""
    )


def _ruff() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ctower-ruff-") as directory:
        source = Path(directory) / "typed.py"
        source.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
        result = _run(
            [sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", str(source)]
        )
    if result.returncode != 0:
        raise RuntimeError(f"Ruff failed: {result.stderr}")
    return _command_details(result)


def _mypy() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ctower-mypy-") as directory:
        root = Path(directory)
        config = root / "mypy.ini"
        config.write_text(
            "[mypy]\nstrict = True\nplugins = pydantic.mypy\n"
            "[pydantic-mypy]\ninit_forbid_extra = True\n"
            "init_typed = True\nwarn_untyped_fields = True\n",
            encoding="utf-8",
        )
        valid = root / "valid.py"
        valid.write_text(
            "from pydantic import BaseModel, ConfigDict\n"
            "class Value(BaseModel):\n"
            "    model_config = ConfigDict(extra='forbid')\n"
            "    count: int\n"
            "value: Value = Value(count=1)\n",
            encoding="utf-8",
        )
        invalid = root / "invalid.py"
        invalid.write_text(
            valid.read_text() + "bad: Value = Value(count=1, extra=True)\n", encoding="utf-8"
        )
        valid_result = _run(
            [sys.executable, "-m", "mypy", "--config-file", str(config), str(valid)]
        )
        invalid_result = _run(
            [sys.executable, "-m", "mypy", "--config-file", str(config), str(invalid)]
        )
    if valid_result.returncode != 0:
        raise RuntimeError(
            f"valid Pydantic model failed mypy: {valid_result.stdout}{valid_result.stderr}"
        )
    invalid_text = invalid_result.stdout + invalid_result.stderr
    if invalid_result.returncode == 0 or "Unexpected keyword argument" not in invalid_text:
        raise RuntimeError("Pydantic mypy plugin did not reject an extra constructor field")
    return {
        "valid": _command_details(valid_result),
        "invalid_exit_code": invalid_result.returncode,
        "extra_field_rejected": True,
    }


def _jsonschema() -> dict[str, object]:
    return _python_json(
        """
import hashlib
import importlib.metadata
import json
import jsonschema
from pydantic import BaseModel, ConfigDict

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str

schema = Contract.model_json_schema()
validator = jsonschema.Draft202012Validator(schema)
validator.validate({"name": "ctower"})
if len(list(validator.iter_errors({"name": "ctower", "extra": True}))) != 1:
    raise RuntimeError("expected exactly one additional-property error")
encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
print(json.dumps({
    "version": importlib.metadata.version("jsonschema"),
    "schema_sha256": hashlib.sha256(encoded).hexdigest(),
}))
"""
    )


def _python_json(source: str) -> dict[str, object]:
    result = _run([sys.executable, "-c", source])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Python compatibility sub-probe failed")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Python compatibility sub-probe returned malformed JSON") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError("Python compatibility sub-probe must return a JSON object")
    return value


def _wheel() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ctower-wheel-") as directory:
        root = Path(directory)
        package = root / "src" / "ctower_compat_wheel"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("MARKER = 'ctower-wheel-ok'\n", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            "[build-system]\nrequires = ['setuptools==83.0.0', 'wheel==0.47.0']\n"
            "build-backend = 'setuptools.build_meta'\n"
            "[project]\nname = 'ctower-compat-wheel'\nversion = '0.0.1'\n",
            encoding="utf-8",
        )
        build = _run([sys.executable, "-m", "build", "--wheel", "--no-isolation", str(root)])
        if build.returncode != 0:
            raise RuntimeError(f"wheel build failed: {build.stdout}{build.stderr}")
        wheel = next((root / "dist").glob("*.whl"))
        install_root = root / "install"
        venv = _run([sys.executable, "-m", "venv", str(install_root)])
        if venv.returncode != 0:
            raise RuntimeError(f"wheel venv failed: {venv.stderr}")
        install_python = install_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = _run([str(install_python), "-m", "pip", "install", "--no-deps", str(wheel)])
        if install.returncode != 0:
            raise RuntimeError(f"wheel install failed: {install.stdout}{install.stderr}")
        imported = _run(
            [str(install_python), "-c", "import ctower_compat_wheel as w; print(w.MARKER)"]
        )
        if imported.returncode != 0 or imported.stdout.strip() != "ctower-wheel-ok":
            raise RuntimeError("installed wheel import smoke failed")
        return {
            "wheel_sha256": _file_sha256(wheel),
            "build": _command_details(build),
            "install": _command_details(install),
            "imported": True,
        }


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "SOURCE_DATE_EPOCH": "0",
    }
    return _spawn(command, environment)


def _command_details(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return {"exit_code": result.returncode}


def _spawn(command: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        actions = [
            (os.POSIX_SPAWN_DUP2, stdout.fileno(), 1),
            (os.POSIX_SPAWN_DUP2, stderr.fileno(), 2),
        ]
        process_id = os.posix_spawn(command[0], command, environment, file_actions=actions)
        _, raw_status = os.waitpid(process_id, 0)
        stdout.seek(0)
        stderr.seek(0)
        return subprocess.CompletedProcess(
            command,
            os.waitstatus_to_exitcode(raw_status),
            stdout.read().decode(errors="replace"),
            stderr.read().decode(errors="replace"),
        )


def _json_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
