from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ValidationError

from .models_core import (
    EXPECTED_REQUIREMENTS,
    CompatibilityError,
    EnvironmentVariable,
    ProcessRequest,
    ProcessResult,
    PythonVersion,
    ResolvedDependency,
    TelemetryContext,
)
from .models_probe import (
    CommandDetails,
    DependencyDetails,
    DependencyObservation,
    FastapiDetails,
    FastapiObservation,
    JsonschemaDetails,
    JsonschemaObservation,
    MypyDetails,
    MypyObservation,
    Observation,
    OpentelemetryDetails,
    OpentelemetryObservation,
    ProbeResult,
    PsycopgDetails,
    PsycopgObservation,
    PydanticDetails,
    PydanticObservation,
    RuffObservation,
    RuntimeObservation,
    WheelDetails,
    WheelObservation,
)
from .process import ExecutionPort, LocalExecutionPort, ProbePort

__all__ = ["collect_probe", "main"]

_PROBE_TIMEOUT_MS = 180_000
_OUTPUT_LIMIT = 65_536


def main(argv: tuple[str, ...] | None = None, *, execution_port: ProbePort | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one contained compatibility probe")
    parser.add_argument("--version", required=True, choices=("3.12.13", "3.13.14", "3.14.6"))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    telemetry = _read_telemetry()
    report = collect_probe(
        cast("PythonVersion", arguments.version), telemetry, execution_port=execution_port
    )
    _write_probe(arguments.output, report)
    return 0


def collect_probe(
    version: PythonVersion,
    telemetry: TelemetryContext,
    *,
    execution_port: ProbePort | None = None,
) -> ProbeResult:
    """Collect the fixed observations through the bounded public execution port."""
    port = execution_port or LocalExecutionPort()
    runtime, runtime_ms = _timed(lambda: port.runtime_details(version))
    dependencies, dependencies_ms = _timed(lambda: _dependencies(port))
    pydantic, pydantic_ms = _timed(lambda: _pydantic(port, telemetry))
    fastapi, fastapi_ms = _timed(lambda: _fastapi(port, telemetry))
    psycopg, psycopg_ms = _timed(lambda: _psycopg(port, telemetry))
    opentelemetry, opentelemetry_ms = _timed(lambda: _opentelemetry(port, telemetry))
    ruff, ruff_ms = _timed(lambda: _ruff(port, telemetry))
    mypy, mypy_ms = _timed(lambda: _mypy(port, telemetry))
    jsonschema, jsonschema_ms = _timed(lambda: _jsonschema(port, telemetry))
    wheel, wheel_ms = _timed(lambda: _wheel(port, telemetry))
    observations: tuple[Observation, ...] = (
        RuntimeObservation(id="runtime", status="passed", duration_ms=runtime_ms, details=runtime),
        DependencyObservation(
            id="dependency_resolution",
            status="passed",
            duration_ms=dependencies_ms,
            details=dependencies,
        ),
        PydanticObservation(
            id="pydantic", status="passed", duration_ms=pydantic_ms, details=pydantic
        ),
        FastapiObservation(id="fastapi", status="passed", duration_ms=fastapi_ms, details=fastapi),
        PsycopgObservation(id="psycopg", status="passed", duration_ms=psycopg_ms, details=psycopg),
        OpentelemetryObservation(
            id="opentelemetry",
            status="passed",
            duration_ms=opentelemetry_ms,
            details=opentelemetry,
        ),
        RuffObservation(id="ruff", status="passed", duration_ms=ruff_ms, details=ruff),
        MypyObservation(
            id="mypy_pydantic_plugin", status="passed", duration_ms=mypy_ms, details=mypy
        ),
        JsonschemaObservation(
            id="jsonschema", status="passed", duration_ms=jsonschema_ms, details=jsonschema
        ),
        WheelObservation(id="wheel", status="passed", duration_ms=wheel_ms, details=wheel),
    )
    return ProbeResult(
        version=version,
        status="passed",
        interpreter=runtime,
        observations=observations,
        telemetry=telemetry,
    )


def _read_telemetry() -> TelemetryContext:
    raw = os.environ.get("CTOWER_TELEMETRY_CONTEXT")
    if raw is None:
        raise CompatibilityError("compatibility probe is missing telemetry context")
    try:
        return TelemetryContext.model_validate_json(raw)
    except ValidationError as error:
        raise CompatibilityError("compatibility probe telemetry is malformed") from error


def _dependencies(port: ProbePort) -> DependencyDetails:
    dependencies = tuple(
        ResolvedDependency(
            name=requirement.split("==", 1)[0],
            version=port.distribution_version(requirement.split("==", 1)[0]),
        )
        for requirement in EXPECTED_REQUIREMENTS
    )
    return DependencyDetails(direct_versions=dependencies)


def _pydantic(port: ExecutionPort, telemetry: TelemetryContext) -> PydanticDetails:
    return _python_model(
        port,
        telemetry,
        PydanticDetails,
        """
import json
from pydantic import BaseModel, ConfigDict, ValidationError
class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    ticket_id: str
accepted = Payload.model_validate({"ticket_id": "CT-L0-007"})
try:
    Payload.model_validate({"ticket_id": "CT-L0-007", "unknown": True})
except ValidationError:
    pass
else:
    raise RuntimeError("unknown field accepted")
print(json.dumps({"extra_fields": "forbidden", "frozen": accepted.model_config["frozen"]}))
""",
    )


def _fastapi(port: ExecutionPort, telemetry: TelemetryContext) -> FastapiDetails:
    return _python_model(
        port,
        telemetry,
        FastapiDetails,
        """
import fastapi, hashlib, json
from fastapi import FastAPI
application = FastAPI()
@application.get("/health", operation_id="compatibility_health")
def health() -> dict[str, str]: return {"status": "ok"}
schema = application.openapi()
encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
print(json.dumps({"version": fastapi.__version__, "openapi": schema["openapi"],
                  "schema_sha256": hashlib.sha256(encoded).hexdigest()}))
""",
    )


def _psycopg(port: ExecutionPort, telemetry: TelemetryContext) -> PsycopgDetails:
    return _python_model(
        port,
        telemetry,
        PsycopgDetails,
        """
import importlib.metadata, json, psycopg, psycopg_pool
if not hasattr(psycopg, "Connection") or not hasattr(psycopg_pool, "ConnectionPool"):
    raise RuntimeError("public imports are incomplete")
print(json.dumps({"psycopg": importlib.metadata.version("psycopg"),
                  "psycopg_pool": importlib.metadata.version("psycopg-pool")}))
""",
    )


def _opentelemetry(port: ExecutionPort, telemetry: TelemetryContext) -> OpentelemetryDetails:
    return _python_model(
        port,
        telemetry,
        OpentelemetryDetails,
        """
import importlib.metadata, json
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
exporter = InMemorySpanExporter(); provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
with provider.get_tracer("ctower.compatibility").start_as_current_span("probe"): pass
spans = exporter.get_finished_spans()
print(json.dumps({"api": importlib.metadata.version("opentelemetry-api"), "spans": len(spans)}))
""",
    )


def _ruff(port: ExecutionPort, telemetry: TelemetryContext) -> CommandDetails:
    with tempfile.TemporaryDirectory(prefix="ctower-ruff-") as directory:
        source = Path(directory) / "typed.py"
        source.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
        result = _checked(
            port,
            telemetry,
            (sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", str(source)),
        )
    return CommandDetails(exit_code=cast("Literal[0]", result.returncode))


def _mypy(port: ExecutionPort, telemetry: TelemetryContext) -> MypyDetails:
    with tempfile.TemporaryDirectory(prefix="ctower-mypy-") as directory:
        root = Path(directory)
        config = root / "mypy.ini"
        config.write_text(
            "[mypy]\nstrict = True\nplugins = pydantic.mypy\n"
            "[pydantic-mypy]\ninit_forbid_extra = True\ninit_typed = True\n",
            encoding="utf-8",
        )
        valid = root / "valid.py"
        valid.write_text(
            "from pydantic import BaseModel, ConfigDict\n"
            "class Value(BaseModel):\n    model_config = ConfigDict(extra='forbid')\n"
            "    count: int\nvalue: Value = Value(count=1)\n",
            encoding="utf-8",
        )
        invalid = root / "invalid.py"
        invalid.write_text(valid.read_text() + "bad: Value = Value(count=1, extra=True)\n")
        valid_result = _checked(
            port,
            telemetry,
            (sys.executable, "-m", "mypy", "--config-file", str(config), str(valid)),
        )
        invalid_result = _run(
            port,
            telemetry,
            (sys.executable, "-m", "mypy", "--config-file", str(config), str(invalid)),
        )
    invalid_text = invalid_result.stdout + invalid_result.stderr
    if invalid_result.returncode != 1 or "Unexpected keyword argument" not in invalid_text:
        raise CompatibilityError("Pydantic mypy plugin did not reject an extra field")
    return MypyDetails(
        valid=CommandDetails(exit_code=cast("Literal[0]", valid_result.returncode)),
        invalid_exit_code=1,
        extra_field_rejected=True,
    )


def _jsonschema(port: ExecutionPort, telemetry: TelemetryContext) -> JsonschemaDetails:
    return _python_model(
        port,
        telemetry,
        JsonschemaDetails,
        """
import hashlib, importlib.metadata, json, jsonschema
from pydantic import BaseModel, ConfigDict
class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
schema = Contract.model_json_schema(); validator = jsonschema.Draft202012Validator(schema)
validator.validate({"name": "ctower"})
if len(list(validator.iter_errors({"name": "ctower", "extra": True}))) != 1:
    raise RuntimeError("expected one additional-property error")
encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
print(json.dumps({"version": importlib.metadata.version("jsonschema"),
                  "schema_sha256": hashlib.sha256(encoded).hexdigest()}))
""",
    )


def _wheel(port: ExecutionPort, telemetry: TelemetryContext) -> WheelDetails:
    with tempfile.TemporaryDirectory(prefix="ctower-wheel-") as directory:
        root = Path(directory)
        package = root / "src" / "ctower_compat_wheel"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("MARKER = 'ctower-wheel-ok'\n")
        (root / "pyproject.toml").write_text(
            "[build-system]\nrequires = ['setuptools==83.0.0', 'wheel==0.47.0']\n"
            "build-backend = 'setuptools.build_meta'\n"
            "[project]\nname = 'ctower-compat-wheel'\nversion = '0.0.1'\n"
        )
        build = _checked(
            port,
            telemetry,
            (sys.executable, "-m", "build", "--wheel", "--no-isolation", str(root)),
        )
        wheel = next((root / "dist").glob("*.whl"))
        install_root = root / "install"
        _checked(port, telemetry, (sys.executable, "-m", "venv", str(install_root)))
        install_python = install_root / "bin" / "python"
        install = _checked(
            port,
            telemetry,
            (str(install_python), "-m", "pip", "install", "--no-deps", str(wheel)),
        )
        imported = _checked(
            port,
            telemetry,
            (str(install_python), "-c", "import ctower_compat_wheel as w; print(w.MARKER)"),
        )
        if imported.stdout.strip() != "ctower-wheel-ok":
            raise CompatibilityError("installed wheel import smoke returned the wrong marker")
        return WheelDetails(
            wheel_sha256=_file_sha256(wheel),
            build=CommandDetails(exit_code=cast("Literal[0]", build.returncode)),
            install=CommandDetails(exit_code=cast("Literal[0]", install.returncode)),
            imported=True,
        )


def _python_model[Detail: BaseModel](
    port: ExecutionPort,
    telemetry: TelemetryContext,
    model: type[Detail],
    source: str,
) -> Detail:
    result = _checked(port, telemetry, (sys.executable, "-c", source))
    try:
        return model.model_validate_json(result.stdout)
    except ValidationError as error:
        raise CompatibilityError("compatibility sub-probe returned malformed evidence") from error


def _checked(
    port: ExecutionPort, telemetry: TelemetryContext, argv: tuple[str, ...]
) -> ProcessResult:
    result = _run(port, telemetry, argv)
    if result.stdout_truncated or result.stderr_truncated:
        raise CompatibilityError("probe subprocess produced incomplete output")
    if result.failure_reason is not None or result.timed_out or result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise CompatibilityError(f"probe subprocess failed: {message[-1000:]}")
    return result


def _run(port: ExecutionPort, telemetry: TelemetryContext, argv: tuple[str, ...]) -> ProcessResult:
    return port.run(
        ProcessRequest(
            operation="probe-subprocess",
            argv=argv,
            environment=_child_environment(telemetry),
            timeout_ms=_PROBE_TIMEOUT_MS,
            terminate_grace_ms=2_000,
            output_limit_bytes=_OUTPUT_LIMIT,
        )
    )


def _child_environment(telemetry: TelemetryContext) -> tuple[EnvironmentVariable, ...]:
    home = os.environ.get("HOME")
    temporary = os.environ.get("TMPDIR")
    if home is None or temporary is None:
        raise CompatibilityError("probe requires explicit contained HOME and TMPDIR")
    values = {
        "HOME": home,
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "SOURCE_DATE_EPOCH": "0",
        "TMPDIR": temporary,
        "PIP_CONFIG_FILE": "/dev/null",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "CTOWER_TELEMETRY_CONTEXT": json.dumps(
            telemetry.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
        ),
    }
    return tuple(
        EnvironmentVariable(name=name, value=value) for name, value in sorted(values.items())
    )


def _timed[Detail: BaseModel](operation: Callable[[], Detail]) -> tuple[Detail, int]:
    started = time.monotonic()
    result = operation()
    return result, round((time.monotonic() - started) * 1000)


def _write_probe(path: Path, report: ProbeResult) -> None:
    encoded = (
        json.dumps(report.model_dump(mode="json", by_alias=True), sort_keys=True) + "\n"
    ).encode()
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.replace(path)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
