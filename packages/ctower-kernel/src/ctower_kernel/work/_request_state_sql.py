"""Derived Request state and closure dependencies from append-only facts."""

from __future__ import annotations

import hashlib
import json
from typing import cast
from uuid import UUID

import psycopg

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
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> str:
    row = connection.execute(
        """
        SELECT canonical_request_id FROM request_triage_facts
        WHERE tenant_id = %s AND request_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (tenant_id, request_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Duplicate Request has no canonical Request fact")
    canonical = cast(UUID, row["canonical_request_id"])
    return "done" if derived_state(connection, tenant_id, canonical) == "DONE" else "open"


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
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> str:
    request = connection.execute(
        "SELECT version FROM requests WHERE tenant_id = %s AND request_id = %s",
        (tenant_id, request_id),
    ).fetchone()
    if request is None:
        return "NEW"
    if _has_valid_done_evaluation(connection, tenant_id, request_id, request):
        return "DONE"
    if _has_request_blocker(connection, tenant_id, request_id) or _has_ticket_blocker(
        connection, tenant_id, request_id
    ):
        return "BLOCKED"
    triage = latest_triage(connection, tenant_id, request_id)
    if triage == "ACCEPTED" and _has_active_required_ticket(connection, tenant_id, request_id):
        return "WIP"
    return "TRIAGED" if triage != "UNTRIAGED" else "NEW"


def _has_valid_done_evaluation(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    request: dict[str, object],
) -> bool:
    closure = connection.execute(
        """
        SELECT outcome, request_version, dependency_digest
        FROM request_closure_evaluations
        WHERE tenant_id = %s AND request_id = %s
        ORDER BY recorded_at DESC, evaluation_id DESC LIMIT 1
        """,
        (tenant_id, request_id),
    ).fetchone()
    if closure is None or str(closure["outcome"]) != "done":
        return False
    if int(cast(int, closure["request_version"])) != int(cast(int, request["version"])):
        return False
    return bytes(cast(bytes, closure["dependency_digest"])) == dependency_digest(
        connection, tenant_id, request_id
    )


def dependency_digest(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> bytes:
    relations = connection.execute(
        _DEPENDENCY_RELATIONS_SQL, _dependency_args(tenant_id, request_id)
    )
    blockers = connection.execute(_DEPENDENCY_BLOCKERS_SQL, (tenant_id, request_id)).fetchall()
    triage = connection.execute(
        """
        SELECT disposition, canonical_request_id FROM request_triage_facts
        WHERE tenant_id = %s AND request_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (tenant_id, request_id),
    ).fetchone()
    payload = {
        "blockers": [str(row["blocker_key"]) for row in blockers],
        "canonical": _canonical_dependency(connection, tenant_id, triage),
        "relations": [_relation_dependency(row) for row in relations],
        "triage": None if triage is None else str(triage["disposition"]),
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).digest()


def _dependency_args(tenant_id: UUID, request_id: UUID) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    return tenant_id, request_id, tenant_id, tenant_id, tenant_id


def _canonical_dependency(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    triage: dict[str, object] | None,
) -> dict[str, object] | None:
    if triage is None or triage["canonical_request_id"] is None:
        return None
    canonical_id = cast(UUID, triage["canonical_request_id"])
    return {
        "request_id": str(canonical_id),
        "state": derived_state(connection, tenant_id, canonical_id),
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
    SELECT DISTINCT ON (ticket_id) ticket_id, purpose, active
    FROM request_ticket_relation_facts
    WHERE tenant_id = %s AND request_id = %s
    ORDER BY ticket_id, recorded_at DESC, relation_fact_id DESC
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

_DEPENDENCY_BLOCKERS_SQL = """
SELECT blocker_key, active FROM (
    SELECT DISTINCT ON (blocker_key) blocker_key, active
    FROM request_blocker_facts WHERE tenant_id = %s AND request_id = %s
    ORDER BY blocker_key, recorded_at DESC, blocker_fact_id DESC
) AS latest WHERE active ORDER BY blocker_key
"""


def active_relations(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    *,
    purpose: str,
) -> tuple[UUID, ...]:
    rows = connection.execute(
        """
        SELECT ticket_id FROM (
            SELECT DISTINCT ON (ticket_id) ticket_id, purpose, active
            FROM request_ticket_relation_facts
            WHERE tenant_id = %s AND request_id = %s
            ORDER BY ticket_id, recorded_at DESC, relation_fact_id DESC
        ) AS latest WHERE active AND purpose = %s ORDER BY ticket_id
        """,
        (tenant_id, request_id, purpose),
    ).fetchall()
    return tuple(cast(UUID, row["ticket_id"]) for row in rows)


def active_blocker_keys(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT blocker_key FROM (
            SELECT DISTINCT ON (blocker_key) blocker_key, active
            FROM request_blocker_facts WHERE tenant_id = %s AND request_id = %s
            ORDER BY blocker_key, recorded_at DESC, blocker_fact_id DESC
        ) AS latest WHERE active ORDER BY blocker_key
        """,
        (tenant_id, request_id),
    ).fetchall()
    return tuple(str(row["blocker_key"]) for row in rows)


def _has_request_blocker(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> bool:
    return bool(active_blocker_keys(connection, tenant_id, request_id))


def _has_ticket_blocker(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> bool:
    tickets = active_relations(connection, tenant_id, request_id, purpose="required")
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
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> bool:
    tickets = active_relations(connection, tenant_id, request_id, purpose="required")
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
              AND episode.state IN ('active', 'waiting') LIMIT 1
            """,
            (tenant_id, list(tickets)),
        ).fetchone()
        is not None
    )


def latest_triage(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> str:
    row = connection.execute(
        """
        SELECT disposition FROM request_triage_facts
        WHERE tenant_id = %s AND request_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (tenant_id, request_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Request has no triage fact")
    return str(row["disposition"])
