"""Postgres implementation behind the Projections Interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.projections import (
    BoardQuery,
    BoardView,
    ControlHealth,
)
from ctower_kernel.projections._health_sql import health as _health
from ctower_kernel.projections._inbox_sql import list_correspondents as _list_correspondents
from ctower_kernel.projections._inbox_sql import list_threads as _list_threads
from ctower_kernel.projections._inbox_sql import read_state as _read_state
from ctower_kernel.projections._inbox_sql import read_thread as _read_thread
from ctower_kernel.projections._postgres_sql import board as _board
from ctower_kernel.projections._postgres_sql import catch_up as _catch_up
from ctower_kernel.projections._postgres_sql import rebuild as _rebuild
from ctower_kernel.projections._project_delivery_reconcile_sql import (
    rebuild as _rebuild_project_delivery,
)
from ctower_kernel.projections._project_delivery_reconcile_sql import (
    reconcile as _reconcile_project_delivery,
)
from ctower_kernel.projections._project_delivery_sql import cutover_health as _cutover_health
from ctower_kernel.projections._project_delivery_sql import (
    project_delivery as _project_delivery,
)
from ctower_kernel.projections.inbox import InboxReadState
from ctower_kernel.projections.interface import (
    InboxCorrespondentList,
    InboxThread,
    InboxThreadList,
)
from ctower_kernel.projections.project_delivery import (
    CtowerProjectCutoverHealth,
    ProjectDeliveryView,
)
from ctower_kernel.record import Actor, DurabilityHealth, RecordProblem

__all__ = ["PostgresProjections"]


class PostgresProjections:
    """Read authority facts and mutate only disposable rows/cursors."""

    def __init__(self, projection_dsn: str) -> None:
        self._dsn = projection_dsn

    def catch_up(self, tenant_id: UUID, through_watermark: int | None = None) -> BoardView:
        return _catch_up(self._dsn, tenant_id, through_watermark)

    def board(self, actor: Actor, query: BoardQuery) -> BoardView | RecordProblem:
        return _board(self._dsn, actor, query)

    def list_inbox(self, actor: Actor, *, unread: bool) -> InboxThreadList:
        return _list_threads(self._dsn, actor, unread=unread)

    def list_inbox_correspondents(self, actor: Actor) -> InboxCorrespondentList:
        return _list_correspondents(self._dsn, actor)

    def read_inbox(self, actor: Actor, thread_id: UUID) -> InboxThread | None:
        return _read_thread(self._dsn, actor, thread_id)

    def inbox_read_state(self, actor: Actor, thread_id: UUID) -> InboxReadState | None:
        return _read_state(self._dsn, actor, thread_id)

    def rebuild(self, tenant_id: UUID) -> BoardView:
        return _rebuild(self._dsn, tenant_id)

    def health(
        self, tenant_id: UUID, durability: DurabilityHealth, *, now: datetime
    ) -> ControlHealth:
        return _health(self._dsn, tenant_id, durability, now=now)

    def cutover_health(self, actor: Actor) -> CtowerProjectCutoverHealth:
        return _cutover_health(self._dsn, actor)

    def project_delivery(
        self, actor: Actor, project_key: str
    ) -> ProjectDeliveryView | RecordProblem | None:
        return _project_delivery(self._dsn, actor, project_key)

    def reconcile_project_delivery(self, tenant_id: UUID, *, now: datetime) -> int:
        return _reconcile_project_delivery(self._dsn, tenant_id, now=now)

    def rebuild_project_delivery(self, tenant_id: UUID, *, now: datetime) -> int:
        return _rebuild_project_delivery(self._dsn, tenant_id, now=now)
