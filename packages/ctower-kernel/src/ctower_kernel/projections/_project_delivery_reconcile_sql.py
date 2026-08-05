"""Worker-owned deterministic Project Delivery reconcile and rebuild."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_kernel.projections._project_delivery_sources_sql import (
    active_checkpoint_event_ids as _active_checkpoint_event_ids,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    criterion_proven as _criterion_proven,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    cutover_claims as _cutover_claims,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    proof_link_states as _proof_link_states,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    qualifying_stage_slots as _qualifying_stage_slots,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    signing_seat_facts as _signing_seat_facts,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    source_complete as _source_complete,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    source_ids as _source_ids,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    source_position as _source_position,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    ticket_facts as _ticket_facts,
)
from ctower_kernel.projections.project_delivery import (
    CheckpointDefinition,
    DeliveryFacts,
    DeliveryState,
    DeliverySurfaceDeclaration,
    delivery_surface_from_columns,
    derive_project_delivery_row,
)
from ctower_kernel.record.transaction import project_delivery_scope_transaction

__all__: tuple[str, ...] = ()
_PORTFOLIO_SCOPE = "all-projects"


def reconcile(dsn: str, tenant_id: UUID, *, now: datetime) -> int:
    """Recompute stored rows at one scoped Record-position snapshot."""

    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as connection:
        connection.execute("SET ROLE ctower_projection")
        with project_delivery_scope_transaction(connection, tenant_id, _PORTFOLIO_SCOPE):
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            return _reconcile(connection, tenant_id, now=now, rebuild_generation=None)


def rebuild(dsn: str, tenant_id: UUID, *, now: datetime) -> int:
    """Delete disposable rows and reproduce their semantic values in one snapshot."""

    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as connection:
        connection.execute("SET ROLE ctower_projection")
        with project_delivery_scope_transaction(connection, tenant_id, _PORTFOLIO_SCOPE):
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            generation = _next_generation(connection, tenant_id)
            connection.execute(
                "DELETE FROM project_delivery_projection_rows WHERE tenant_id = %s",
                (tenant_id,),
            )
            return _reconcile(
                connection,
                tenant_id,
                now=now,
                rebuild_generation=generation,
            )


def _reconcile(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    *,
    now: datetime,
    rebuild_generation: int | None,
) -> int:
    active_events = frozenset(_active_checkpoint_event_ids(connection, tenant_id))
    definitions = _definitions(connection, tenant_id, active_events)
    removed = _delete_inactive_rows(connection, tenant_id, definitions)
    if not definitions:
        return removed
    project_keys = tuple(dict.fromkeys(str(row["project_key"]) for row in definitions))
    project_states: list[tuple[str, list[dict[str, object]], int, bool, int]] = []
    for project_key in project_keys:
        project_definitions = [row for row in definitions if str(row["project_key"]) == project_key]
        event_ids = tuple(cast(UUID, row["event_id"]) for row in project_definitions)
        source = _source_position(connection, tenant_id, project_key, event_ids)
        complete = _source_complete(
            connection, tenant_id, project_definitions, source, active_events
        )
        projection = source if complete else _prior_projection(connection, tenant_id, project_key)
        project_states.append((project_key, project_definitions, source, complete, projection))
    generation = (
        rebuild_generation
        if rebuild_generation is not None
        else _current_generation(connection, tenant_id)
    )
    cutover = _cutover_claims(connection, tenant_id)
    affected = removed
    for project_key, project_definitions, source, complete, projection in project_states:
        if rebuild_generation is None and _up_to_date(
            connection,
            tenant_id,
            project_key,
            row_count=len(project_definitions),
            source=source,
            projection=projection,
            complete=complete,
            now=now,
        ):
            continue
        for definition_row in project_definitions:
            definition, facts = _facts(
                connection,
                tenant_id,
                definition_row,
                source=source,
                projection=projection,
                complete=complete,
                generation=generation,
                cutover=cutover,
                now=now,
            )
            row = derive_project_delivery_row(definition, facts)
            affected += _store_row(
                connection,
                tenant_id,
                project_key,
                row.response_payload(),
                source=source,
                projection=projection,
                now=now,
            )
    return affected


def _definitions(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    event_ids: frozenset[UUID],
) -> list[dict[str, object]]:
    if not event_ids:
        return []
    return connection.execute(
        """
        SELECT *
        FROM project_delivery_checkpoint_definitions
        WHERE tenant_id = %s AND event_id = ANY(%s)
        ORDER BY project_key, ordered_position
        """,
        (tenant_id, list(event_ids)),
    ).fetchall()


def _facts(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    row: dict[str, object],
    *,
    source: int,
    projection: int,
    complete: bool,
    generation: int,
    cutover: dict[str, str],
    now: datetime,
) -> tuple[CheckpointDefinition, DeliveryFacts]:
    criteria_rows = _criteria_rows(connection, tenant_id, row)
    criteria = tuple(str(item["criterion_key"]) for item in criteria_rows)
    # One shared read of every configured proof link; criterion coverage and slot
    # coverage are two compositions of the same resolved facts, never two predicates.
    project_key = str(row["project_key"])
    link_states = _proof_link_states(connection, tenant_id, project_key, criteria_rows)
    proven = frozenset(
        str(item["criterion_key"]) for item in criteria_rows if _criterion_proven(item, link_states)
    )
    ticket_ids = tuple(
        item["proof_ticket_id"]
        for item in criteria_rows
        if isinstance(item["proof_ticket_id"], UUID)
    )
    maturity, blockers, authorized_ticket_ids = _ticket_facts(
        connection, tenant_id, project_key, ticket_ids
    )
    signing_seats = _signing_seat_facts(connection, tenant_id, project_key, criteria_rows)
    slots = _qualifying_stage_slots(criteria_rows, link_states, signing_seats)
    source_ids = tuple(
        sorted(
            {
                *_source_ids(row, criteria_rows, authorized_ticket_ids),
                *(f"evidence:{fact.evidence_id}" for fact in signing_seats.values()),
                *(fact.assignment_source_id for fact in signing_seats.values()),
            }
        )
    )
    links_complete = all(state.project_present for state in link_states.values())
    states = frozenset(
        DeliveryState(str(value)) for value in cast(list[object], row["applicable_states"])
    )
    definition = CheckpointDefinition(
        key=str(row["checkpoint_key"]),
        label=str(row["checkpoint_label"]),
        outcome=str(row["outcome"]),
        accountable_owner=str(row["accountable_owner"]),
        criteria=criteria,
        applicable_states=states,
        delivery_surface=_delivery_surface(row),
    )
    facts = DeliveryFacts(
        maturity=maturity,
        proven_criteria=proven,
        effective_blockers=blockers,
        source_ids=source_ids,
        source_watermark=source,
        projection_watermark=projection,
        last_reconciled_at=now,
        observed_at=now,
        source_complete=complete and links_complete,
        cp3_d_proven=cutover["durability"] == "CP3_D_PROVEN",
        qualifying_stage_slots=slots,
        durability=cutover["durability"],
        recovery=cutover["recovery"],
        data_class=cutover["data_class"],
        rebuild_generation=generation,
    )
    return definition, facts


def _criteria_rows(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    row: dict[str, object],
) -> list[dict[str, object]]:
    return connection.execute(
        """
        SELECT criterion.criterion_key, criterion.proof_ticket_id,
            criterion.proof_criterion_key, criterion.source_ids,
            criterion.assigned_seat_key,
            member.seat_label AS assigned_seat_label,
            catalog.catalog_key AS assigned_catalog_key,
            catalog.catalog_revision AS assigned_catalog_revision,
            encode(catalog.catalog_digest, 'hex') AS assigned_catalog_digest
        FROM project_delivery_exit_criteria AS criterion
        LEFT JOIN project_delivery_seat_catalog_members AS member
          ON member.seat_catalog_revision_id = criterion.assigned_seat_catalog_revision_id
         AND member.tenant_id = criterion.tenant_id
         AND member.seat_key = criterion.assigned_seat_key
        LEFT JOIN project_delivery_seat_catalog_revisions AS catalog
          ON catalog.seat_catalog_revision_id = member.seat_catalog_revision_id
         AND catalog.tenant_id = member.tenant_id
        WHERE criterion.tenant_id = %s AND criterion.checkpoint_definition_id = %s
        ORDER BY criterion.ordinal
        """,
        (tenant_id, row["checkpoint_definition_id"]),
    ).fetchall()


def _delete_inactive_rows(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    definitions: list[dict[str, object]],
) -> int:
    projects = [str(row["project_key"]) for row in definitions]
    checkpoints = [str(row["checkpoint_key"]) for row in definitions]
    if not definitions:
        return connection.execute(
            "DELETE FROM project_delivery_projection_rows WHERE tenant_id = %s",
            (tenant_id,),
        ).rowcount
    return connection.execute(
        """
        DELETE FROM project_delivery_projection_rows AS projection
        WHERE projection.tenant_id = %s
          AND NOT EXISTS (
            SELECT 1
            FROM unnest(%s::text[], %s::text[])
              AS active(project_key, checkpoint_key)
            WHERE active.project_key = projection.project_key
              AND active.checkpoint_key = projection.checkpoint_key
          )
        """,
        (tenant_id, projects, checkpoints),
    ).rowcount


def _up_to_date(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str,
    *,
    row_count: int,
    source: int,
    projection: int,
    complete: bool,
    now: datetime,
) -> bool:
    row = connection.execute(
        """
        SELECT count(*) AS count,
            COALESCE(MIN(source_watermark), 0) AS source,
            COALESCE(MIN(projection_watermark), 0) AS projection,
            MIN((row_payload ->> 'freshness_due_at')::timestamptz) AS due,
            bool_and(
              NOT (row_payload -> 'derivation_reasons' ? 'source_incomplete')
            ) AS source_complete
        FROM project_delivery_projection_rows WHERE tenant_id = %s AND project_key = %s
        """,
        (tenant_id, project_key),
    ).fetchone()
    if row is None or row["due"] is None:
        return False
    return bool(
        int(cast(int, row["count"])) == row_count
        and int(cast(int, row["source"])) == source
        and int(cast(int, row["projection"])) == projection
        and bool(row["source_complete"]) is complete
        and cast(datetime, row["due"]) > now
    )


def _store_row(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str,
    payload: dict[str, object],
    *,
    source: int,
    projection: int,
    now: datetime,
) -> int:
    result = connection.execute(
        """
        INSERT INTO project_delivery_projection_rows (
            tenant_id, project_key, checkpoint_key, row_payload,
            source_watermark, projection_watermark, reconciled_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, project_key, checkpoint_key) DO UPDATE SET
            row_payload = EXCLUDED.row_payload,
            source_watermark = EXCLUDED.source_watermark,
            projection_watermark = EXCLUDED.projection_watermark,
            reconciled_at = EXCLUDED.reconciled_at
        """,
        (
            tenant_id,
            project_key,
            payload["checkpoint_key"],
            Jsonb(payload),
            source,
            projection,
            now,
        ),
    )
    return result.rowcount


def _prior_projection(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str,
) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MIN(projection_watermark), 0) AS value
        FROM project_delivery_projection_rows WHERE tenant_id = %s AND project_key = %s
        """,
        (tenant_id, project_key),
    ).fetchone()
    return int(cast(int, row["value"])) if row is not None else 0


def _current_generation(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX((row_payload ->> 'rebuild_generation')::integer), 0) AS value
        FROM project_delivery_projection_rows WHERE tenant_id = %s
        """,
        (tenant_id,),
    ).fetchone()
    return int(cast(int, row["value"])) if row is not None else 0


def _next_generation(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> int:
    return _current_generation(connection, tenant_id) + 1


def _delivery_surface(row: dict[str, object]) -> DeliverySurfaceDeclaration:
    return delivery_surface_from_columns(
        row["landing_boundary"],
        row["non_production_environments"],
        row["externally_effective_outcome"],
    )
