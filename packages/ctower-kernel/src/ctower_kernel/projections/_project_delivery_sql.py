"""Read-only Postgres queries for I1.7 authority and Project Delivery."""

from __future__ import annotations

from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.projections.project_delivery import (
    CtowerProjectCutoverHealth,
    DeliveryState,
    ProjectDeliveryRow,
    ProjectDeliveryView,
)
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def cutover_health(dsn: str, actor: Actor) -> CtowerProjectCutoverHealth:
    """Return the latest append-only fact, defaulting safely before I1.7B/C."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        fact, ambiguous = _select_authority_fact(connection, actor.tenant_id)
        stats = _projection_stats(connection, actor.tenant_id)
    source = int(cast(int, fact["source_watermark"])) if fact is not None else 0
    projected = stats["max_projection"]
    complete = _completeness(stats, source, fact_present=fact is not None, ambiguous=ambiguous)
    split_brain = str(fact["split_brain"]) if fact is not None else "clear"
    fence = str(fact["legacy_writer_fence"]) if fact is not None else "not_armed"
    writes_enabled = bool(fact["writes_enabled"]) if fact is not None else False
    if complete == "STATE_UNKNOWN" or split_brain != "clear" or fence == "unknown":
        writes_enabled = False
    if fact is None:
        return CtowerProjectCutoverHealth(
            projection_completeness=complete,
            source_watermark=source,
            projection_watermark=projected,
            writes_enabled=writes_enabled,
            legacy_writer_fence=fence,
            split_brain=split_brain,
        )
    return CtowerProjectCutoverHealth(
        cutover_id=cast(UUID, fact["cutover_id"]),
        authority_mode=str(fact["authority_mode"]),
        phase=str(fact["phase"]),
        writes_enabled=writes_enabled,
        durability_claim=str(fact["durability_claim"]),
        recovery_claim=str(fact["recovery_claim"]),
        data_class=str(fact["data_class"]),
        legacy_writer_fence=fence,
        split_brain=split_brain,
        projection_completeness=complete,
        source_watermark=source,
        projection_watermark=projected,
    )


def project_delivery(
    dsn: str,
    actor: Actor,
    project_key: str,
) -> ProjectDeliveryView | None:
    """Return stored rows for exactly one tenant/project without catch-up."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        rows = connection.execute(
            """
            SELECT row.row_payload, definition.company_key
            FROM project_delivery_projection_rows AS row
            JOIN LATERAL (
                SELECT company_key, ordered_position
                FROM project_delivery_checkpoint_definitions
                WHERE tenant_id = row.tenant_id
                  AND project_key = row.project_key
                  AND checkpoint_key = row.checkpoint_key
                ORDER BY definition_revision DESC LIMIT 1
            ) AS definition ON true
            WHERE row.tenant_id = %s AND row.project_key = %s
            ORDER BY definition.ordered_position, row.checkpoint_key
            """,
            (actor.tenant_id, project_key),
        ).fetchall()
    if not rows:
        return None
    company_key = str(rows[0]["company_key"])
    return ProjectDeliveryView(
        company_key=company_key,
        project_key=project_key,
        rows=tuple(_row(cast(dict[str, object], item["row_payload"])) for item in rows),
    )


def _select_authority_fact(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> tuple[dict[str, object] | None, bool]:
    """Select the latest fact by transactional append order within one cutover.

    The repository's authority order is the transactional ``events.record_position``
    with an ``event_id`` tie-break (matching ``0013_durability_authority.sql``), not
    the caller-supplied ``recorded_at`` wall clock, so a backdated or restored
    correction cannot suppress a newer armed fact. Returns ``(fact, ambiguous)``;
    when more than one cutover lineage has facts the active cutover is ambiguous
    and the caller must fail closed rather than silently picking one.
    """

    lineages = connection.execute(
        "SELECT DISTINCT cutover_id FROM ctower_project_cutover_facts WHERE tenant_id = %s",
        (tenant_id,),
    ).fetchall()
    if not lineages:
        return None, False
    if len(lineages) > 1:
        return None, True
    fact = connection.execute(
        """
        SELECT fact.*
        FROM ctower_project_cutover_facts AS fact
        JOIN events AS event
          ON event.event_id = fact.event_id
         AND event.tenant_id = fact.tenant_id
        WHERE fact.tenant_id = %s
        ORDER BY event.record_position DESC, fact.event_id DESC
        LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()
    return fact, False


def _projection_stats(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT
            count(*) AS row_count,
            COALESCE(MIN(source_watermark), 0) AS min_source,
            COALESCE(MAX(source_watermark), 0) AS max_source,
            COALESCE(MIN(projection_watermark), 0) AS min_projection,
            COALESCE(MAX(projection_watermark), 0) AS max_projection
        FROM project_delivery_projection_rows WHERE tenant_id = %s
        """,
        (tenant_id,),
    ).fetchone()
    if row is None:
        return {
            "row_count": 0,
            "min_source": 0,
            "max_source": 0,
            "min_projection": 0,
            "max_projection": 0,
        }
    return cast(dict[str, int], row)


def _completeness(
    stats: dict[str, int],
    source: int,
    *,
    fact_present: bool,
    ambiguous: bool,
) -> str:
    """Report projection completeness truthfully, failing closed on uncertainty.

    Ambiguous authority, or any delivery row without a corresponding authority
    fact, renders completeness ``STATE_UNKNOWN``; the pristine empty case (no
    fact and no rows) is the only no-fact state that stays ``current``.
    """

    if ambiguous:
        return "STATE_UNKNOWN"
    if not fact_present:
        return "STATE_UNKNOWN" if stats["row_count"] > 0 else "current"
    empty_current = stats["row_count"] == 0 and source == 0
    all_rows_current = (
        stats["row_count"] > 0
        and stats["min_source"]
        == stats["max_source"]
        == stats["min_projection"]
        == stats["max_projection"]
        == source
    )
    return "current" if empty_current or all_rows_current else "STATE_UNKNOWN"


def _row(payload: dict[str, object]) -> ProjectDeliveryRow:
    criteria = cast(dict[str, object], payload["criteria"])
    return ProjectDeliveryRow(
        checkpoint_key=str(payload["checkpoint_key"]),
        checkpoint_label=str(payload["checkpoint_label"]),
        headline_state=DeliveryState(str(payload["headline_state"])),
        underlying_maturity=DeliveryState(str(payload["underlying_maturity"])),
        outcome=str(payload["outcome"]),
        accountable_owner=str(payload["accountable_owner"]),
        proven_criteria=int(cast(int, criteria["proven"])),
        declared_criteria=int(cast(int, criteria["declared"])),
        source_watermark=int(cast(int, payload["source_watermark"])),
        projection_watermark=int(cast(int, payload["projection_watermark"])),
        freshness=str(payload["freshness"]),
        confidence=str(payload["confidence"]),
        health=str(payload["health"]),
        source_ids=tuple(str(item) for item in cast(list[object], payload["source_ids"])),
        derivation_reasons=tuple(
            str(item) for item in cast(list[object], payload["derivation_reasons"])
        ),
    )
