from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from .models_core import (
    EXPECTED_CANDIDATES,
    Digest,
    EnvironmentName,
    FrozenModel,
    HostIdentity,
    Sha256,
    TelemetryContext,
)
from .models_probe import ProbeResult


class ResolutionEvidence(FrozenModel):
    lock: tuple[Annotated[str, StringConstraints(min_length=3, max_length=256)], ...]
    lock_sha256: Sha256
    commands: tuple[
        tuple[Annotated[str, StringConstraints(min_length=1, max_length=32768)], ...], ...
    ]


class ImageIdentity(FrozenModel):
    requested: Annotated[
        str,
        StringConstraints(pattern=r"^docker\.io/library/python@sha256:[0-9a-f]{64}$"),
    ]
    container_id: Sha256
    owner_label: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
    image_id: Digest
    repository_digests: tuple[
        Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9./_-]+@sha256:[0-9a-f]{64}$")], ...
    ]
    os: Literal["linux"]
    architecture: Literal["amd64", "arm64"]

    @model_validator(mode="after")
    def bind_requested_digest(self) -> Self:
        requested_digest = self.requested.rsplit("@", 1)[1]
        if not any(item.rsplit("@", 1)[-1] == requested_digest for item in self.repository_digests):
            raise ValueError("inspected repository digests do not include requested image")
        return self


class DockerImageInspection(FrozenModel):
    image_id: Digest
    architecture: Literal["amd64", "arm64"]
    os: Literal["linux"]
    repository_digests: tuple[
        Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9./_-]+@sha256:[0-9a-f]{64}$")], ...
    ]


class DockerContainerInspection(FrozenModel):
    container_id: Sha256
    image_id: Digest
    owner_label: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


class ArtifactEvidence(FrozenModel):
    status: Literal["not_exercised"]
    reason_code: Literal["artifact_absent"]


class ProductArtifactEvidence(FrozenModel):
    release_helper_wheel: ArtifactEvidence
    generated_clients: ArtifactEvidence


class CompatibilityRun(ProbeResult):
    environment: EnvironmentName
    host_identity: HostIdentity
    resolution: ResolutionEvidence
    product_artifacts: ProductArtifactEvidence
    image_identity: ImageIdentity | None = None

    @model_validator(mode="after")
    def validate_environment_identity(self) -> Self:
        _validate_common_identity(self)
        if self.environment == "macos-host":
            _validate_host_leg(self)
        else:
            _validate_container_leg(self)
        return self


class CompatibilityReport(FrozenModel):
    schema_: Literal["ctower.compatibility-result/v1"] = Field(alias="schema")
    input_digest: Digest
    matrix_id: Literal["ct-l0-007-python-2026-07-19"]
    telemetry: TelemetryContext
    runs: tuple[CompatibilityRun, ...]

    @model_validator(mode="after")
    def validate_report_topology(self) -> Self:
        expected_topology = tuple(
            (candidate.version, environment)
            for candidate in EXPECTED_CANDIDATES
            for environment in ("macos-host", "linux-container")
        )
        observed_topology = tuple((run.version, run.environment) for run in self.runs)
        if observed_topology != expected_topology:
            raise ValueError("runs do not match the exact six-leg L0 topology")
        if any(run.telemetry != self.telemetry for run in self.runs):
            raise ValueError("run telemetry does not match report telemetry")
        _validate_report_images(self)
        return self


def _validate_common_identity(run: CompatibilityRun) -> None:
    if run.host_identity.system != run.interpreter.system:
        raise ValueError("declared system does not match interpreter evidence")
    if _normalize_machine(run.host_identity.machine) != _normalize_machine(run.interpreter.machine):
        raise ValueError("declared machine does not match interpreter evidence")


def _validate_host_leg(run: CompatibilityRun) -> None:
    if run.host_identity.system != "Darwin" or run.image_identity is not None:
        raise ValueError("macos-host evidence must prove a Darwin host without an image")


def _validate_container_leg(run: CompatibilityRun) -> None:
    if run.host_identity.system != "Linux" or run.image_identity is None:
        raise ValueError("linux-container evidence must prove Linux and an image identity")
    if _normalize_machine(run.image_identity.architecture) != _normalize_machine(
        run.interpreter.machine
    ):
        raise ValueError("container machine does not match inspected image architecture")


def _validate_report_images(report: CompatibilityReport) -> None:
    images = {candidate.version: candidate.linux_image for candidate in EXPECTED_CANDIDATES}
    for run in report.runs:
        if run.environment != "linux-container":
            continue
        if run.image_identity is None or run.image_identity.requested != images[run.version]:
            raise ValueError("container evidence does not bind to the input image")


def _normalize_machine(value: str) -> str:
    aliases = {"aarch64": "arm64", "x86_64": "amd64", "AMD64": "amd64"}
    return aliases.get(value, value.lower())
