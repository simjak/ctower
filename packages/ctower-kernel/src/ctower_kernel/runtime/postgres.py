"""PostgreSQL implementation behind the deterministic Runtime Interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.runtime import (
    DreamDispatchConsumeCommand,
    DreamDispatchEffect,
    DreamDispatchReceipt,
    FixedOperationAttempt,
    FixedOperationCompletion,
    FixedOperationResult,
    RoutineRevision,
    SchedulerScan,
    SyntheticRun,
    SyntheticRunCommand,
    SyntheticRunReceipt,
)
from ctower_kernel.runtime._dream_dispatch_sql import (
    bind_dream_lane as _bind_dream_lane,
)
from ctower_kernel.runtime._dream_dispatch_sql import (
    consume_dream_dispatch as _consume_dream_dispatch,
)
from ctower_kernel.runtime._dream_dispatch_sql import (
    list_dream_dispatches as _list_dream_dispatches,
)
from ctower_kernel.runtime._routine_alarms_sql import read_alarm_episodes as _alarm_episodes
from ctower_kernel.runtime._routine_items_sql import complete as _complete_routine_work_item
from ctower_kernel.runtime._routine_sql import register as _register
from ctower_kernel.runtime._routine_sql import scan as _scan
from ctower_kernel.runtime._routine_sql import tenant_ids as _tenant_ids
from ctower_kernel.runtime._synthetic_sql import claim_synthetic as _claim_synthetic
from ctower_kernel.runtime._synthetic_sql import complete_synthetic as _complete_synthetic
from ctower_kernel.runtime._synthetic_sql import start_synthetic as _start_synthetic
from ctower_kernel.runtime._synthetic_sql import synthetic_run as _synthetic_run
from ctower_kernel.runtime.dream_lane import DreamLaneBindCommand, DreamLaneBindingReceipt
from ctower_kernel.runtime.items import (
    CompleteRoutineWorkItemCommand,
    RoutineAlarmEpisode,
    RoutineWorkItemReceipt,
)

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

    def complete_routine_work_item(
        self,
        actor: Actor,
        command: CompleteRoutineWorkItemCommand,
    ) -> RoutineWorkItemReceipt | RecordProblem:
        return _complete_routine_work_item(self._dsn, actor, command)

    def alarm_episodes(self, tenant_id: UUID) -> tuple[RoutineAlarmEpisode, ...]:
        return _alarm_episodes(self._dsn, tenant_id)

    def list_dream_dispatches(self, actor: Actor) -> tuple[DreamDispatchEffect, ...]:
        return _list_dream_dispatches(self._dsn, actor)

    def consume_dream_dispatch(
        self, actor: Actor, command: DreamDispatchConsumeCommand
    ) -> DreamDispatchReceipt | RecordProblem:
        return _consume_dream_dispatch(self._dsn, actor, command)

    def bind_dream_lane(
        self, actor: Actor, command: DreamLaneBindCommand
    ) -> DreamLaneBindingReceipt | RecordProblem:
        return _bind_dream_lane(self._dsn, actor, command)

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
