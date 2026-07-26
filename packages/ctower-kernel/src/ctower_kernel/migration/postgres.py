"""Postgres implementation behind the restricted Migration Interface."""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
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
from ctower_kernel.migration import (
    _correction_sql,
    _credential_sql,
    _fence_sql,
    _operation_sql,
    _reconciliation_sql,
    _run_sql,
)
from ctower_kernel.migration._artifact import TrustedReviewerKeys
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["PostgresMigration"]


class PostgresMigration:
    """Persist one dormant, run-scoped ctower-project import authority."""

    def __init__(
        self,
        dsn: str,
        *,
        trusted_reviewer_keys: TrustedReviewerKeys | None = None,
    ) -> None:
        self._dsn = dsn
        self._trusted_reviewer_keys = trusted_reviewer_keys or MappingProxyType({})

    def create_run(
        self,
        actor: Actor,
        request: CtowerProjectImportRunCreateRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportRun | RecordProblem:
        return _run_sql.create_run(
            self._dsn,
            actor,
            request,
            command_id=command_id,
            now=now,
            telemetry=telemetry,
            trusted_keys=self._trusted_reviewer_keys,
        )

    def bind_export_equality(
        self,
        actor: Actor,
        request: CtowerProjectExportEqualityBindRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportRun | RecordProblem:
        return _run_sql.bind_export_equality(
            self._dsn,
            actor,
            request,
            command_id=command_id,
            now=now,
            telemetry=telemetry,
            trusted_keys=self._trusted_reviewer_keys,
        )

    def bind_alias_plan(
        self,
        actor: Actor,
        request: CtowerProjectAliasPlanBindRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportRun | RecordProblem:
        return _run_sql.bind_alias_plan(
            self._dsn,
            actor,
            request,
            command_id=command_id,
            now=now,
            telemetry=telemetry,
            trusted_keys=self._trusted_reviewer_keys,
        )

    def apply_batch(
        self,
        actor: Actor,
        request: CtowerProjectImportBatchRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectImportBatchResult | RecordProblem:
        return _operation_sql.apply_batch(
            self._dsn,
            actor,
            request,
            command_id=command_id,
            now=now,
            telemetry=telemetry,
        )

    def finalize_run(
        self,
        actor: Actor,
        request: CtowerProjectImportFinalizeRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectReconciliationResult | RecordProblem:
        return _reconciliation_sql.finalize_run(
            self._dsn, actor, request, command_id=command_id, now=now, telemetry=telemetry
        )

    def get_run(self, actor: Actor, run_id: UUID) -> CtowerProjectImportRun | RecordProblem:
        return _run_sql.get_run(self._dsn, actor, run_id)

    def append_correction(
        self,
        actor: Actor,
        request: CtowerProjectImportCorrectionRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectMigrationReceipt | RecordProblem:
        return _correction_sql.append_correction(
            self._dsn, actor, request, command_id=command_id, now=now, telemetry=telemetry
        )

    def report_fence_observation(
        self,
        actor: Actor,
        request: CtowerProjectFenceObservationRequest,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> CtowerProjectMigrationReceipt | RecordProblem:
        return _fence_sql.report_observation(
            self._dsn, actor, request, command_id=command_id, now=now, telemetry=telemetry
        )

    def resolve_importer(
        self,
        credential_digest: bytes,
        run_id: UUID,
        cutover_id: UUID,
        project_key: str,
        now: datetime,
    ) -> Actor | None:
        return _credential_sql.resolve_importer(
            self._dsn,
            credential_digest,
            run_id,
            cutover_id,
            project_key,
            now=now,
        )

    def resolve_importer_credential(
        self,
        credential_digest: bytes,
        now: datetime,
    ) -> Actor | None:
        return _credential_sql.resolve_importer_credential(
            self._dsn,
            credential_digest,
            now=now,
        )

    def resolve_fence_observer(
        self,
        credential_digest: bytes,
        now: datetime,
    ) -> Actor | None:
        return _credential_sql.resolve_fence_observer(
            self._dsn,
            credential_digest,
            now=now,
        )
