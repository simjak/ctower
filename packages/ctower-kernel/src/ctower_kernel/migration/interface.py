"""Small capability-first Interface for the restricted import kernel."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportBatchResult,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRun,
    CtowerProjectImportRunCreateRequest,
    CtowerProjectMigrationReceipt,
    CtowerProjectReconciliationResult,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["Migration"]


class _MigrationStore(Protocol):
    def create_run(
        self,
        actor: Actor,
        request: CtowerProjectImportRunCreateRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportRun | RecordProblem: ...

    def bind_export_equality(
        self,
        actor: Actor,
        request: CtowerProjectExportEqualityBindRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportRun | RecordProblem: ...

    def bind_alias_plan(
        self,
        actor: Actor,
        request: CtowerProjectAliasPlanBindRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportRun | RecordProblem: ...

    def apply_batch(
        self,
        actor: Actor,
        request: CtowerProjectImportBatchRequest,
        *,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportBatchResult | RecordProblem: ...

    def finalize_run(
        self,
        actor: Actor,
        request: CtowerProjectImportFinalizeRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectReconciliationResult | RecordProblem: ...

    def get_run(self, actor: Actor, run_id: UUID) -> CtowerProjectImportRun | RecordProblem: ...

    def append_correction(
        self,
        actor: Actor,
        request: CtowerProjectImportCorrectionRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectMigrationReceipt | RecordProblem: ...

    def report_fence_observation(
        self,
        actor: Actor,
        request: CtowerProjectFenceObservationRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectMigrationReceipt | RecordProblem: ...


class Migration:
    """Expose only reviewed migration commands and refuse before persistence."""

    def __init__(
        self, store: _MigrationStore, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_run(
        self,
        actor: Actor,
        request: CtowerProjectImportRunCreateRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportRun | RecordProblem:
        if actor.kind is not PrincipalKind.OPERATOR:
            return _denied(command_id)
        return self._store.create_run(
            actor, request, command_id=command_id, now=self._clock(), telemetry=telemetry
        )

    def bind_export_equality(
        self,
        actor: Actor,
        request: CtowerProjectExportEqualityBindRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportRun | RecordProblem:
        if actor.kind is not PrincipalKind.OPERATOR:
            return _denied(command_id)
        return self._store.bind_export_equality(
            actor, request, command_id=command_id, now=self._clock(), telemetry=telemetry
        )

    def bind_alias_plan(
        self,
        actor: Actor,
        request: CtowerProjectAliasPlanBindRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportRun | RecordProblem:
        if actor.kind is not PrincipalKind.OPERATOR:
            return _denied(command_id)
        return self._store.bind_alias_plan(
            actor, request, command_id=command_id, now=self._clock(), telemetry=telemetry
        )

    def apply_batch(
        self,
        actor: Actor,
        request: CtowerProjectImportBatchRequest,
        *,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportBatchResult | RecordProblem:
        if actor.kind is not PrincipalKind.MIGRATION_IMPORTER:
            return _denied()
        return self._store.apply_batch(actor, request, now=self._clock(), telemetry=telemetry)

    def finalize_run(
        self,
        actor: Actor,
        request: CtowerProjectImportFinalizeRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> CtowerProjectReconciliationResult | RecordProblem:
        if actor.kind is not PrincipalKind.OPERATOR:
            return _denied(command_id)
        return self._store.finalize_run(
            actor, request, command_id=command_id, now=self._clock(), telemetry=telemetry
        )

    def get_run(self, actor: Actor, run_id: UUID) -> CtowerProjectImportRun | RecordProblem:
        if actor.kind is not PrincipalKind.OPERATOR:
            return _denied()
        return self._store.get_run(actor, run_id)

    def append_correction(
        self,
        actor: Actor,
        request: CtowerProjectImportCorrectionRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> CtowerProjectMigrationReceipt | RecordProblem:
        if actor.kind is not PrincipalKind.OPERATOR:
            return _denied(command_id)
        return self._store.append_correction(
            actor, request, command_id=command_id, now=self._clock(), telemetry=telemetry
        )

    def report_fence_observation(
        self,
        actor: Actor,
        request: CtowerProjectFenceObservationRequest,
        *,
        command_id: UUID,
        telemetry: TelemetryContext,
    ) -> CtowerProjectMigrationReceipt | RecordProblem:
        if actor.kind is not PrincipalKind.FENCE_OBSERVER:
            return _denied(command_id)
        return self._store.report_fence_observation(
            actor, request, command_id=command_id, now=self._clock(), telemetry=telemetry
        )


def _denied(command_id: UUID | None = None) -> RecordProblem:
    return RecordProblem(
        code="migration-capability-denied",
        detail="The principal has no authority for this migration command.",
        status=403,
        title="Migration capability denied",
        command_id=command_id,
    )
