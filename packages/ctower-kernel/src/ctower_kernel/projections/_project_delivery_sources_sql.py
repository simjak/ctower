"""Authoritative source reads for Project Delivery reconciliation."""

from __future__ import annotations

from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.projections.project_delivery import (
    DeliveryState,
    EvidenceSlotFact,
    EvidenceSlotState,
)

__all__: tuple[str, ...] = ()

_SLOT_STATE_RANK = {
    EvidenceSlotState.FILLED: 0,
    EvidenceSlotState.UNFILLED: 1,
    EvidenceSlotState.UNKNOWN: 2,
}


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
        SELECT criterion.requires_verdict,
          EXISTS (
            SELECT 1
            FROM proof_evidence AS evidence
            WHERE evidence.proof_id = criterion.proof_id
              AND evidence.tenant_id = criterion.tenant_id
              AND evidence.criterion_key = criterion.criterion_key
              AND (
                NOT criterion.candidate_dependent
                OR evidence.candidate_digest = bundle.candidate_digest
              )
              AND NOT EXISTS (
                SELECT 1 FROM proof_invalidations AS invalidation
                WHERE invalidation.proof_id = evidence.proof_id
                  AND invalidation.tenant_id = evidence.tenant_id
                  AND invalidation.target_kind = 'evidence'
                  AND invalidation.target_id = evidence.evidence_id
              )
          ) AS has_evidence,
          (
            SELECT verdict.decision
            FROM proof_verdicts AS verdict
            WHERE verdict.proof_id = criterion.proof_id
              AND verdict.tenant_id = criterion.tenant_id
              AND verdict.criterion_key = criterion.criterion_key
              AND (
                NOT criterion.candidate_dependent
                OR verdict.candidate_digest = bundle.candidate_digest
              )
              AND NOT EXISTS (
                SELECT 1 FROM proof_invalidations AS invalidation
                WHERE invalidation.proof_id = verdict.proof_id
                  AND invalidation.tenant_id = verdict.tenant_id
                  AND invalidation.target_kind = 'verdict'
                  AND invalidation.target_id = verdict.verdict_id
              )
            ORDER BY verdict.proof_sequence DESC
            LIMIT 1
          ) AS verdict
        FROM proof_bundles AS bundle
        JOIN proof_criteria AS criterion
          ON criterion.proof_id = bundle.proof_id
         AND criterion.tenant_id = bundle.tenant_id
        WHERE bundle.tenant_id = %s AND bundle.ticket_id = %s
          AND criterion.criterion_key = %s
        """,
        (tenant_id, ticket_id, proof_key),
    ).fetchone()
    return bool(
        row is not None
        and row["has_evidence"]
        and (not row["requires_verdict"] or row["verdict"] == "pass")
    )


def qualifying_stage_slots(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    criteria: list[dict[str, object]],
) -> tuple[EvidenceSlotFact, ...]:
    """Derive required slot states without interpreting any stage key."""

    requested, states = _configured_slot_requests(criteria)
    if not requested:
        return _slot_facts(states)
    rows = connection.execute(
        """
        SELECT requested.ticket_id, run.current_stage, criterion.criterion_key,
          CASE
            WHEN run.current_stage IS NULL OR criterion.criterion_key IS NULL
              THEN NULL
            ELSE (
              EXISTS (
                SELECT 1
                FROM proof_evidence AS evidence
                WHERE evidence.proof_id = criterion.proof_id
                  AND evidence.tenant_id = criterion.tenant_id
                  AND evidence.criterion_key = criterion.criterion_key
                  AND (
                    NOT criterion.candidate_dependent
                    OR evidence.candidate_digest = bundle.candidate_digest
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM proof_invalidations AS invalidation
                    WHERE invalidation.proof_id = evidence.proof_id
                      AND invalidation.tenant_id = evidence.tenant_id
                      AND invalidation.target_kind = 'evidence'
                      AND invalidation.target_id = evidence.evidence_id
                  )
              )
              AND (
                NOT criterion.requires_verdict
                OR (
                  SELECT verdict.decision
                  FROM proof_verdicts AS verdict
                  WHERE verdict.proof_id = criterion.proof_id
                    AND verdict.tenant_id = criterion.tenant_id
                    AND verdict.criterion_key = criterion.criterion_key
                    AND (
                      NOT criterion.candidate_dependent
                      OR verdict.candidate_digest = bundle.candidate_digest
                    )
                    AND NOT EXISTS (
                      SELECT 1 FROM proof_invalidations AS invalidation
                      WHERE invalidation.proof_id = verdict.proof_id
                        AND invalidation.tenant_id = verdict.tenant_id
                        AND invalidation.target_kind = 'verdict'
                        AND invalidation.target_id = verdict.verdict_id
                    )
                  ORDER BY verdict.proof_sequence DESC
                  LIMIT 1
                ) = 'pass'
              )
            )
          END AS filled
        FROM unnest(%s::uuid[]) AS requested(ticket_id)
        LEFT JOIN workflow_runs AS run
          ON run.tenant_id = %s AND run.ticket_id = requested.ticket_id
        LEFT JOIN proof_bundles AS bundle
          ON bundle.tenant_id = %s AND bundle.ticket_id = requested.ticket_id
        LEFT JOIN proof_criteria AS criterion
          ON criterion.proof_id = bundle.proof_id
         AND criterion.tenant_id = bundle.tenant_id
        ORDER BY requested.ticket_id, criterion.criterion_key
        """,
        (list(requested), tenant_id, tenant_id),
    ).fetchall()
    discovered: dict[UUID, set[str]] = {ticket_id: set() for ticket_id in requested}
    for row in rows:
        ticket_id = cast(UUID, row["ticket_id"])
        criterion_key = row["criterion_key"]
        if not isinstance(criterion_key, str):
            continue
        discovered[ticket_id].add(criterion_key)
        _merge_slot_state(states, criterion_key, _slot_state(row["filled"]))
    for ticket_id, proof_keys in requested.items():
        for proof_key in proof_keys.difference(discovered[ticket_id]):
            _merge_slot_state(states, proof_key, EvidenceSlotState.UNKNOWN)
    return _slot_facts(states)


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


def active_checkpoint_event_ids(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> tuple[UUID, ...]:
    """Read the ordered checkpoint set from the latest accepted bundle event."""

    rows = connection.execute(
        """
        WITH active AS (
          SELECT payload
          FROM events
          WHERE tenant_id = %s AND kind = 'catalog.bundle_activated'
          ORDER BY record_position DESC
          LIMIT 1
        )
        SELECT published.event_id
        FROM active
        CROSS JOIN LATERAL jsonb_array_elements_text(
          active.payload -> 'member_event_ids'
        ) WITH ORDINALITY AS member(event_id, ordinal)
        JOIN events AS published
          ON published.tenant_id = %s
         AND published.event_id = member.event_id::uuid
         AND published.kind = 'catalog.component_published'
        WHERE published.payload #>> '{component,kind}' = 'checkpoint'
        ORDER BY member.ordinal
        """,
        (tenant_id, tenant_id),
    ).fetchall()
    return tuple(cast(UUID, row["event_id"]) for row in rows)


def source_complete(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    definitions: list[dict[str, object]],
    source_watermark: int,
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
        SELECT acceptance_position, health, blocked_outbox_id
        FROM outbox_consumer_cursors
        WHERE consumer_key = 'board_projection' AND tenant_id = %s
          AND topic = 'record.events'
        """,
        (tenant_id,),
    ).fetchone()
    board_complete = (
        board is not None
        and board["blocked_outbox_id"] is None
        and board["health"] == "CURRENT"
        and int(cast(int, board["acceptance_position"])) >= source_watermark
    )
    active_events = set(active_checkpoint_event_ids(connection, tenant_id))
    materialized_events = {cast(UUID, row["event_id"]) for row in definitions}
    checkpoint_complete = active_events == materialized_events
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


def _merge_slot_state(
    states: dict[str, EvidenceSlotState],
    key: str,
    state: EvidenceSlotState,
) -> None:
    current = states.get(key)
    if current is None or _SLOT_STATE_RANK[state] > _SLOT_STATE_RANK[current]:
        states[key] = state


def _configured_slot_requests(
    criteria: list[dict[str, object]],
) -> tuple[dict[UUID, set[str]], dict[str, EvidenceSlotState]]:
    requested: dict[UUID, set[str]] = {}
    states: dict[str, EvidenceSlotState] = {}
    for criterion in criteria:
        ticket_id = criterion["proof_ticket_id"]
        proof_key = criterion["proof_criterion_key"]
        if isinstance(ticket_id, UUID) and isinstance(proof_key, str):
            requested.setdefault(ticket_id, set()).add(proof_key)
        else:
            _merge_slot_state(
                states,
                str(criterion["criterion_key"]),
                EvidenceSlotState.UNKNOWN,
            )
    return requested, states


def _slot_state(value: object) -> EvidenceSlotState:
    if value is None:
        return EvidenceSlotState.UNKNOWN
    return EvidenceSlotState.FILLED if value else EvidenceSlotState.UNFILLED


def _slot_facts(states: dict[str, EvidenceSlotState]) -> tuple[EvidenceSlotFact, ...]:
    return tuple(EvidenceSlotFact(key, states[key]) for key in sorted(states))
