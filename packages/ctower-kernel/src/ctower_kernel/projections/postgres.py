"""Postgres implementation behind the Projections Interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.projections import BoardQuery, BoardView, ControlHealth
from ctower_kernel.projections._health_sql import health as _health
from ctower_kernel.projections._postgres_sql import board as _board
from ctower_kernel.projections._postgres_sql import catch_up as _catch_up
from ctower_kernel.projections._postgres_sql import rebuild as _rebuild
from ctower_kernel.record import Actor, DurabilityHealth

__all__ = ["PostgresProjections"]


class PostgresProjections:
    """Read authority facts and mutate only disposable rows/cursors."""

    def __init__(self, projection_dsn: str) -> None:
        self._dsn = projection_dsn

    def catch_up(self, tenant_id: UUID, through_watermark: int | None = None) -> BoardView:
        return _catch_up(self._dsn, tenant_id, through_watermark)

    def board(self, actor: Actor, query: BoardQuery) -> BoardView:
        return _board(self._dsn, actor, query)

    def rebuild(self, tenant_id: UUID) -> BoardView:
        return _rebuild(self._dsn, tenant_id)

    def health(
        self, tenant_id: UUID, durability: DurabilityHealth, *, now: datetime
    ) -> ControlHealth:
        return _health(self._dsn, tenant_id, durability, now=now)
