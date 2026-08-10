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
        connection.execute("SET ROLE ctower_svc")
        requested = _requested_projects(connection, actor.tenant_id, project_key)
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
                state=derived_state(connection, actor.tenant_id, cast(UUID, row["request_id"])),
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
        return (project_key,)
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
    SELECT request.*, confirmation.acceptance_position
    FROM requests AS request
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = request.tenant_id
     AND confirmation.principal_id = request.submitted_by
     AND confirmation.client_command_id = request.capture_command_id
    WHERE request.tenant_id = %s AND request.project_key = ANY(%s)
), latest_owner AS (
    SELECT DISTINCT ON (request_id) request_id, owner_id
    FROM request_owner_facts ORDER BY request_id, sequence DESC
), latest_priority AS (
    SELECT DISTINCT ON (request_id) request_id, priority, is_default
    FROM request_priority_facts ORDER BY request_id, sequence DESC
), latest_triage AS (
    SELECT DISTINCT ON (request_id) request_id, disposition
    FROM request_triage_facts ORDER BY request_id, sequence DESC
), relation AS (
    SELECT DISTINCT ON (request_id, ticket_id) request_id, ticket_id, purpose, active
    FROM request_ticket_relation_facts
    ORDER BY request_id, ticket_id, recorded_at DESC, relation_fact_id DESC
), blocker AS (
    SELECT DISTINCT ON (request_id, blocker_key) request_id, blocker_key, active
    FROM request_blocker_facts
    ORDER BY request_id, blocker_key, recorded_at DESC, blocker_fact_id DESC
), closure AS (
    SELECT DISTINCT ON (request_id) request_id, outcome, dependency_digest, request_version
    FROM request_closure_evaluations
    ORDER BY request_id, recorded_at DESC, evaluation_id DESC
)
SELECT accepted.request_id, accepted.request_number, accepted.project_key,
       accepted.content, accepted.source_kind, accepted.created_at,
       accepted.version, accepted.acceptance_position,
       latest_owner.owner_id, principal.display_name AS owner,
       latest_priority.priority, latest_priority.is_default,
       latest_triage.disposition,
       COALESCE(array_agg(relation.ticket_id ORDER BY relation.ticket_id)
           FILTER (WHERE relation.active AND relation.purpose = 'required'), ARRAY[]::uuid[])
           AS required_ticket_ids,
       COALESCE(array_agg(relation.ticket_id ORDER BY relation.ticket_id)
           FILTER (WHERE relation.active AND relation.purpose = 'optional'), ARRAY[]::uuid[])
           AS optional_ticket_ids,
       min(blocker.blocker_key) FILTER (WHERE blocker.active) AS blocker,
       closure.outcome AS closure_outcome
FROM accepted
JOIN latest_owner ON latest_owner.request_id = accepted.request_id
JOIN principals AS principal
  ON principal.tenant_id = accepted.tenant_id AND principal.principal_id = latest_owner.owner_id
JOIN latest_priority ON latest_priority.request_id = accepted.request_id
JOIN latest_triage ON latest_triage.request_id = accepted.request_id
LEFT JOIN relation ON relation.request_id = accepted.request_id
LEFT JOIN blocker ON blocker.request_id = accepted.request_id
LEFT JOIN closure ON closure.request_id = accepted.request_id
GROUP BY accepted.request_id, accepted.request_number, accepted.project_key,
         accepted.content, accepted.source_kind, accepted.created_at, accepted.version,
         accepted.acceptance_position, latest_owner.owner_id, principal.display_name,
         latest_priority.priority, latest_priority.is_default, latest_triage.disposition,
         closure.outcome
ORDER BY accepted.request_number
"""


def _request_row(row: dict[str, object], *, state: str) -> RequestRow:
    return RequestRow(
        request_id=cast(UUID, row["request_id"]),
        request_number=int(cast(int, row["request_number"])),
        project_key=str(row["project_key"]),
        content=str(row["content"]),
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
    )
