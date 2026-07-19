from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

from tools.compatibility.contract import (
    EXPECTED_REQUIREMENTS,
    EnvironmentVariable,
    HostIdentity,
    ProcessRequest,
    ProcessResult,
    PythonVersion,
    RuntimeDetails,
    TelemetryContext,
)

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "contracts" / "compatibility" / "ct-l0-007-matrix.json"
HASH = "a" * 64
CONTAINER_ID = "b" * 64
IMAGE_ID = "sha256:" + ("c" * 64)


def telemetry_from_request(request: ProcessRequest) -> dict[str, object]:
    environment = request.environment_dict()
    raw = environment.get("CTOWER_TELEMETRY_CONTEXT")
    if raw is None:
        item = next(
            value for value in request.argv if value.startswith("CTOWER_TELEMETRY_CONTEXT=")
        )
        raw = item.split("=", 1)[1]
    value: object = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError("telemetry must be an object")
    return cast("dict[str, object]", value)


def probe_payload(
    version: str,
    *,
    system: Literal["Darwin", "Linux"],
    machine: str,
    telemetry: dict[str, object],
) -> dict[str, object]:
    runtime = _runtime_payload(version, system, machine)
    return {
        "version": version,
        "status": "passed",
        "interpreter": runtime,
        "observations": _probe_observations(runtime),
        "telemetry": telemetry,
    }


def _runtime_payload(
    version: str, system: Literal["Darwin", "Linux"], machine: str
) -> dict[str, object]:
    return {
        "version": version,
        "implementation": "CPython",
        "free_threaded": False,
        "gil_enabled": True,
        "system": system,
        "platform": f"{system}-fixture",
        "machine": machine,
        "soabi": "cpython-fixture",
        "cache_tag": "cpython-fixture",
        "py_gil_disabled": 0,
        "executable_sha256": HASH,
    }


def _probe_observations(runtime: dict[str, object]) -> list[dict[str, object]]:
    direct = [
        {"name": item.split("==", 1)[0], "version": item.split("==", 1)[1]}
        for item in EXPECTED_REQUIREMENTS
    ]
    return [
        _observation("runtime", runtime),
        _observation("dependency_resolution", {"direct_versions": direct}),
        _observation("pydantic", {"extra_fields": "forbidden", "frozen": True}),
        _observation("fastapi", {"version": "0.139.2", "openapi": "3.1.0", "schema_sha256": HASH}),
        _observation("psycopg", {"psycopg": "3.3.4", "psycopg_pool": "3.3.1"}),
        _observation("opentelemetry", {"api": "1.44.0", "spans": 1}),
        _observation("ruff", {"exit_code": 0}),
        _observation(
            "mypy_pydantic_plugin",
            {
                "valid": {"exit_code": 0},
                "invalid_exit_code": 1,
                "extra_field_rejected": True,
            },
        ),
        _observation("jsonschema", {"version": "4.26.0", "schema_sha256": HASH}),
        _observation(
            "wheel",
            {
                "wheel_sha256": HASH,
                "build": {"exit_code": 0},
                "install": {"exit_code": 0},
                "imported": True,
            },
        ),
    ]


def _observation(identifier: str, details: object) -> dict[str, object]:
    return {"id": identifier, "status": "passed", "duration_ms": 1, "details": details}


class MatrixPort:
    def __init__(self) -> None:
        self.calls: list[ProcessRequest] = []
        self.mount: Path | None = None
        self.cleanup_mode: Literal["ok", "failed", "timeout"] = "ok"
        self.fail_operation: str | None = None
        self.host = HostIdentity(system="Darwin", machine="arm64")
        self.container_machine = "aarch64"
        self.image_architecture: Literal["amd64", "arm64"] = "arm64"
        self.image_id = IMAGE_ID
        self.container_image_id = IMAGE_ID
        self.container_id = CONTAINER_ID
        self.owner_label = ""
        self.owner_label_override: str | None = None
        self.create_stdout: str | None = None
        self.image_inspection_override: str | None = None
        self.container_inspection_override: str | None = None
        self.malformed_probe: str | None = None
        self.probe_mutator: Callable[[dict[str, object]], None] | None = None

    def resolve_tool(self, name: str) -> str | None:
        return f"/usr/local/bin/{name}" if name in {"uv", "docker"} else None

    def host_identity(self) -> HostIdentity:
        return self.host

    def run(self, request: ProcessRequest) -> ProcessResult:
        self.calls.append(request)
        if request.operation == self.fail_operation:
            return _result(request, returncode=7, stderr="synthetic failure")
        handlers: dict[str, Callable[[ProcessRequest], ProcessResult]] = {
            "uv-bootstrap": self._bootstrap_uv,
            "docker-cleanup": self._cleanup,
            "docker-create": self._create,
            "dependency-freeze": self._freeze,
            "docker-freeze": self._freeze,
            "docker-inspect": self._inspect,
            "compatibility-probe": self._probe,
            "docker-probe": self._probe,
        }
        handler = handlers.get(request.operation)
        return handler(request) if handler is not None else _result(request)

    def _cleanup(self, request: ProcessRequest) -> ProcessResult:
        if self.cleanup_mode == "failed":
            return _result(request, returncode=9, stderr="cleanup refused")
        if self.cleanup_mode == "timeout":
            return _result(request, returncode=-9, timed_out=True, termination="killed")
        return _result(request)

    def _create(self, request: ProcessRequest) -> ProcessResult:
        self._remember_mount(request.argv)
        return _result(request, stdout=self.create_stdout or self.container_id + "\n")

    def _freeze(self, request: ProcessRequest) -> ProcessResult:
        return _result(request, stdout="\n".join(EXPECTED_REQUIREMENTS) + "\n")

    def _inspect(self, request: ProcessRequest) -> ProcessResult:
        return _result(request, stdout=self._inspection(request.argv))

    def _probe(self, request: ProcessRequest) -> ProcessResult:
        self._write_probe(request)
        return _result(request)

    def _bootstrap_uv(self, request: ProcessRequest) -> ProcessResult:
        if request.argv[-1] == "--version":
            return _result(request, stdout="uv 0.11.29\n")
        environment = request.environment_dict()
        binary = Path(environment["UV_TOOL_BIN_DIR"]) / "uv"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"fixture uv")
        return _result(request)

    def _remember_mount(self, argv: tuple[str, ...]) -> None:
        mount = argv[argv.index("--mount") + 1]
        source = mount.split("source=", 1)[1].split(",target=", 1)[0]
        self.mount = Path(source)
        label = argv[argv.index("--label") + 1]
        self.owner_label = label.split("=", 1)[1]

    def _inspection(self, argv: tuple[str, ...]) -> str:
        if "container" in argv:
            if self.container_inspection_override is not None:
                return self.container_inspection_override
            return json.dumps(
                {
                    "container_id": self.container_id,
                    "image_id": self.container_image_id,
                    "owner_label": self.owner_label_override or self.owner_label,
                }
            )
        if self.image_inspection_override is not None:
            return self.image_inspection_override
        requested = argv[-1]
        digest = requested.rsplit("@", 1)[1]
        return json.dumps(
            {
                "image_id": self.image_id,
                "architecture": self.image_architecture,
                "os": "linux",
                "repository_digests": [f"python@{digest}"],
            }
        )

    def _write_probe(self, request: ProcessRequest) -> None:
        version = request.argv[request.argv.index("--version") + 1]
        output = request.argv[request.argv.index("--output") + 1]
        if output == "/fixture/result.json":
            if self.mount is None:
                raise AssertionError("container mount was not recorded")
            destination = self.mount / "result.json"
            system: Literal["Darwin", "Linux"] = "Linux"
            machine = self.container_machine
        else:
            destination = Path(output)
            system = "Darwin"
            machine = self.host.machine
        payload = probe_payload(
            version,
            system=system,
            machine=machine,
            telemetry=telemetry_from_request(request),
        )
        if self.probe_mutator is not None:
            self.probe_mutator(payload)
        text = self.malformed_probe or json.dumps(payload)
        destination.write_text(text, encoding="utf-8")


class ProbeFixturePort:
    def __init__(self, version: PythonVersion = "3.12.13") -> None:
        self.version = version
        self.calls: list[ProcessRequest] = []
        self.fail_source: str | None = None
        self.timeout_source: str | None = None
        self.output_overrides: dict[str, str] = {}
        self.mypy_invalid_returncode = 1
        self.import_marker = "ctower-wheel-ok\n"

    def resolve_tool(self, name: str) -> str | None:
        del name
        return None

    def host_identity(self) -> HostIdentity:
        return HostIdentity(system="Darwin", machine="arm64")

    def runtime_details(self, expected_version: PythonVersion) -> RuntimeDetails:
        if expected_version != self.version:
            raise AssertionError("wrong fixture candidate")
        return RuntimeDetails(
            version=expected_version,
            implementation="CPython",
            free_threaded=False,
            gil_enabled=True,
            system="Darwin",
            platform="Darwin-fixture",
            machine="arm64",
            soabi="cpython-fixture",
            cache_tag="cpython-fixture",
            py_gil_disabled=0,
            executable_sha256=HASH,
        )

    def distribution_version(self, name: str) -> str:
        requirement = next(item for item in EXPECTED_REQUIREMENTS if item.startswith(f"{name}=="))
        return requirement.split("==", 1)[1]

    def run(self, request: ProcessRequest) -> ProcessResult:
        self.calls.append(request)
        joined = " ".join(request.argv)
        failure = self._failure(request, joined)
        if failure is not None:
            return failure
        self._materialize_build(request, joined)
        return self._command_result(request, joined)

    def _failure(self, request: ProcessRequest, joined: str) -> ProcessResult | None:
        if self.fail_source and self.fail_source in joined:
            return _result(request, returncode=5, stderr="synthetic probe failure")
        if self.timeout_source and self.timeout_source in joined:
            return _result(request, returncode=-9, timed_out=True, termination="killed")
        return None

    @staticmethod
    def _materialize_build(request: ProcessRequest, joined: str) -> None:
        if " -m build " in f" {joined} ":
            root = Path(request.argv[-1])
            (root / "dist").mkdir()
            (root / "dist" / "fixture.whl").write_bytes(b"fixture-wheel")

    def _command_result(self, request: ProcessRequest, joined: str) -> ProcessResult:
        if request.argv[-1].endswith("invalid.py"):
            return _result(
                request,
                returncode=self.mypy_invalid_returncode,
                stdout="Unexpected keyword argument",
            )
        if "ctower_compat_wheel as w" in joined:
            return _result(request, stdout=self.import_marker)
        return self._observation_result(request, joined)

    def _observation_result(self, request: ProcessRequest, joined: str) -> ProcessResult:
        outputs: dict[str, object] = {
            "unknown field accepted": {"extra_fields": "forbidden", "frozen": True},
            "FastAPI": {"version": "0.139.2", "openapi": "3.1.0", "schema_sha256": HASH},
            "psycopg_pool": {"psycopg": "3.3.4", "psycopg_pool": "3.3.1"},
            "InMemorySpanExporter": {"api": "1.44.0", "spans": 1},
            "Draft202012Validator": {"version": "4.26.0", "schema_sha256": HASH},
        }
        match = next(((key, value) for key, value in outputs.items() if key in joined), None)
        if match is None:
            return _result(request)
        marker, value = match
        stdout = self.output_overrides.get(marker, json.dumps(value))
        return _result(request, stdout=stdout)


def _result(
    request: ProcessRequest,
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
    termination: Literal["exited", "terminated", "killed"] = "exited",
) -> ProcessResult:
    return ProcessResult(
        argv=request.argv,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        termination=termination,
        stdout_truncated=False,
        stderr_truncated=False,
    )


def env_names(environment: tuple[EnvironmentVariable, ...]) -> set[str]:
    return {item.name for item in environment}


def telemetry() -> TelemetryContext:
    return TelemetryContext.create()
