"""Read-side kernel module composition for the development runtime.

The runtime entry point composes one process out of every kernel Interface, which makes it
the one place whose dependency breadth grows with the system. This module owns the read-side
half of that composition so neither file has to know the whole of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ctower_kernel.attention import Attention
from ctower_kernel.attention.postgres import PostgresAttention
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.postgres import PostgresBoardContextFacts
from ctower_kernel.inbox import Inbox, PostgresInbox
from ctower_kernel.knowledge import (
    Knowledge,
    PostgresKnowledge,
    StaticFileKnowledgeSource,
    bundled_static_root,
)
from ctower_kernel.pools import Pools, PostgresPools
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections

__all__ = ["ReadSideModules", "read_side_modules"]


@dataclass(frozen=True, slots=True)
class ReadSideModules:
    """Every kernel Interface the development runtime composes for reads."""

    projections: Projections
    attention: Attention
    board_context: BoardContextFacts
    inbox: Inbox
    knowledge: Knowledge
    pools: Pools


def read_side_modules(runtime_dsn: str, projection_dsn: str) -> ReadSideModules:
    """Compose the read-side modules against the two development runtime roles."""

    return ReadSideModules(
        projections=Projections(PostgresProjections(projection_dsn)),
        attention=Attention(PostgresAttention(runtime_dsn)),
        board_context=BoardContextFacts(PostgresBoardContextFacts(runtime_dsn)),
        inbox=Inbox(PostgresInbox(runtime_dsn)),
        knowledge=Knowledge(
            PostgresKnowledge(runtime_dsn, source=StaticFileKnowledgeSource(bundled_static_root()))
        ),
        pools=Pools(PostgresPools(runtime_dsn)),
    )
