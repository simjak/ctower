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
        fact = connection.execute(
            """
            SELECT * FROM ctower_project_cutover_facts
            WHERE tenant_id = %s
            ORDER BY recorded_at DESC, fact_sequence DESC
            LIMIT 1
            """,
            (actor.tenant_id,),
        ).fetchone()
        if fact is None:
            return CtowerProjectCutoverHealth()
        projection_stats = connection.execute(
            """
            SELECT
                count(*) AS row_count,
                COALESCE(MIN(source_watermark), 0) AS min_source,
                COALESCE(MAX(source_watermark), 0) AS max_source,
                COALESCE(MIN(projection_watermark), 0) AS min_projection,
                COALESCE(MAX(projection_watermark), 0) AS max_projection
            FROM project_delivery_projection_rows WHERE tenant_id = %s
            """,
            (actor.tenant_id,),
        ).fetchone()
    source = int(cast(int, fact["source_watermark"]))
    stats = cast(dict[str, int], projection_stats)
    projected = stats["max_projection"]
    empty_current = stats["row_count"] == 0 and source == 0
    all_rows_current = (
        stats["row_count"] > 0
        and stats["min_source"]
        == stats["max_source"]
        == stats["min_projection"]
        == stats["max_projection"]
        == source
    )
    complete = "current" if empty_current or all_rows_current else "STATE_UNKNOWN"
    split_brain = str(fact["split_brain"])
    fence = str(fact["legacy_writer_fence"])
    writes_enabled = bool(fact["writes_enabled"])
    if complete == "STATE_UNKNOWN" or split_brain != "clear" or fence == "unknown":
        writes_enabled = False
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
