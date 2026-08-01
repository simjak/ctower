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
    SeatCatalogReference,
    SeatIdentity,
)

__all__: tuple[str, ...] = ()

# One evidence-and-verdict predicate, resolved once per configured link and composed by
# both criterion proof coverage and qualifying-stage slot coverage. It is two-valued by
# construction: `IS NOT DISTINCT FROM` keeps a missing, pending or invalidated verdict
# FALSE instead of NULL, so a slot the sources fully establish is never published as
# UNKNOWN. Only an unresolved configured proof criterion is genuinely unestablishable;
# Workflow stage presence cannot disagree with the shared proof predicate.
_LINK_STATE_QUERY = """
SELECT requested.ticket_id, requested.proof_key,
  criterion.criterion_key IS NOT NULL AS criterion_present,
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
LEFT JOIN proof_bundles AS bundle
  ON bundle.tenant_id = %s AND bundle.ticket_id = requested.ticket_id
LEFT JOIN proof_criteria AS criterion
  ON criterion.proof_id = bundle.proof_id
 AND criterion.tenant_id = bundle.tenant_id
 AND criterion.criterion_key = requested.proof_key
ORDER BY requested.ticket_id, requested.proof_key
"""

_SIGNING_SEAT_QUERY = """
SELECT requested.ticket_id, requested.proof_key, evidence.evidence_id,
  assignment.assignment_ticket_id, assignment.assignment_kind,
  assignment.assignment_interval_sequence,
  member.seat_key, member.seat_label,
  catalog.catalog_key, catalog.catalog_revision,
  encode(catalog.catalog_digest, 'hex') AS catalog_digest
FROM unnest(%s::uuid[], %s::text[]) AS requested(ticket_id, proof_key)
JOIN proof_bundles AS bundle
  ON bundle.tenant_id = %s AND bundle.ticket_id = requested.ticket_id
JOIN proof_criteria AS criterion
  ON criterion.proof_id = bundle.proof_id
 AND criterion.tenant_id = bundle.tenant_id
 AND criterion.criterion_key = requested.proof_key
JOIN LATERAL (
  SELECT candidate.evidence_id
  FROM proof_evidence AS candidate
  WHERE candidate.proof_id = criterion.proof_id
    AND candidate.tenant_id = criterion.tenant_id
    AND candidate.criterion_key = criterion.criterion_key
    AND (
      NOT criterion.candidate_dependent
      OR candidate.candidate_digest = bundle.candidate_digest
    )
    AND NOT EXISTS (
      SELECT 1 FROM proof_invalidations AS invalidation
      WHERE invalidation.proof_id = candidate.proof_id
        AND invalidation.tenant_id = candidate.tenant_id
        AND invalidation.target_kind = 'evidence'
        AND invalidation.target_id = candidate.evidence_id
    )
  ORDER BY candidate.recorded_at DESC, candidate.evidence_id DESC
  LIMIT 1
) AS evidence ON true
JOIN proof_evidence_verifier_assignments AS assignment
  ON assignment.evidence_id = evidence.evidence_id
 AND assignment.tenant_id = criterion.tenant_id
JOIN assignment_interval_seat_facts AS seat_fact
  ON seat_fact.ticket_id = assignment.assignment_ticket_id
 AND seat_fact.tenant_id = assignment.tenant_id
 AND seat_fact.assignment_kind = assignment.assignment_kind
 AND seat_fact.interval_sequence = assignment.assignment_interval_sequence
JOIN project_delivery_seat_catalog_members AS member
  ON member.seat_catalog_revision_id = seat_fact.seat_catalog_revision_id
 AND member.tenant_id = seat_fact.tenant_id
 AND member.seat_key = seat_fact.seat_key
JOIN project_delivery_seat_catalog_revisions AS catalog
  ON catalog.seat_catalog_revision_id = member.seat_catalog_revision_id
 AND catalog.tenant_id = member.tenant_id
ORDER BY requested.ticket_id, requested.proof_key
"""


@dataclass(frozen=True, slots=True)
class ProofLinkState:
    """One configured proof link, resolved once for every derivation that needs it."""

    criterion_present: bool
    proven: bool


@dataclass(frozen=True, slots=True)
class SigningSeatFact:
    """A signing seat derived through one Evidence verifier assignment interval."""

    seat: SeatIdentity
    evidence_id: UUID
    assignment_source_id: str


type _LinkStates = Mapping[tuple[UUID, str], ProofLinkState]


def proof_link_states(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
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
        ),
    ).fetchall()
    return {
        (cast(UUID, row["ticket_id"]), str(row["proof_key"])): ProofLinkState(
            criterion_present=bool(row["criterion_present"]),
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
    signing_seats: Mapping[tuple[UUID, str], SigningSeatFact] | None = None,
) -> tuple[EvidenceSlotFact, ...]:
    """Derive required slot states without interpreting any stage key."""

    signing = {} if signing_seats is None else signing_seats
    slots: list[EvidenceSlotFact] = []
    for criterion in criteria:
        slot_key = str(criterion["criterion_key"])
        link = _configured_link(criterion)
        if link is None:
            slots.append(
                EvidenceSlotFact(
                    slot_key,
                    EvidenceSlotState.UNKNOWN,
                    assigned_seat=_assigned_seat(criterion),
                )
            )
            continue
        state = _slot_state(states.get(link))
        signed = signing.get(link)
        slots.append(
            EvidenceSlotFact(
                slot_key,
                state,
                assigned_seat=_assigned_seat(criterion),
                signing_seat=(
                    signed.seat
                    if signed is not None and state is EvidenceSlotState.FILLED
                    else None
                ),
            )
        )
    return tuple(sorted(slots, key=lambda slot: slot.key))


def signing_seat_facts(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    criteria: list[dict[str, object]],
) -> Mapping[tuple[UUID, str], SigningSeatFact]:
    """Resolve signing seats only through explicit Evidence assignment references."""

    requested = _configured_links(criteria)
    if not requested:
        return {}
    rows = connection.execute(
        _SIGNING_SEAT_QUERY,
        (
            [ticket_id for ticket_id, _ in requested],
            [proof_key for _, proof_key in requested],
            tenant_id,
        ),
    ).fetchall()
    return {
        (cast(UUID, row["ticket_id"]), str(row["proof_key"])): SigningSeatFact(
            seat=_seat(row),
            evidence_id=cast(UUID, row["evidence_id"]),
            assignment_source_id=(
                f"assignment:{row['assignment_ticket_id']}:"
                f"{row['assignment_kind']}:{row['assignment_interval_sequence']}"
            ),
        )
        for row in rows
    }


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
    seat_catalogs = (
        f"seat-catalog:{criterion['assigned_catalog_key']}@"
        f"{criterion['assigned_catalog_revision']}:"
        f"sha256:{criterion['assigned_catalog_digest']}"
        for criterion in criteria
        if criterion.get("assigned_seat_key") is not None
    )
    return tuple(
        sorted(
            {
                f"catalog:{definition['catalog_revision']}",
                *(f"ticket:{ticket_id}" for ticket_id in ticket_ids),
                *configured,
                *seat_catalogs,
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
    """Only an unresolvable configured proof criterion may publish UNKNOWN."""

    if state is None or not state.criterion_present:
        return EvidenceSlotState.UNKNOWN
    return EvidenceSlotState.FILLED if state.proven else EvidenceSlotState.UNFILLED


def _assigned_seat(criterion: dict[str, object]) -> SeatIdentity | None:
    if criterion.get("assigned_seat_key") is None:
        return None
    return _seat(criterion)


def _seat(row: Mapping[str, object]) -> SeatIdentity:
    return SeatIdentity(
        key=str(row["seat_key"] if "seat_key" in row else row["assigned_seat_key"]),
        label=str(row["seat_label"] if "seat_label" in row else row["assigned_seat_label"]),
        catalog_revision=SeatCatalogReference(
            catalog_key=str(
                row["catalog_key"] if "catalog_key" in row else row["assigned_catalog_key"]
            ),
            revision=int(
                cast(
                    int,
                    row["catalog_revision"]
                    if "catalog_revision" in row
                    else row["assigned_catalog_revision"],
                )
            ),
            content_digest=(
                "sha256:"
                + str(
                    row["catalog_digest"]
                    if "catalog_digest" in row
                    else row["assigned_catalog_digest"]
                )
            ),
        ),
    )
