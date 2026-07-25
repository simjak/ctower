"""Control-plane port for the reviewed migration command surface."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRunCreateRequest,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

type MigrationOutcome = BaseModel | RecordProblem


class MigrationPort(Protocol):
    """Only the typed operations exposed by the I1.7B HTTP adapter."""

    def create_run(
        self,
        actor: Actor,
        request: CtowerProjectImportRunCreateRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> MigrationOutcome: ...

    def bind_export_equality(
        self,
        actor: Actor,
        request: CtowerProjectExportEqualityBindRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> MigrationOutcome: ...

    def bind_alias_plan(
        self,
        actor: Actor,
        request: CtowerProjectAliasPlanBindRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> MigrationOutcome: ...

    def apply_batch(
        self,
        actor: Actor,
        request: CtowerProjectImportBatchRequest,
        *,
        telemetry: TelemetryContext,
    ) -> MigrationOutcome: ...

    def finalize_run(
        self,
        actor: Actor,
        request: CtowerProjectImportFinalizeRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> MigrationOutcome: ...

    def get_run(self, actor: Actor, run_id: UUID) -> MigrationOutcome: ...

    def append_correction(
        self,
        actor: Actor,
        request: CtowerProjectImportCorrectionRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> MigrationOutcome: ...

    def report_fence_observation(
        self,
        actor: Actor,
        request: CtowerProjectFenceObservationRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> MigrationOutcome: ...
