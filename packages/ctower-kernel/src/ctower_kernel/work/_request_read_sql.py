"""Accepted-only Request list projection from PostgreSQL authority."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.transaction import project_scope_refusal
from ctower_kernel.work._request_state_sql import derived_state
from ctower_kernel.work._request_types import RequestList, RequestRow

__all__ = ["list_requests"]


def list_requests(
    dsn: str,
    actor: Actor,
    *,
    project_key: str | None,
    now: datetime,
) -> RequestList | RecordProblem:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("SET ROLE ctower_svc")
        requested = _requested_projects(connection, actor.tenant_id, project_key)
        if project_key is not None and not requested:
            return RecordProblem(
                code="request-project-unavailable",
                detail="The requested Project is not present in the active tenant hierarchy.",
                status=404,
                title="Request Project unavailable",
            )
        scope = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=requested,
            operator_only=project_key is None and actor.kind is not PrincipalKind.OPERATOR,
        )
        if scope is not None:
            return scope
        watermark_row = connection.execute(
            "SELECT last_position FROM record_position_ledger WHERE singleton"
        ).fetchone()
        watermark = int(cast(int, watermark_row["last_position"])) if watermark_row else 0
        rows = connection.execute(_LIST_SQL, (actor.tenant_id, list(requested))).fetchall()
        projected = tuple(
            _request_row(
                row,
                state=derived_state(
                    connection,
                    actor.tenant_id,
                    cast(UUID, row["request_id"]),
                    accepted_only=True,
                ),
            )
            for row in rows
        )
    return RequestList(projected, requested, requested, (), watermark, now)


def _requested_projects(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str | None,
) -> tuple[str, ...]:
    if project_key is not None:
        row = connection.execute(
            """
            SELECT 1 FROM (
                SELECT project_key FROM project_delivery_checkpoint_definitions
                WHERE tenant_id = %s
                UNION
                SELECT project_key FROM project_seats WHERE tenant_id = %s
            ) AS project WHERE project_key = %s LIMIT 1
            """,
            (tenant_id, tenant_id, project_key),
        ).fetchone()
        return (project_key,) if row is not None else ()
    rows = connection.execute(
        """
        SELECT project_key FROM (
            SELECT project_key FROM project_delivery_checkpoint_definitions WHERE tenant_id = %s
            UNION
            SELECT project_key FROM project_seats WHERE tenant_id = %s
        ) AS project ORDER BY project_key
        """,
        (tenant_id, tenant_id),
    ).fetchall()
    return tuple(str(row["project_key"]) for row in rows)


_LIST_SQL = """
WITH accepted AS (
    SELECT request.*, confirmation.acceptance_position AS capture_position
    FROM requests AS request
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = request.tenant_id
     AND confirmation.principal_id = request.submitted_by
     AND confirmation.client_command_id = request.capture_command_id
    WHERE request.tenant_id = %s AND request.project_key = ANY(%s)
), accepted_event AS (
    SELECT event.aggregate_id AS request_id, max(event.sequence) AS version,
           max(confirmation.acceptance_position) AS acceptance_position
    FROM events AS event
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = event.tenant_id
     AND confirmation.principal_id = event.actor_principal_id
     AND confirmation.client_command_id = event.client_command_id
    WHERE event.kind = 'request.changed'
    GROUP BY event.aggregate_id
), latest_owner AS (
    SELECT DISTINCT ON (fact.request_id) fact.request_id, fact.owner_id,
           confirmation.acceptance_position
    FROM request_owner_facts AS fact
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = fact.tenant_id
     AND confirmation.principal_id = fact.recorded_by
     AND confirmation.client_command_id = fact.command_id
    ORDER BY fact.request_id, fact.sequence DESC
), latest_priority AS (
    SELECT DISTINCT ON (fact.request_id) fact.request_id, fact.priority, fact.is_default,
           confirmation.acceptance_position
    FROM request_priority_facts AS fact
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = fact.tenant_id
     AND confirmation.principal_id = fact.recorded_by
     AND confirmation.client_command_id = fact.command_id
    ORDER BY fact.request_id, fact.sequence DESC
), latest_triage AS (
    SELECT DISTINCT ON (fact.request_id) fact.request_id, fact.disposition,
           confirmation.acceptance_position
    FROM request_triage_facts AS fact
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = fact.tenant_id
     AND confirmation.principal_id = fact.recorded_by
     AND confirmation.client_command_id = fact.command_id
    ORDER BY fact.request_id, fact.sequence DESC
), relation_latest AS (
    SELECT DISTINCT ON (fact.request_id, fact.ticket_id)
           fact.request_id, fact.ticket_id, fact.purpose, fact.active,
           confirmation.acceptance_position
    FROM request_ticket_relation_facts AS fact
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = fact.tenant_id
     AND confirmation.principal_id = fact.recorded_by
     AND confirmation.client_command_id = fact.command_id
    ORDER BY fact.request_id, fact.ticket_id, fact.request_version DESC
), relation AS (
    SELECT request_id,
           COALESCE(array_agg(ticket_id ORDER BY ticket_id)
               FILTER (WHERE active AND purpose = 'required'), ARRAY[]::uuid[])
               AS required_ticket_ids,
           COALESCE(array_agg(ticket_id ORDER BY ticket_id)
               FILTER (WHERE active AND purpose = 'optional'), ARRAY[]::uuid[])
               AS optional_ticket_ids,
           max(acceptance_position) AS acceptance_position
    FROM relation_latest GROUP BY request_id
), blocker_latest AS (
    SELECT DISTINCT ON (fact.request_id, fact.blocker_key)
           fact.request_id, fact.blocker_key, fact.active,
           confirmation.acceptance_position
    FROM request_blocker_facts AS fact
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = fact.tenant_id
     AND confirmation.principal_id = fact.recorded_by
     AND confirmation.client_command_id = fact.command_id
    ORDER BY fact.request_id, fact.blocker_key, fact.request_version DESC
), blocker AS (
    SELECT request_id, min(blocker_key) FILTER (WHERE active) AS blocker,
           max(acceptance_position) AS acceptance_position
    FROM blocker_latest GROUP BY request_id
), closure AS (
    SELECT DISTINCT ON (evaluation.request_id)
           evaluation.request_id, evaluation.outcome, evaluation.dependency_digest,
           evaluation.request_version, confirmation.acceptance_position
    FROM request_closure_evaluations AS evaluation
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = evaluation.tenant_id
     AND confirmation.principal_id = evaluation.recorded_by
     AND confirmation.client_command_id = evaluation.command_id
    ORDER BY evaluation.request_id, evaluation.request_version DESC
)
SELECT accepted.request_id, accepted.request_number, accepted.project_key,
       accepted.content, accepted.content_digest, accepted.source_kind,
       accepted.source_ref, accepted.created_at,
       accepted_event.version,
       GREATEST(
           accepted.capture_position, accepted_event.acceptance_position,
           latest_owner.acceptance_position, latest_priority.acceptance_position,
           latest_triage.acceptance_position,
           COALESCE(relation.acceptance_position, 0),
           COALESCE(blocker.acceptance_position, 0),
           COALESCE(closure.acceptance_position, 0)
       ) AS acceptance_position,
       latest_owner.owner_id, principal.display_name AS owner,
       latest_priority.priority, latest_priority.is_default,
       latest_triage.disposition,
       COALESCE(relation.required_ticket_ids, ARRAY[]::uuid[]) AS required_ticket_ids,
       COALESCE(relation.optional_ticket_ids, ARRAY[]::uuid[]) AS optional_ticket_ids,
       blocker.blocker,
       closure.outcome AS closure_outcome,
       owner_alias.source_owner_digest
FROM accepted
JOIN accepted_event ON accepted_event.request_id = accepted.request_id
JOIN latest_owner ON latest_owner.request_id = accepted.request_id
JOIN principals AS principal
  ON principal.tenant_id = accepted.tenant_id AND principal.principal_id = latest_owner.owner_id
JOIN latest_priority ON latest_priority.request_id = accepted.request_id
JOIN latest_triage ON latest_triage.request_id = accepted.request_id
LEFT JOIN relation ON relation.request_id = accepted.request_id
LEFT JOIN blocker ON blocker.request_id = accepted.request_id
LEFT JOIN closure ON closure.request_id = accepted.request_id
LEFT JOIN request_owner_aliases AS owner_alias
  ON owner_alias.tenant_id = accepted.tenant_id
 AND owner_alias.request_id = accepted.request_id
ORDER BY accepted.request_number
"""


def _request_row(row: dict[str, object], *, state: str) -> RequestRow:
    return RequestRow(
        request_id=cast(UUID, row["request_id"]),
        request_number=int(cast(int, row["request_number"])),
        project_key=str(row["project_key"]),
        content=str(row["content"]),
        content_sha256=_digest(row["content_digest"]),
        state=state,
        triage=str(row["disposition"]),
        owner_id=cast(UUID, row["owner_id"]),
        owner=str(row["owner"]),
        priority=str(row["priority"]),
        priority_default=bool(row["is_default"]),
        created_at=cast(datetime, row["created_at"]),
        required_ticket_ids=tuple(cast(list[UUID], row["required_ticket_ids"])),
        optional_ticket_ids=tuple(cast(list[UUID], row["optional_ticket_ids"])),
        blocker=cast(str | None, row["blocker"]),
        proof_coverage=None,
        durability_state="accepted",
        freshness=int(cast(int, row["acceptance_position"])),
        source_kind=str(row["source_kind"]),
        source_ref=str(row["source_ref"]),
        original_owner_sha256=(
            None if row["source_owner_digest"] is None else _digest(row["source_owner_digest"])
        ),
    )


def _digest(value: object) -> str:
    return f"sha256:{bytes(cast(bytes, value)).hex()}"
