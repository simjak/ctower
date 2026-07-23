"""PostgreSQL implementation behind the deterministic Runtime Interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.runtime import RoutineRevision, SchedulerScan
from ctower_kernel.runtime._routine_sql import register as _register
from ctower_kernel.runtime._routine_sql import scan as _scan
from ctower_kernel.runtime._routine_sql import tenant_ids as _tenant_ids

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
