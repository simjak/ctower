"""Derived Request state and closure dependencies from append-only facts."""

from __future__ import annotations

import hashlib
import json
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.work._decision_brief import OPERATOR_DECISION_BLOCKER

__all__ = [
    "active_blocker_keys",
    "active_relations",
    "closure_outcome",
    "dependency_digest",
    "derived_state",
    "latest_triage",
]


def closure_outcome(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> str:
    triage = latest_triage(connection, tenant_id, request_id)
    if triage == "REJECTED":
        return "done"
    if triage == "DUPLICATE":
        return _duplicate_outcome(connection, tenant_id, request_id)
    if triage != "ACCEPTED" or _has_request_blocker(connection, tenant_id, request_id):
        return "open"
    tickets = active_relations(connection, tenant_id, request_id, purpose="required")
    if not tickets:
        return "open"
    return _required_tickets_outcome(connection, tenant_id, tickets)


def _duplicate_outcome(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    accepted_only: bool = False,
) -> str:
    row = connection.execute(
        """
        SELECT fact.canonical_request_id FROM request_triage_facts AS fact
        WHERE fact.tenant_id = %s AND fact.request_id = %s
          AND (NOT %s OR EXISTS (
              SELECT 1 FROM durability_acceptance_confirmations AS confirmation
              WHERE confirmation.tenant_id = fact.tenant_id
                AND confirmation.principal_id = fact.recorded_by
                AND confirmation.client_command_id = fact.command_id
          ))
        ORDER BY fact.sequence DESC LIMIT 1
        """,
        (tenant_id, request_id, accepted_only),
    ).fetchone()
    if row is None:
        raise RuntimeError("Duplicate Request has no canonical Request fact")
    canonical = cast(UUID, row["canonical_request_id"])
    return (
        "done"
        if derived_state(connection, tenant_id, canonical, accepted_only=accepted_only) == "DONE"
        else "open"
    )


def _required_tickets_outcome(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    tickets: tuple[UUID, ...],
) -> str:
    for ticket_id in tickets:
        row = connection.execute(
            """
            SELECT episode.state, episode.closed_at
            FROM tickets AS ticket
            JOIN lifecycle_episodes AS episode
              ON episode.tenant_id = ticket.tenant_id AND episode.ticket_id = ticket.ticket_id
             AND episode.episode_number = ticket.current_episode
            WHERE ticket.tenant_id = %s AND ticket.ticket_id = %s
            """,
            (tenant_id, ticket_id),
        ).fetchone()
        if row is None or str(row["state"]) != "closed":
            return "open"
        if _ticket_closure_invalid(connection, tenant_id, ticket_id, row["closed_at"]):
            return "open"
    return "done"


def _ticket_closure_invalid(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_id: UUID,
    closed_at: object,
) -> bool:
    blocked = connection.execute(
        """
        SELECT 1 FROM blocker_heads
        WHERE tenant_id = %s AND ticket_id = %s
          AND board_impact AND resolved_at IS NULL LIMIT 1
        """,
        (tenant_id, ticket_id),
    ).fetchone()
    invalidated = connection.execute(
        """
        SELECT 1 FROM proof_invalidations AS invalidation
        JOIN proof_bundles AS bundle
          ON bundle.tenant_id = invalidation.tenant_id
         AND bundle.proof_id = invalidation.proof_id
        WHERE bundle.tenant_id = %s AND bundle.ticket_id = %s
          AND invalidation.recorded_at > %s LIMIT 1
        """,
        (tenant_id, ticket_id, closed_at),
    ).fetchone()
    return blocked is not None or invalidated is not None


def derived_state(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    accepted_only: bool = False,
) -> str:
    request = (
        _accepted_request_version(connection, tenant_id, request_id)
        if accepted_only
        else connection.execute(
            "SELECT version FROM requests WHERE tenant_id = %s AND request_id = %s",
            (tenant_id, request_id),
        ).fetchone()
    )
    if request is None:
        return "NEW"
    if _has_valid_done_evaluation(
        connection, tenant_id, request_id, request, accepted_only=accepted_only
    ):
        return "DONE"
    if _has_request_blocker(
        connection, tenant_id, request_id, accepted_only=accepted_only
    ) or _has_ticket_blocker(connection, tenant_id, request_id, accepted_only=accepted_only):
        return "BLOCKED"
    triage = latest_triage(connection, tenant_id, request_id, accepted_only=accepted_only)
    if triage == "ACCEPTED" and _has_active_required_ticket(
        connection, tenant_id, request_id, accepted_only=accepted_only
    ):
        return "WIP"
    return "TRIAGED" if triage != "UNTRIAGED" else "NEW"


def _has_valid_done_evaluation(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    request: dict[str, object],
    *,
    accepted_only: bool = False,
) -> bool:
    closure = connection.execute(
        """
        SELECT evaluation.outcome, evaluation.request_version, evaluation.dependency_digest
        FROM request_closure_evaluations AS evaluation
        WHERE evaluation.tenant_id = %s AND evaluation.request_id = %s
          AND (NOT %s OR EXISTS (
              SELECT 1 FROM durability_acceptance_confirmations AS confirmation
              WHERE confirmation.tenant_id = evaluation.tenant_id
                AND confirmation.principal_id = evaluation.recorded_by
                AND confirmation.client_command_id = evaluation.command_id
          ))
        ORDER BY evaluation.request_version DESC LIMIT 1
        """,
        (tenant_id, request_id, accepted_only),
    ).fetchone()
    if closure is None or str(closure["outcome"]) != "done":
        return False
    if int(cast(int, closure["request_version"])) != int(cast(int, request["version"])):
        return False
    return bytes(cast(bytes, closure["dependency_digest"])) == dependency_digest(
        connection, tenant_id, request_id, accepted_only=accepted_only
    )


def dependency_digest(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    accepted_only: bool = False,
) -> bytes:
    relations = connection.execute(
        _DEPENDENCY_RELATIONS_SQL,
        _dependency_args(tenant_id, request_id, accepted_only=accepted_only),
    )
    blockers = active_blocker_keys(connection, tenant_id, request_id, accepted_only=accepted_only)
    triage = connection.execute(
        """
        SELECT fact.disposition, fact.canonical_request_id FROM request_triage_facts AS fact
        WHERE fact.tenant_id = %s AND fact.request_id = %s
          AND (NOT %s OR EXISTS (
              SELECT 1 FROM durability_acceptance_confirmations AS confirmation
              WHERE confirmation.tenant_id = fact.tenant_id
                AND confirmation.principal_id = fact.recorded_by
                AND confirmation.client_command_id = fact.command_id
          ))
        ORDER BY fact.sequence DESC LIMIT 1
        """,
        (tenant_id, request_id, accepted_only),
    ).fetchone()
    payload = {
        "blockers": list(blockers),
        "canonical": _canonical_dependency(
            connection, tenant_id, triage, accepted_only=accepted_only
        ),
        "relations": [_relation_dependency(row) for row in relations],
        "triage": None if triage is None else str(triage["disposition"]),
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).digest()


def _dependency_args(
    tenant_id: UUID, request_id: UUID, *, accepted_only: bool
) -> tuple[UUID, UUID, bool, UUID, UUID, UUID]:
    return tenant_id, request_id, accepted_only, tenant_id, tenant_id, tenant_id


def _canonical_dependency(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    triage: dict[str, object] | None,
    *,
    accepted_only: bool = False,
) -> dict[str, object] | None:
    if triage is None or triage["canonical_request_id"] is None:
        return None
    canonical_id = cast(UUID, triage["canonical_request_id"])
    return {
        "request_id": str(canonical_id),
        "state": derived_state(connection, tenant_id, canonical_id, accepted_only=accepted_only),
    }


def _relation_dependency(row: dict[str, object]) -> dict[str, object]:
    return {
        "blockers": int(cast(int, row["blockers"])),
        "invalidations": int(cast(int, row["invalidations"])),
        "proof_version": int(cast(int, row["proof_version"])),
        "purpose": str(row["purpose"]),
        "state": None if row["state"] is None else str(row["state"]),
        "ticket_id": str(row["ticket_id"]),
    }


_DEPENDENCY_RELATIONS_SQL = """
WITH latest AS (
    SELECT DISTINCT ON (fact.ticket_id) fact.ticket_id, fact.purpose, fact.active
    FROM request_ticket_relation_facts AS fact
    WHERE fact.tenant_id = %s AND fact.request_id = %s
      AND (NOT %s OR EXISTS (
          SELECT 1 FROM durability_acceptance_confirmations AS confirmation
          WHERE confirmation.tenant_id = fact.tenant_id
            AND confirmation.principal_id = fact.recorded_by
            AND confirmation.client_command_id = fact.command_id
      ))
    ORDER BY fact.ticket_id, fact.request_version DESC
)
SELECT latest.ticket_id, latest.purpose, episode.state,
       COALESCE((SELECT count(*) FROM blocker_heads AS blocker
                 WHERE blocker.tenant_id = %s AND blocker.ticket_id = latest.ticket_id
                   AND blocker.board_impact
                   AND blocker.resolved_at IS NULL), 0) AS blockers,
       COALESCE(bundle.version, 0) AS proof_version,
       COALESCE((SELECT count(*) FROM proof_invalidations AS invalidation
                 WHERE invalidation.tenant_id = %s
                   AND invalidation.proof_id = bundle.proof_id), 0) AS invalidations
FROM latest
LEFT JOIN tickets AS ticket
  ON ticket.tenant_id = %s AND ticket.ticket_id = latest.ticket_id
LEFT JOIN lifecycle_episodes AS episode
  ON episode.tenant_id = ticket.tenant_id AND episode.ticket_id = ticket.ticket_id
 AND episode.episode_number = ticket.current_episode
LEFT JOIN proof_bundles AS bundle
  ON bundle.tenant_id = ticket.tenant_id AND bundle.ticket_id = ticket.ticket_id
WHERE latest.active ORDER BY latest.ticket_id
"""


def active_relations(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    purpose: str,
    accepted_only: bool = False,
) -> tuple[UUID, ...]:
    rows = connection.execute(
        """
        SELECT ticket_id FROM (
            SELECT DISTINCT ON (fact.ticket_id) fact.ticket_id, fact.purpose, fact.active
            FROM request_ticket_relation_facts AS fact
            WHERE fact.tenant_id = %s AND fact.request_id = %s
              AND (NOT %s OR EXISTS (
                  SELECT 1 FROM durability_acceptance_confirmations AS confirmation
                  WHERE confirmation.tenant_id = fact.tenant_id
                    AND confirmation.principal_id = fact.recorded_by
                    AND confirmation.client_command_id = fact.command_id
              ))
            ORDER BY fact.ticket_id, fact.request_version DESC
        ) AS latest WHERE active AND purpose = %s ORDER BY ticket_id
        """,
        (tenant_id, request_id, accepted_only, purpose),
    ).fetchall()
    return tuple(cast(UUID, row["ticket_id"]) for row in rows)


def active_blocker_keys(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    accepted_only: bool = False,
) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT blocker_key, blocker_fact_id FROM (
            SELECT DISTINCT ON (fact.blocker_key)
                   fact.blocker_key, fact.blocker_fact_id, fact.active
            FROM request_blocker_facts AS fact
            WHERE fact.tenant_id = %s AND fact.request_id = %s
              AND (NOT %s OR EXISTS (
                  SELECT 1 FROM durability_acceptance_confirmations AS confirmation
                  WHERE confirmation.tenant_id = fact.tenant_id
                    AND confirmation.principal_id = fact.recorded_by
                    AND confirmation.client_command_id = fact.command_id
              ))
            ORDER BY fact.blocker_key, fact.request_version DESC
        ) AS latest WHERE active ORDER BY blocker_key
        """,
        (tenant_id, request_id, accepted_only),
    ).fetchall()
    decision_fact_id = next(
        (
            cast(UUID, row["blocker_fact_id"])
            for row in rows
            if str(row["blocker_key"]) == OPERATOR_DECISION_BLOCKER
        ),
        None,
    )
    if decision_fact_id is None or not _decision_answered(
        connection,
        tenant_id,
        decision_fact_id,
        accepted_only=accepted_only,
    ):
        return tuple(str(row["blocker_key"]) for row in rows)
    return tuple(
        str(row["blocker_key"])
        for row in rows
        if str(row["blocker_key"]) != OPERATOR_DECISION_BLOCKER
    )


def _decision_answered(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    decision_blocker_fact_id: UUID,
    *,
    accepted_only: bool,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM rulings AS ruling
            WHERE ruling.tenant_id = %s AND ruling.decision_blocker_fact_id = %s
              AND (NOT %s OR EXISTS (
                  SELECT 1 FROM durability_acceptance_confirmations AS confirmation
                  WHERE confirmation.tenant_id = ruling.tenant_id
                    AND confirmation.principal_id = ruling.recorded_by
                    AND confirmation.client_command_id = ruling.command_id
              ))
            LIMIT 1
            """,
            (tenant_id, decision_blocker_fact_id, accepted_only),
        ).fetchone()
        is not None
    )


def _has_request_blocker(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    accepted_only: bool = False,
) -> bool:
    return bool(active_blocker_keys(connection, tenant_id, request_id, accepted_only=accepted_only))


def _has_ticket_blocker(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    accepted_only: bool = False,
) -> bool:
    tickets = active_relations(
        connection, tenant_id, request_id, purpose="required", accepted_only=accepted_only
    )
    if not tickets:
        return False
    return (
        connection.execute(
            """
            SELECT 1 FROM blocker_heads
            WHERE tenant_id = %s AND ticket_id = ANY(%s)
              AND board_impact AND resolved_at IS NULL LIMIT 1
            """,
            (tenant_id, list(tickets)),
        ).fetchone()
        is not None
    )


def _has_active_required_ticket(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    accepted_only: bool = False,
) -> bool:
    tickets = active_relations(
        connection, tenant_id, request_id, purpose="required", accepted_only=accepted_only
    )
    if not tickets:
        return False
    return (
        connection.execute(
            """
            SELECT 1 FROM tickets AS ticket
            JOIN lifecycle_episodes AS episode
              ON episode.tenant_id = ticket.tenant_id AND episode.ticket_id = ticket.ticket_id
             AND episode.episode_number = ticket.current_episode
            WHERE ticket.tenant_id = %s AND ticket.ticket_id = ANY(%s)
              AND episode.state = 'active' LIMIT 1
            """,
            (tenant_id, list(tickets)),
        ).fetchone()
        is not None
    )


def latest_triage(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    accepted_only: bool = False,
) -> str:
    row = connection.execute(
        """
        SELECT fact.disposition FROM request_triage_facts AS fact
        WHERE fact.tenant_id = %s AND fact.request_id = %s
          AND (NOT %s OR EXISTS (
              SELECT 1 FROM durability_acceptance_confirmations AS confirmation
              WHERE confirmation.tenant_id = fact.tenant_id
                AND confirmation.principal_id = fact.recorded_by
                AND confirmation.client_command_id = fact.command_id
          ))
        ORDER BY fact.sequence DESC LIMIT 1
        """,
        (tenant_id, request_id, accepted_only),
    ).fetchone()
    if row is None:
        raise RuntimeError("Request has no triage fact")
    return str(row["disposition"])


def _accepted_request_version(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT max(event.sequence) AS version
        FROM events AS event
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = event.tenant_id
         AND confirmation.principal_id = event.actor_principal_id
         AND confirmation.client_command_id = event.client_command_id
        WHERE event.tenant_id = %s AND event.stream_id = %s
          AND event.kind = 'request.changed'
        HAVING max(event.sequence) IS NOT NULL
        """,
        (tenant_id, f"request:{request_id}"),
    ).fetchone()
