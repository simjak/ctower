"""Small PostgreSQL entry point for accepted-only Board projections."""

from __future__ import annotations

from uuid import UUID

from ctower_kernel.projections import BoardQuery, BoardView
from ctower_kernel.projections._board_sql import read_view
from ctower_kernel.projections._consumer_sql import (
    consume_one,
    mark_requested_unknown,
    read_source,
    reset_projection,
)
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def catch_up(dsn: str, tenant_id: UUID, through_watermark: int | None) -> BoardView:
    """Consume only the accepted partition; HTTP callers never invoke this path."""

    source = read_source(dsn, tenant_id)
    if through_watermark is not None and through_watermark != source:
        mark_requested_unknown(dsn, tenant_id, through_watermark, source)
        return read_view(dsn, tenant_id, None, source=source)
    while consume_one(dsn, tenant_id):
        pass
    source = read_source(dsn, tenant_id)
    return read_view(dsn, tenant_id, None, source=source)


def board(dsn: str, actor: Actor, query: BoardQuery) -> BoardView:
    """Read stored projection rows and watermarks without mutation."""

    source = read_source(dsn, actor.tenant_id)
    return read_view(dsn, actor.tenant_id, query, source=source)


def rebuild(dsn: str, tenant_id: UUID) -> BoardView:
    """Discard disposable state and replay the accepted immutable outbox prefix."""

    reset_projection(dsn, tenant_id)
    return catch_up(dsn, tenant_id, None)
