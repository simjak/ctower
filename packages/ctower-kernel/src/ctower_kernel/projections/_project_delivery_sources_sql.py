"""Authoritative source reads for Project Delivery reconciliation."""

from __future__ import annotations

from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.projections.project_delivery import DeliveryState

__all__: tuple[str, ...] = ()
_CHECKPOINT_COUNT = 14


def criterion_proven(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    criterion: dict[str, object],
) -> bool:
    ticket_id = criterion["proof_ticket_id"]
    proof_key = criterion["proof_criterion_key"]
    if not isinstance(ticket_id, UUID) or not isinstance(proof_key, str):
        return False
    row = connection.execute(
        """
        SELECT verdict.verdict_id, verdict.decision
        FROM proof_bundles AS bundle
        JOIN proof_verdicts AS verdict
          ON verdict.proof_id = bundle.proof_id AND verdict.tenant_id = bundle.tenant_id
        WHERE bundle.tenant_id = %s AND bundle.ticket_id = %s
          AND verdict.criterion_key = %s
          AND verdict.candidate_digest = bundle.candidate_digest
          AND NOT EXISTS (
              SELECT 1 FROM proof_invalidations AS invalidation
              WHERE invalidation.proof_id = verdict.proof_id
                AND invalidation.tenant_id = verdict.tenant_id
                AND invalidation.target_kind = 'verdict'
                AND invalidation.target_id = verdict.verdict_id
          )
        ORDER BY verdict.proof_sequence DESC LIMIT 1
        """,
        (tenant_id, ticket_id, proof_key),
    ).fetchone()
    return row is not None and str(row["decision"]) == "pass"


def ticket_facts(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_ids: tuple[UUID, ...],
) -> tuple[DeliveryState, tuple[str, ...]]:
    if not ticket_ids:
        return DeliveryState.PLANNED, ()
    rows = connection.execute(
        """
        SELECT ticket_id, lane, delivery_facts
        FROM board_projection_rows
        WHERE tenant_id = %s AND ticket_id = ANY(%s)
        """,
        (tenant_id, list(ticket_ids)),
    ).fetchall()
    blockers = connection.execute(
        """
        SELECT blocker_id FROM blocker_heads
        WHERE tenant_id = %s AND ticket_id = ANY(%s) AND resolved_at IS NULL
        ORDER BY blocker_id
        """,
        (tenant_id, list(ticket_ids)),
    ).fetchall()
    maturity = max(
        (_maturity(row) for row in rows),
        key=_maturity_rank,
        default=DeliveryState.PLANNED,
    )
    return maturity, tuple(f"blocker:{row['blocker_id']}" for row in blockers)


def source_ids(
    definition: dict[str, object],
    criteria: list[dict[str, object]],
    ticket_ids: tuple[UUID, ...],
) -> tuple[str, ...]:
    configured = (
        str(value)
        for criterion in criteria
        for value in cast(list[object], criterion["source_ids"])
    )
    return tuple(
        sorted(
            {
                f"catalog:{definition['catalog_revision']}",
                *(f"ticket:{ticket_id}" for ticket_id in ticket_ids),
                *configured,
            }
        )
    )


def source_position(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(record_position), 0) AS value FROM events WHERE tenant_id = %s",
        (tenant_id,),
    ).fetchone()
    return int(cast(int, row["value"])) if row is not None else 0


def source_complete(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    definitions: list[dict[str, object]],
) -> bool:
    streams = connection.execute(
        """
        SELECT stream_id, count(*) AS count, min(sequence) AS minimum, max(sequence) AS maximum
        FROM events WHERE tenant_id = %s GROUP BY stream_id
        """,
        (tenant_id,),
    ).fetchall()
    contiguous = all(
        int(cast(int, row["minimum"])) == 1
        and int(cast(int, row["maximum"])) == int(cast(int, row["count"]))
        for row in streams
    )
    board = connection.execute(
        """
        SELECT blocked_outbox_id FROM outbox_consumer_cursors
        WHERE consumer_key = 'board_projection' AND tenant_id = %s
          AND topic = 'record.events'
        """,
        (tenant_id,),
    ).fetchone()
    board_complete = board is None or board["blocked_outbox_id"] is None
    projects = {(str(row["project_key"]), str(row["checkpoint_key"])) for row in definitions}
    checkpoint_complete = bool(projects) and all(
        sum(1 for item in projects if item[0] == project) == _CHECKPOINT_COUNT
        for project, _ in projects
    )
    return contiguous and board_complete and checkpoint_complete


def cutover_claims(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> dict[str, str]:
    row = connection.execute(
        """
        SELECT durability_claim, recovery_claim, data_class
        FROM ctower_project_cutover_facts
        WHERE tenant_id = %s ORDER BY fact_sequence DESC, cutover_fact_id DESC LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()
    if row is None:
        return {
            "durability": "CP3_D_NOT_PROVEN",
            "recovery": "EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
            "data_class": "RECONSTRUCTIBLE_ONLY",
        }
    return {
        "durability": str(row["durability_claim"]),
        "recovery": str(row["recovery_claim"]),
        "data_class": str(row["data_class"]),
    }


def _maturity(row: dict[str, object]) -> DeliveryState:
    facts = {str(item) for item in cast(list[object], row["delivery_facts"])}
    if "production_verified" in facts:
        return DeliveryState.RELEASED
    if "staging_verified" in facts:
        return DeliveryState.VERIFIED
    if "change_merged" in facts:
        return DeliveryState.MERGED
    return {
        "backlog": DeliveryState.PLANNED,
        "ready": DeliveryState.IN_PROGRESS,
        "in_progress": DeliveryState.IN_PROGRESS,
        "in_review": DeliveryState.READY_TO_LAND,
        "blocked": DeliveryState.IN_PROGRESS,
        "complete": DeliveryState.VERIFIED,
    }.get(str(row["lane"]), DeliveryState.PLANNED)


def _maturity_rank(state: DeliveryState) -> int:
    return (
        DeliveryState.PLANNED,
        DeliveryState.IN_PROGRESS,
        DeliveryState.READY_TO_LAND,
        DeliveryState.MERGED,
        DeliveryState.VERIFIED,
        DeliveryState.RELEASED,
    ).index(state)
