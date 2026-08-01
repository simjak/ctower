"""Authoritative source reads for Project Delivery reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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

# One evidence-and-verdict predicate, resolved once per configured link and composed by
# both criterion proof coverage and qualifying-stage slot coverage. It is two-valued by
# construction: `IS NOT DISTINCT FROM` keeps a missing, pending or invalidated verdict
# FALSE instead of NULL, so a slot the sources fully establish is never published as
# UNKNOWN. Whether the link resolves at all, and whether the ticket has a current stage,
# are reported separately, because only those can make a slot genuinely unestablishable.
_LINK_STATE_QUERY = """
SELECT requested.ticket_id, requested.proof_key,
  scoped_ticket.ticket_id IS NOT NULL AS project_present,
  criterion.criterion_key IS NOT NULL AS criterion_present,
  run.current_stage IS NOT NULL AS stage_present,
  (
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
      ) IS NOT DISTINCT FROM 'pass'
    )
  ) AS proven
FROM unnest(%s::uuid[], %s::text[]) AS requested(ticket_id, proof_key)
LEFT JOIN tickets AS scoped_ticket
  ON scoped_ticket.tenant_id = %s
 AND scoped_ticket.project_key = %s
 AND scoped_ticket.ticket_id = requested.ticket_id
LEFT JOIN workflow_runs AS run
  ON run.tenant_id = %s AND run.ticket_id = scoped_ticket.ticket_id
LEFT JOIN proof_bundles AS bundle
  ON bundle.tenant_id = %s AND bundle.ticket_id = scoped_ticket.ticket_id
LEFT JOIN proof_criteria AS criterion
  ON criterion.proof_id = bundle.proof_id
 AND criterion.tenant_id = bundle.tenant_id
 AND criterion.criterion_key = requested.proof_key
ORDER BY requested.ticket_id, requested.proof_key
"""


@dataclass(frozen=True, slots=True)
class ProofLinkState:
    """One configured proof link, resolved once for every derivation that needs it."""

    project_present: bool
    criterion_present: bool
    stage_present: bool
    proven: bool


type _LinkStates = Mapping[tuple[UUID, str], ProofLinkState]


def proof_link_states(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str,
    criteria: list[dict[str, object]],
) -> _LinkStates:
    """Resolve every proof link these exit criteria configure, in one read.

    The configured links drive the row set, so no criterion the checkpoint never
    configured can reach either derivation, and an unresolved link still returns its own
    row.
    """

    requested = _configured_links(criteria)
    if not requested:
        return {}
    rows = connection.execute(
        _LINK_STATE_QUERY,
        (
            [ticket_id for ticket_id, _ in requested],
            [proof_key for _, proof_key in requested],
            tenant_id,
            project_key,
            tenant_id,
            tenant_id,
        ),
    ).fetchall()
    return {
        (cast(UUID, row["ticket_id"]), str(row["proof_key"])): ProofLinkState(
            project_present=bool(row["project_present"]),
            criterion_present=bool(row["criterion_present"]),
            stage_present=bool(row["stage_present"]),
            proven=bool(row["criterion_present"]) and bool(row["proven"]),
        )
        for row in rows
    }


def criterion_proven(criterion: dict[str, object], states: _LinkStates) -> bool:
    """Answer criterion proof coverage from the shared predicate."""

    link = _configured_link(criterion)
    if link is None:
        return False
    state = states.get(link)
    return state is not None and state.proven


def qualifying_stage_slots(
    criteria: list[dict[str, object]],
    states: _LinkStates,
) -> tuple[EvidenceSlotFact, ...]:
    """Derive required slot states without interpreting any stage key."""

    slots: dict[str, EvidenceSlotState] = {}
    for criterion in criteria:
        link = _configured_link(criterion)
        if link is None:
            _merge_slot_state(
                slots,
                str(criterion["criterion_key"]),
                EvidenceSlotState.UNKNOWN,
            )
            continue
        _merge_slot_state(slots, link[1], _slot_state(states.get(link)))
    return _slot_facts(slots)


def ticket_facts(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str,
    ticket_ids: tuple[UUID, ...],
) -> tuple[DeliveryState, tuple[str, ...], tuple[UUID, ...]]:
    if not ticket_ids:
        return DeliveryState.PLANNED, (), ()
    rows = connection.execute(
        """
        SELECT ticket_id, lane, delivery_facts
        FROM board_projection_rows
        WHERE tenant_id = %s AND project_key = %s AND ticket_id = ANY(%s)
        """,
        (tenant_id, project_key, list(ticket_ids)),
    ).fetchall()
    blockers = connection.execute(
        """
        SELECT blocker.blocker_id
        FROM blocker_heads AS blocker
        JOIN tickets AS ticket
          ON ticket.tenant_id = blocker.tenant_id
         AND ticket.ticket_id = blocker.ticket_id
        WHERE blocker.tenant_id = %s AND ticket.project_key = %s
          AND blocker.ticket_id = ANY(%s) AND blocker.resolved_at IS NULL
        ORDER BY blocker.blocker_id
        """,
        (tenant_id, project_key, list(ticket_ids)),
    ).fetchall()
    maturity = max(
        (_maturity(row) for row in rows),
        key=_maturity_rank,
        default=DeliveryState.PLANNED,
    )
    return (
        maturity,
        tuple(f"blocker:{row['blocker_id']}" for row in blockers),
        tuple(cast(UUID, row["ticket_id"]) for row in rows),
    )


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
    project_key: str,
    definition_event_ids: tuple[UUID, ...],
) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(event.record_position), 0) AS value
        FROM events AS event
        WHERE event.tenant_id = %s
          AND (
            event.kind = 'catalog.bundle_activated'
            OR event.event_id = ANY(%s)
            OR event.payload ->> 'project_key' = %s
            OR EXISTS (
              SELECT 1
              FROM event_links AS link
              JOIN tickets AS ticket
                ON ticket.tenant_id = link.tenant_id
               AND ticket.ticket_id = link.subject_id
              WHERE link.tenant_id = event.tenant_id
                AND link.event_id = event.event_id
                AND link.subject_kind = 'ticket'
                AND ticket.project_key = %s
            )
          )
        """,
        (tenant_id, list(definition_event_ids), project_key, project_key),
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


def _configured_links(criteria: list[dict[str, object]]) -> tuple[tuple[UUID, str], ...]:
    """The distinct proof links these exit criteria configure, in configured order."""

    links: dict[tuple[UUID, str], None] = {}
    for criterion in criteria:
        link = _configured_link(criterion)
        if link is not None:
            links[link] = None
    return tuple(links)


def _configured_link(criterion: dict[str, object]) -> tuple[UUID, str] | None:
    ticket_id = criterion["proof_ticket_id"]
    proof_key = criterion["proof_criterion_key"]
    if isinstance(ticket_id, UUID) and isinstance(proof_key, str):
        return ticket_id, proof_key
    return None


def _slot_state(state: ProofLinkState | None) -> EvidenceSlotState:
    """Only an unresolvable link or a stageless ticket may publish UNKNOWN."""

    if state is None or not state.criterion_present or not state.stage_present:
        return EvidenceSlotState.UNKNOWN
    return EvidenceSlotState.FILLED if state.proven else EvidenceSlotState.UNFILLED


def _slot_facts(states: dict[str, EvidenceSlotState]) -> tuple[EvidenceSlotFact, ...]:
    return tuple(EvidenceSlotFact(key, states[key]) for key in sorted(states))
