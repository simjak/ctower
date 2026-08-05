"""Immutable configured attention-kind data materialized for source reads."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg

from ctower_kernel.catalog._postgres_revisions import RevisionState
from ctower_kernel.catalog.interface import ComponentKind
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def materialize_attention_kind_catalogs(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    states: tuple[RevisionState, ...],
    *,
    now: datetime,
) -> None:
    """Carry every newly published attention-kind catalog revision and its members."""

    for state in states:
        if (
            not state.is_new
            or state.resource.component.kind is not ComponentKind.ATTENTION_KIND_CATALOG
        ):
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
        raise RuntimeError("new attention-kind catalog publication facts are incomplete")
    connection.execute(
        """
        INSERT INTO attention_kind_catalog_revisions (
            attention_kind_catalog_revision_id, tenant_id, catalog_key, catalog_revision,
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
        INSERT INTO attention_kind_catalog_members (
            attention_kind_catalog_revision_id, tenant_id, kind_key, label, ordinal
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
