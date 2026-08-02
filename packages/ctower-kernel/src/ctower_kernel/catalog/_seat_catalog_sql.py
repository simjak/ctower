"""Immutable configured seat data materialized for projection-source reads."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg

from ctower_kernel.catalog._postgres_revisions import RevisionState
from ctower_kernel.catalog.interface import ComponentKind
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def materialize_seat_catalogs(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    states: tuple[RevisionState, ...],
    *,
    now: datetime,
) -> None:
    """Carry every newly published seat revision and its ordered members."""

    for state in states:
        if not state.is_new or state.resource.component.kind is not ComponentKind.SEAT_CATALOG:
            continue
        _insert_revision(connection, actor, state, now=now)


def _insert_revision(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    state: RevisionState,
    *,
    now: datetime,
) -> None:
    component = state.resource.component
    event_id = state.publication_event_id
    if event_id is None:
        raise RuntimeError("new seat catalog publication facts are incomplete")
    connection.execute(
        """
        INSERT INTO project_delivery_seat_catalog_revisions (
            seat_catalog_revision_id, tenant_id, catalog_key, catalog_revision,
            catalog_digest, event_id, actor_principal_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            state.revision_id,
            actor.tenant_id,
            component.key,
            component.revision,
            bytes.fromhex(component.content_digest.removeprefix("sha256:")),
            event_id,
            actor.principal_id,
            now,
        ),
    )
    members = cast(list[dict[str, object]], state.resource.payload["members"])
    connection.cursor().executemany(
        """
        INSERT INTO project_delivery_seat_catalog_members (
            seat_catalog_revision_id, tenant_id, seat_key, seat_label, ordinal
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        tuple(
            (
                state.revision_id,
                actor.tenant_id,
                str(member["key"]),
                str(member["label"]),
                ordinal,
            )
            for ordinal, member in enumerate(members, start=1)
        ),
    )
