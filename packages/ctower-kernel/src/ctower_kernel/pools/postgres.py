"""PostgreSQL implementation behind the Pools Interface."""

from __future__ import annotations

from ctower_kernel.pools._sql import read_limits as _read_limits
from ctower_kernel.pools._sql import record_observation as _record_observation
from ctower_kernel.pools.models import (
    PoolLimitsView,
    PoolObservationCommand,
    PoolObservationReceipt,
)
from ctower_kernel.record import Actor, RecordProblem

__all__ = ["PostgresPools"]


class PostgresPools:
    """Persist append-only credential-pool sweeps and read the latest per profile."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def record_observation(
        self, actor: Actor, command: PoolObservationCommand
    ) -> PoolObservationReceipt | RecordProblem:
        return _record_observation(self._dsn, actor, command)

    def read_limits(self, actor: Actor, profile_key: str | None) -> PoolLimitsView | RecordProblem:
        return _read_limits(self._dsn, actor, profile_key)
