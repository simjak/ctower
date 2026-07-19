from __future__ import annotations

import hashlib
import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

__all__ = [
    "CompatibilityError",
    "CompatibilityMatrix",
    "EnvironmentName",
]

PythonVersion = Literal["3.12.13", "3.13.14", "3.14.6"]
EnvironmentName = Literal["macos-host", "linux-container"]
ObservationName = Literal[
    "runtime",
    "dependency_resolution",
    "pydantic",
    "fastapi",
    "psycopg",
    "opentelemetry",
    "ruff",
    "mypy_pydantic_plugin",
    "jsonschema",
    "wheel",
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
Machine = Literal["amd64", "arm64"]
UuidText = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    ),
]

EXPECTED_REQUIREMENTS = (
    "build==1.5.0",
    "fastapi==0.139.2",
    "httpx==0.28.1",
    "jsonschema==4.26.0",
    "mypy==1.20.2",
    "opentelemetry-api==1.44.0",
    "opentelemetry-sdk==1.44.0",
    "psycopg==3.3.4",
    "psycopg-binary==3.3.4",
    "psycopg-pool==3.3.1",
    "pydantic==2.13.4",
    "ruff==0.15.22",
    "setuptools==83.0.0",
    "types-jsonschema==4.26.0.20260518",
    "uv==0.11.29",
    "uvicorn==0.51.0",
    "wheel==0.47.0",
)
EXPECTED_OBSERVATIONS: tuple[ObservationName, ...] = (
    "runtime",
    "dependency_resolution",
    "pydantic",
    "fastapi",
    "psycopg",
    "opentelemetry",
    "ruff",
    "mypy_pydantic_plugin",
    "jsonschema",
    "wheel",
)
EXPECTED_ARTIFACTS = ("release_helper_wheel", "generated_clients")


class CompatibilityError(RuntimeError):
    """The compatibility input, validation, or publication failed closed."""


class FrozenModel(BaseModel):
    """Strict immutable base for every compatibility boundary value."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TelemetryContext(FrozenModel):
    schema_: Literal["ctower.telemetry-context/v1"] = Field(alias="schema")
    trace_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
    span_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]
    trace_flags: int = Field(ge=0, le=255)
    trace_state: None = None
    correlation_id: UuidText
    causation_id: UuidText
    tenant_id: Literal["ctower-public-contracts"]
    actor_id: Literal["ctower.compatibility-validator"]
    command_id: UuidText
    ticket_id: None = None
    workflow_run_id: None = None
    stage_attempt_id: None = None
    job_id: None = None
    runner_id: None = None
    fencing_token: None = None
    effect_id: None = None
    component_revision_id: Literal["CT-L0-007"]
    deployment_id: None = None

    @classmethod
    def for_matrix(cls, input_digest: str) -> Self:
        seed = hashlib.sha256(input_digest.encode()).digest()
        return cls(
            schema="ctower.telemetry-context/v1",
            trace_id=hashlib.sha256(seed + b"trace").hexdigest()[:32],
            span_id=hashlib.sha256(seed + b"span").hexdigest()[:16],
            trace_flags=1,
            correlation_id=str(
                uuid.UUID(bytes=hashlib.sha256(seed + b"correlation").digest()[:16], version=4)
            ),
            causation_id=str(
                uuid.UUID(bytes=hashlib.sha256(seed + b"causation").digest()[:16], version=4)
            ),
            tenant_id="ctower-public-contracts",
            actor_id="ctower.compatibility-validator",
            command_id=str(
                uuid.UUID(bytes=hashlib.sha256(seed + b"command").digest()[:16], version=4)
            ),
            component_revision_id="CT-L0-007",
        )


class Candidate(FrozenModel):
    version: PythonVersion
    gil: Literal["required"]
    release_date: Annotated[str, StringConstraints(pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")]
    release_url: Annotated[
        str,
        StringConstraints(pattern=r"^https://www\.python\.org/downloads/release/python-[0-9]+/$"),
    ]
    source_url: Annotated[
        str,
        StringConstraints(
            pattern=r"^https://www\.python\.org/ftp/python/[0-9.]+/Python-[0-9.]+\.tgz$"
        ),
    ]
    source_sha256: Sha256
    linux_image: Annotated[
        str,
        StringConstraints(pattern=r"^docker\.io/library/python@sha256:[0-9a-f]{64}$"),
    ]


EXPECTED_CANDIDATES = (
    Candidate(
        version="3.12.13",
        gil="required",
        release_date="2026-03-03",
        release_url="https://www.python.org/downloads/release/python-31213/",
        source_url="https://www.python.org/ftp/python/3.12.13/Python-3.12.13.tgz",
        source_sha256="0816c4761c97ecdb3f50a3924de0a93fd78cb63ee8e6c04201ddfaedca500b0b",
        linux_image="docker.io/library/python@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de",
    ),
    Candidate(
        version="3.13.14",
        gil="required",
        release_date="2026-06-10",
        release_url="https://www.python.org/downloads/release/python-31314/",
        source_url="https://www.python.org/ftp/python/3.13.14/Python-3.13.14.tgz",
        source_sha256="5ae535a36af0ebca6fca176ecb8197f5db9c1cb8c8f0cd12cdf1787046db1f41",
        linux_image="docker.io/library/python@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91",
    ),
    Candidate(
        version="3.14.6",
        gil="required",
        release_date="2026-06-10",
        release_url="https://www.python.org/downloads/release/python-3146/",
        source_url="https://www.python.org/ftp/python/3.14.6/Python-3.14.6.tgz",
        source_sha256="74d0d71d0600e477651a077101d6e62d1e2e69b8e992ba18c993dd643b7ba222",
        linux_image="docker.io/library/python@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6",
    ),
)


class MatrixInput(FrozenModel):
    schema_: Literal["ctower.compatibility-input/v1"] = Field(alias="schema")
    matrix_id: Literal["ct-l0-007-python-2026-07-19"]
    uv_version: Literal["0.11.29"]
    requirements: tuple[str, ...]
    required_observations: tuple[ObservationName, ...]
    product_artifacts: tuple[Literal["release_helper_wheel", "generated_clients"], ...]
    candidates: tuple[Candidate, ...]

    @model_validator(mode="after")
    def enforce_fixed_preflight(self) -> Self:
        if self.requirements != EXPECTED_REQUIREMENTS:
            raise ValueError("requirements do not match the reviewed L0 allowlist")
        if self.required_observations != EXPECTED_OBSERVATIONS:
            raise ValueError("observations do not match the reviewed L0 allowlist")
        if self.product_artifacts != EXPECTED_ARTIFACTS:
            raise ValueError("product artifacts do not match the reviewed L0 allowlist")
        if self.candidates != EXPECTED_CANDIDATES:
            raise ValueError("candidates do not match the reviewed L0 allowlist")
        return self


class CompatibilityMatrix(FrozenModel):
    source: MatrixInput
    digest: Digest
    telemetry: TelemetryContext

    @property
    def matrix_id(self) -> str:
        return self.source.matrix_id

    @property
    def uv_version(self) -> str:
        return self.source.uv_version

    @property
    def requirements(self) -> tuple[str, ...]:
        return self.source.requirements

    @property
    def required_observations(self) -> tuple[ObservationName, ...]:
        return self.source.required_observations

    @property
    def product_artifacts(self) -> tuple[str, ...]:
        return self.source.product_artifacts

    @property
    def candidates(self) -> tuple[Candidate, ...]:
        return self.source.candidates


class HostIdentity(FrozenModel):
    system: Literal["Darwin", "Linux"]
    machine: Machine


class ResolvedDependency(FrozenModel):
    name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]+$")]
    version: Annotated[str, StringConstraints(pattern=r"^[0-9][A-Za-z0-9.+!-]*$")]


class RuntimeDetails(FrozenModel):
    version: PythonVersion
    implementation: Literal["CPython"]
    free_threaded: Literal[False]
    gil_enabled: Literal[True]
    system: Literal["Darwin", "Linux"]
    platform: Literal["linux-amd64", "linux-arm64", "macos-amd64", "macos-arm64"]
    machine: Machine
    soabi: Literal[
        "cpython-312-aarch64-linux-gnu",
        "cpython-312-darwin",
        "cpython-312-x86_64-linux-gnu",
        "cpython-313-aarch64-linux-gnu",
        "cpython-313-darwin",
        "cpython-313-x86_64-linux-gnu",
        "cpython-314-aarch64-linux-gnu",
        "cpython-314-darwin",
        "cpython-314-x86_64-linux-gnu",
    ]
    cache_tag: Literal["cpython-312", "cpython-313", "cpython-314"]
    py_gil_disabled: Literal[0]
    executable_sha256: Sha256

    @model_validator(mode="after")
    def enforce_runtime_identity(self) -> Self:
        parts = self.version.split(".")
        abi = f"{parts[0]}{parts[1]}"
        expected_tag = f"cpython-{abi}"
        expected_platform = f"{'macos' if self.system == 'Darwin' else 'linux'}-{self.machine}"
        linux_machine = "aarch64" if self.machine == "arm64" else "x86_64"
        expected_soabi = (
            f"cpython-{abi}-darwin"
            if self.system == "Darwin"
            else f"cpython-{abi}-{linux_machine}-linux-gnu"
        )
        if (
            self.cache_tag != expected_tag
            or self.platform != expected_platform
            or self.soabi != expected_soabi
        ):
            raise ValueError("runtime strings do not match the canonical identity")
        return self
