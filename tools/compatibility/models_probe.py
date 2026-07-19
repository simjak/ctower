from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from .models_core import (
    EXPECTED_OBSERVATIONS,
    EXPECTED_REQUIREMENTS,
    FrozenModel,
    PythonVersion,
    ResolvedDependency,
    RuntimeDetails,
    Sha256,
    TelemetryContext,
)


class DependencyDetails(FrozenModel):
    direct_versions: tuple[ResolvedDependency, ...]

    @model_validator(mode="after")
    def enforce_direct_versions(self) -> Self:
        expected = tuple(
            ResolvedDependency(name=item.split("==", 1)[0], version=item.split("==", 1)[1])
            for item in EXPECTED_REQUIREMENTS
        )
        if self.direct_versions != expected:
            raise ValueError("resolved direct dependencies do not match the L0 allowlist")
        return self


class PydanticDetails(FrozenModel):
    extra_fields: Literal["forbidden"]
    frozen: Literal[True]


class FastapiDetails(FrozenModel):
    version: Literal["0.139.2"]
    openapi: Annotated[str, StringConstraints(pattern=r"^3\.[01]\.[0-9]+$")]
    schema_sha256: Sha256


class PsycopgDetails(FrozenModel):
    psycopg: Literal["3.3.4"]
    psycopg_pool: Literal["3.3.1"]


class OpentelemetryDetails(FrozenModel):
    api: Literal["1.44.0"]
    spans: Literal[1]


class CommandDetails(FrozenModel):
    exit_code: Literal[0]


class MypyDetails(FrozenModel):
    valid: CommandDetails
    invalid_exit_code: Literal[1]
    extra_field_rejected: Literal[True]


class JsonschemaDetails(FrozenModel):
    version: Literal["4.26.0"]
    schema_sha256: Sha256


class WheelDetails(FrozenModel):
    wheel_sha256: Sha256
    build: CommandDetails
    install: CommandDetails
    imported: Literal[True]


class ObservationBase(FrozenModel):
    status: Literal["passed"]
    duration_ms: int = Field(ge=0, le=900_000)


class RuntimeObservation(ObservationBase):
    id: Literal["runtime"]
    details: RuntimeDetails


class DependencyObservation(ObservationBase):
    id: Literal["dependency_resolution"]
    details: DependencyDetails


class PydanticObservation(ObservationBase):
    id: Literal["pydantic"]
    details: PydanticDetails


class FastapiObservation(ObservationBase):
    id: Literal["fastapi"]
    details: FastapiDetails


class PsycopgObservation(ObservationBase):
    id: Literal["psycopg"]
    details: PsycopgDetails


class OpentelemetryObservation(ObservationBase):
    id: Literal["opentelemetry"]
    details: OpentelemetryDetails


class RuffObservation(ObservationBase):
    id: Literal["ruff"]
    details: CommandDetails


class MypyObservation(ObservationBase):
    id: Literal["mypy_pydantic_plugin"]
    details: MypyDetails


class JsonschemaObservation(ObservationBase):
    id: Literal["jsonschema"]
    details: JsonschemaDetails


class WheelObservation(ObservationBase):
    id: Literal["wheel"]
    details: WheelDetails


Observation = Annotated[
    RuntimeObservation
    | DependencyObservation
    | PydanticObservation
    | FastapiObservation
    | PsycopgObservation
    | OpentelemetryObservation
    | RuffObservation
    | MypyObservation
    | JsonschemaObservation
    | WheelObservation,
    Field(discriminator="id"),
]


class ProbeResult(FrozenModel):
    version: PythonVersion
    status: Literal["passed"]
    interpreter: RuntimeDetails
    observations: tuple[Observation, ...]
    telemetry: TelemetryContext

    @model_validator(mode="after")
    def validate_probe(self) -> Self:
        if self.version != self.interpreter.version:
            raise ValueError("interpreter version does not match probe candidate")
        if tuple(item.id for item in self.observations) != EXPECTED_OBSERVATIONS:
            raise ValueError("probe observation set or order is invalid")
        if self.observations[0].details != self.interpreter:
            raise ValueError("runtime observation and interpreter identity differ")
        return self
