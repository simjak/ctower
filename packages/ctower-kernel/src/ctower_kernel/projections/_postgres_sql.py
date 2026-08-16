"""Small PostgreSQL entry point for accepted-only Board projections."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from ctower_kernel.projections import BoardQuery, BoardView
from ctower_kernel.projections._board_sql import read_view
from ctower_kernel.projections._consumer_sql import (
    consume_one,
    mark_requested_unknown,
    read_source,
    reset_projection,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

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

    if (
        query.project_key is not None
        and actor.kind is not PrincipalKind.OPERATOR
        and query.project_key not in actor.project_grants
    ):
        return cast(
            BoardView,
            RecordProblem(
                "project-scope-denied",
                "The authenticated project seat cannot reach a ticket from another project.",
                403,
                "Project scope denied",
            ),
        )
    source = read_source(dsn, actor.tenant_id)
    return read_view(dsn, actor.tenant_id, query, source=source)


def rebuild(dsn: str, tenant_id: UUID) -> BoardView:
    """Discard disposable state and replay the accepted immutable outbox prefix."""

    reset_projection(dsn, tenant_id)
    return catch_up(dsn, tenant_id, None)
