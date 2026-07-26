"""Worker-owned deterministic Project Delivery reconcile and rebuild."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_kernel.projections._project_delivery_sources_sql import (
    criterion_proven as _criterion_proven,
)
from ctower_kernel.projections._project_delivery_sources_sql import (
    cutover_claims as _cutover_claims,
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
    derive_project_delivery_row,
)

__all__: tuple[str, ...] = ()


def reconcile(dsn: str, tenant_id: UUID, *, now: datetime) -> int:
    """Recompute stored rows at one scoped Record-position snapshot."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("SET ROLE ctower_projection")
        return _reconcile(connection, tenant_id, now=now, rebuild_generation=None)


def rebuild(dsn: str, tenant_id: UUID, *, now: datetime) -> int:
    """Delete disposable rows and reproduce their semantic values in one snapshot."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("SET ROLE ctower_projection")
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
    definitions = _definitions(connection, tenant_id)
    if not definitions:
        return 0
    source = _source_position(connection, tenant_id)
    complete = _source_complete(connection, tenant_id, definitions, source)
    projection = source if complete else _prior_projection(connection, tenant_id)
    generation = (
        rebuild_generation
        if rebuild_generation is not None
        else _current_generation(connection, tenant_id)
    )
    cutover = _cutover_claims(connection, tenant_id)
    if rebuild_generation is None and _up_to_date(
        connection,
        tenant_id,
        row_count=len(definitions),
        source=source,
        projection=projection,
        complete=complete,
        now=now,
    ):
        return 0
    affected = 0
    for definition_row in definitions:
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
            str(definition_row["project_key"]),
            row.response_payload(),
            source=source,
            projection=projection,
            now=now,
        )
    return affected


def _definitions(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> list[dict[str, object]]:
    return connection.execute(
        """
        SELECT DISTINCT ON (project_key, checkpoint_key) *
        FROM project_delivery_checkpoint_definitions
        WHERE tenant_id = %s
        ORDER BY project_key, checkpoint_key, definition_revision DESC
        """,
        (tenant_id,),
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
    criteria_rows = connection.execute(
        """
        SELECT criterion_key, proof_ticket_id, proof_criterion_key, source_ids
        FROM project_delivery_exit_criteria
        WHERE tenant_id = %s AND checkpoint_definition_id = %s
        ORDER BY ordinal
        """,
        (tenant_id, row["checkpoint_definition_id"]),
    ).fetchall()
    criteria = tuple(str(item["criterion_key"]) for item in criteria_rows)
    proven = frozenset(
        str(item["criterion_key"])
        for item in criteria_rows
        if _criterion_proven(connection, tenant_id, item)
    )
    ticket_ids = tuple(
        item["proof_ticket_id"]
        for item in criteria_rows
        if isinstance(item["proof_ticket_id"], UUID)
    )
    maturity, blockers = _ticket_facts(connection, tenant_id, ticket_ids)
    source_ids = _source_ids(row, criteria_rows, ticket_ids)
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
        source_complete=complete,
        cp3_d_proven=cutover["durability"] == "CP3_D_PROVEN",
        durability=cutover["durability"],
        recovery=cutover["recovery"],
        data_class=cutover["data_class"],
        rebuild_generation=generation,
    )
    return definition, facts


def _up_to_date(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
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
            bool_and((row_payload ->> 'health') <> 'STATE_UNKNOWN') AS known
        FROM project_delivery_projection_rows WHERE tenant_id = %s
        """,
        (tenant_id,),
    ).fetchone()
    if row is None or row["due"] is None:
        return False
    return bool(
        int(cast(int, row["count"])) == row_count
        and int(cast(int, row["source"])) == source
        and int(cast(int, row["projection"])) == projection
        and bool(row["known"]) is complete
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
) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MIN(projection_watermark), 0) AS value
        FROM project_delivery_projection_rows WHERE tenant_id = %s
        """,
        (tenant_id,),
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
