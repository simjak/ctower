"""Accepted-only Request list projection from PostgreSQL authority."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.transaction import project_scope_refusal
from ctower_kernel.work._decision_brief import decision_brief
from ctower_kernel.work._request_state_sql import derived_state
from ctower_kernel.work._request_types import (
    RequestList,
    RequestMergeProvenance,
    RequestResemblance,
    RequestRow,
)

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
                connection,
                actor.tenant_id,
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
), accepted_ruling AS (
    SELECT ruling.*, confirmation.acceptance_position
    FROM rulings AS ruling
    JOIN accepted AS request
      ON request.tenant_id = ruling.tenant_id
     AND request.project_key = ruling.project_key
     AND request.request_id = ruling.request_id
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = ruling.tenant_id
     AND confirmation.principal_id = ruling.recorded_by
     AND confirmation.client_command_id = ruling.command_id
), current_ruling AS (
    SELECT ruling.request_id, ruling.decision_blocker_fact_id,
           ruling.ruling_id, ruling.acceptance_position
    FROM accepted_ruling AS ruling
    WHERE NOT EXISTS (
        SELECT 1 FROM accepted_ruling AS successor
        WHERE successor.supersedes_ruling_id = ruling.ruling_id
    )
), blocker_latest AS (
    SELECT DISTINCT ON (fact.request_id, fact.blocker_key)
           fact.request_id, fact.blocker_fact_id, fact.blocker_key, fact.active,
           confirmation.acceptance_position
    FROM request_blocker_facts AS fact
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = fact.tenant_id
     AND confirmation.principal_id = fact.recorded_by
     AND confirmation.client_command_id = fact.command_id
    ORDER BY fact.request_id, fact.blocker_key, fact.request_version DESC
), blocker AS (
    SELECT latest.request_id,
           min(latest.blocker_key) FILTER (
               WHERE latest.active AND NOT (
                   latest.blocker_key = 'operator-decision-required'
                   AND current_ruling.ruling_id IS NOT NULL
               )
           ) AS blocker,
           max(latest.acceptance_position) AS acceptance_position
    FROM blocker_latest AS latest
    LEFT JOIN current_ruling
      ON current_ruling.decision_blocker_fact_id = latest.blocker_fact_id
    GROUP BY latest.request_id
), decision AS (
    SELECT latest.request_id, latest.blocker_fact_id
    FROM blocker_latest AS latest
    WHERE latest.blocker_key = 'operator-decision-required'
      AND latest.active
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
), resemblance AS (
    SELECT endpoint.request_id, max(endpoint.acceptance_position) AS acceptance_position
    FROM (
        SELECT link.source_request_id AS request_id, confirmation.acceptance_position
        FROM request_resemblance_links AS link
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = link.tenant_id
         AND confirmation.principal_id = link.linked_by
         AND confirmation.client_command_id = link.command_id
        UNION ALL
        SELECT link.candidate_request_id AS request_id, confirmation.acceptance_position
        FROM request_resemblance_links AS link
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = link.tenant_id
         AND confirmation.principal_id = link.linked_by
         AND confirmation.client_command_id = link.command_id
    ) AS endpoint
    GROUP BY endpoint.request_id
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
           COALESCE(closure.acceptance_position, 0),
           COALESCE(current_ruling.acceptance_position, 0),
           COALESCE(resemblance.acceptance_position, 0)
       ) AS acceptance_position,
       latest_owner.owner_id, principal.display_name AS owner,
       latest_priority.priority, latest_priority.is_default,
       latest_triage.disposition,
       COALESCE(relation.required_ticket_ids, ARRAY[]::uuid[]) AS required_ticket_ids,
       COALESCE(relation.optional_ticket_ids, ARRAY[]::uuid[]) AS optional_ticket_ids,
       COALESCE((
           SELECT count(*) FROM proof_bundles AS bundle
           WHERE bundle.tenant_id = accepted.tenant_id
             AND bundle.ticket_id = ANY(
                 COALESCE(relation.required_ticket_ids, ARRAY[]::uuid[])
             )
             AND NOT EXISTS (
                 SELECT 1 FROM proof_invalidations AS invalidation
                 WHERE invalidation.tenant_id = bundle.tenant_id
                   AND invalidation.proof_id = bundle.proof_id
             )
       ), 0) AS proof_coverage,
       blocker.blocker,
       decision.request_id IS NOT NULL AS decision_required,
       current_ruling.ruling_id,
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
LEFT JOIN decision ON decision.request_id = accepted.request_id
LEFT JOIN current_ruling
  ON current_ruling.decision_blocker_fact_id = decision.blocker_fact_id
LEFT JOIN closure ON closure.request_id = accepted.request_id
LEFT JOIN resemblance ON resemblance.request_id = accepted.request_id
LEFT JOIN request_owner_aliases AS owner_alias
  ON owner_alias.tenant_id = accepted.tenant_id
 AND owner_alias.request_id = accepted.request_id
ORDER BY accepted.request_number
"""


def _request_row(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    row: dict[str, object],
    *,
    state: str,
) -> RequestRow:
    ruling_id = cast(UUID | None, row["ruling_id"])
    triage = str(row["disposition"])
    brief = (
        decision_brief(
            content=str(row["content"]),
            reference=f"R{int(cast(int, row['request_number']))}",
            triage=triage,
            ruling_id=ruling_id,
        )
        if bool(row["decision_required"])
        else None
    )
    return RequestRow(
        request_id=cast(UUID, row["request_id"]),
        request_number=int(cast(int, row["request_number"])),
        project_key=str(row["project_key"]),
        content=str(row["content"]),
        content_sha256=_digest(row["content_digest"]),
        state=state,
        triage=triage,
        owner_id=cast(UUID, row["owner_id"]),
        owner=str(row["owner"]),
        priority=str(row["priority"]),
        priority_default=bool(row["is_default"]),
        created_at=cast(datetime, row["created_at"]),
        required_ticket_ids=tuple(cast(list[UUID], row["required_ticket_ids"])),
        optional_ticket_ids=tuple(cast(list[UUID], row["optional_ticket_ids"])),
        blocker=cast(str | None, row["blocker"]),
        proof_coverage=int(cast(int, row["proof_coverage"])),
        durability_state="accepted",
        freshness=int(cast(int, row["acceptance_position"])),
        source_kind=str(row["source_kind"]),
        source_ref=str(row["source_ref"]),
        original_owner_sha256=(
            None if row["source_owner_digest"] is None else _digest(row["source_owner_digest"])
        ),
        resemblances=_resemblances(connection, tenant_id, cast(UUID, row["request_id"])),
        merge_provenance=_merge_provenance(connection, tenant_id, cast(UUID, row["request_id"])),
        decision_brief=brief,
    )


def _resemblances(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> tuple[RequestResemblance, ...]:
    rows = connection.execute(
        """
        SELECT link.source_request_id, link.candidate_request_id, link.similarity,
               link.algorithm_ref, link.linked_at,
               other.request_id AS other_request_id,
               other.request_number AS other_request_number
        FROM request_resemblance_links AS link
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = link.tenant_id
         AND confirmation.principal_id = link.linked_by
         AND confirmation.client_command_id = link.command_id
        JOIN requests AS other
          ON other.tenant_id = link.tenant_id
         AND other.request_id = CASE
             WHEN link.source_request_id = %s THEN link.candidate_request_id
             ELSE link.source_request_id
         END
        WHERE link.tenant_id = %s
          AND %s IN (link.source_request_id, link.candidate_request_id)
        ORDER BY other.request_number
        """,
        (request_id, tenant_id, request_id),
    ).fetchall()
    return tuple(
        RequestResemblance(
            cast(UUID, item["other_request_id"]),
            int(cast(int, item["other_request_number"])),
            derived_state(
                connection,
                tenant_id,
                cast(UUID, item["other_request_id"]),
                accepted_only=True,
            ),
            round(float(cast(float, item["similarity"])) * 1_000_000),
            str(item["algorithm_ref"]),
            cast(datetime, item["linked_at"]),
        )
        for item in rows
    )


def _merge_provenance(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> RequestMergeProvenance | None:
    row = connection.execute(
        """
        SELECT fact.*
        FROM request_merge_facts AS fact
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = fact.tenant_id
         AND confirmation.principal_id = fact.merged_by
         AND confirmation.client_command_id = fact.command_id
        WHERE fact.tenant_id = %s AND fact.duplicate_request_id = %s
        """,
        (tenant_id, request_id),
    ).fetchone()
    if row is None:
        return None
    return RequestMergeProvenance(
        cast(UUID, row["duplicate_request_id"]),
        int(cast(int, row["duplicate_request_number"])),
        str(row["duplicate_content"]),
        cast(datetime, row["duplicate_created_at"]),
        cast(UUID, row["canonical_request_id"]),
        int(cast(int, row["canonical_request_number"])),
        str(row["canonical_content"]),
        cast(datetime, row["canonical_created_at"]),
        str(row["trigger_kind"]),
        str(row["merge_wording"]),
        cast(UUID, row["merged_by"]),
        cast(datetime, row["merged_at"]),
    )


def _digest(value: object) -> str:
    return f"sha256:{bytes(cast(bytes, value)).hex()}"
