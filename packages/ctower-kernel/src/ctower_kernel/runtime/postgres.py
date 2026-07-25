"""PostgreSQL implementation behind the deterministic Runtime Interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.record import RecordProblem
from ctower_kernel.runtime import (
    FixedOperationAttempt,
    FixedOperationCompletion,
    FixedOperationResult,
    RoutineRevision,
    SchedulerScan,
    SyntheticRun,
    SyntheticRunCommand,
    SyntheticRunReceipt,
)
from ctower_kernel.runtime._routine_sql import register as _register
from ctower_kernel.runtime._routine_sql import scan as _scan
from ctower_kernel.runtime._routine_sql import tenant_ids as _tenant_ids
from ctower_kernel.runtime._synthetic_sql import claim_synthetic as _claim_synthetic
from ctower_kernel.runtime._synthetic_sql import complete_synthetic as _complete_synthetic
from ctower_kernel.runtime._synthetic_sql import start_synthetic as _start_synthetic
from ctower_kernel.runtime._synthetic_sql import synthetic_run as _synthetic_run

__all__ = ["PostgresRuntime"]


class PostgresRuntime:
    """Persist Routine occurrence/job truth without exposing arbitrary dispatch."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def register(
        self,
        tenant_id: UUID,
        revision: RoutineRevision,
        *,
        first_fire_at: datetime | None,
    ) -> None:
        _register(self._dsn, tenant_id, revision, first_fire_at=first_fire_at)

    def scan(self, tenant_id: UUID) -> SchedulerScan:
        return _scan(self._dsn, tenant_id)

    def tenant_ids(self) -> tuple[UUID, ...]:
        return _tenant_ids(self._dsn)

    def start_synthetic(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command: SyntheticRunCommand,
        revision: RoutineRevision,
    ) -> SyntheticRunReceipt | RecordProblem:
        return _start_synthetic(self._dsn, tenant_id, principal_id, command, revision)

    def claim_synthetic(self, worker_ref: str) -> FixedOperationAttempt | None:
        return _claim_synthetic(self._dsn, worker_ref)

    def complete_synthetic(
        self,
        attempt: FixedOperationAttempt,
        completion: FixedOperationCompletion,
    ) -> FixedOperationResult:
        return _complete_synthetic(self._dsn, attempt, completion)

    def synthetic_run(self, tenant_id: UUID, run_id: UUID) -> SyntheticRun | None:
        return _synthetic_run(self._dsn, tenant_id, run_id)
