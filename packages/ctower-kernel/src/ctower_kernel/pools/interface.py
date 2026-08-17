"""Small Pools Interface: record one observed sweep, read per-entry limits back.

Ctower does not maintain a parallel opinion about whether a credential is capped. The
harness engine owns its own auth state and ctower never writes it; what ctower owns is the
history the engine does not keep, projected through a named-field allowlist, plus the
desired topology the engine has no concept of.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ctower_kernel.pools.models import (
    PoolLimitsView,
    PoolObservationCommand,
    PoolObservationReceipt,
)
from ctower_kernel.record import Actor, RecordProblem

__all__ = ["Pools"]


class _PoolStore(Protocol):
    def record_observation(
        self, actor: Actor, command: PoolObservationCommand
    ) -> PoolObservationReceipt | RecordProblem: ...

    def read_limits(
        self, actor: Actor, profile_key: str | None
    ) -> PoolLimitsView | RecordProblem: ...


class Pools:
    """Append credential-pool observations and read the latest sweep per profile."""

    def __init__(self, store: _PoolStore) -> None:
        self._store = store

    def record_observation(
        self, actor: Actor, command: PoolObservationCommand
    ) -> PoolObservationReceipt | RecordProblem:
        return self._store.record_observation(actor, command)

    def read_limits(
        self, actor: Actor, profile_key: str | None = None
    ) -> PoolLimitsView | RecordProblem:
        return self._store.read_limits(actor, profile_key)


def observation_stream(observation_id: UUID) -> str:
    """Return the canonical stream this observation appends to."""

    return f"pool-observation:{observation_id}"
