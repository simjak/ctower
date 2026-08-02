"""Server-measured, run-scoped pass-two target snapshots."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import psycopg
import rfc8785
from psycopg.types.json import Jsonb

from ctower_kernel.migration import _checkpoint_expectation_sql, _target_anomaly

__all__ = [
    "TargetSnapshot",
    "capture",
    "evidence",
    "graph",
    "persist",
    "ready_for_pass_two",
    "zero_delta",
]
_PROJECT_DELIVERY_VOLATILE = frozenset(
    {
        "freshness_due_at",
        "projection_watermark",
        "rebuild_generation",
        "reconciled_at",
        "semantic_digest",
        "source_watermark",
    }
)


@dataclass(frozen=True, slots=True)
class TargetSnapshot:
    """One exhaustive target identity graph at a stable transaction boundary."""

    body: dict[str, object]
    digest: bytes
    domain_fact_count: int
    event_count: int
    outbox_count: int
    record_position: int
    project_delivery_digest: bytes
    project_delivery_current: bool


def capture(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
) -> TargetSnapshot:
    scope = connection.execute(
        """
        SELECT run.tenant_id, binding.principal_id
        FROM migration_import_runs AS run
        JOIN migration_importer_bindings AS binding ON binding.run_id = run.run_id
        WHERE run.run_id = %s
        """,
        (run_id,),
    ).fetchone()
    if scope is None:
        raise RuntimeError("pass-two scope is unavailable")
    tenant_id = cast(UUID, scope["tenant_id"])
    operation_results = _operation_results(connection, run_id)
    ticket_bindings = _ticket_bindings(connection, run_id, tenant_id)
    ticket_ids = [row["ticket_id"] for row in ticket_bindings]
    graph = _migration_target_rows(
        connection,
        run_id,
        tenant_id,
        operation_results,
        ticket_bindings,
    )
    graph.update(_ticket_fact_rows(connection, run_id, tenant_id, ticket_ids))
    graph.update(_checkpoint_rows(connection, tenant_id))
    graph["signed_checkpoint_keys"] = _checkpoint_expectation_sql.signed_keys(
        connection,
        run_id,
    )
    event_ids = _event_ids(connection, run_id, operation_results)
    events = _scoped_events(connection, tenant_id, event_ids)
    outbox = _scoped_outbox(connection, tenant_id, event_ids)
    graph["event_ids"] = events
    graph["outbox_rows"] = outbox
    return _snapshot(graph, events, outbox)


def _operation_results(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
) -> list[dict[str, object]]:
    return _rows(
        connection,
        """
        SELECT command_id, namespace, immutable_source_id, source_version_or_digest,
            operation_kind, planned_target_ref, target_id, event_ids, record_position,
            request_digest
        FROM migration_import_operation_results
        WHERE run_id = %s
        ORDER BY namespace, immutable_source_id, source_version_or_digest,
            operation_kind, planned_target_ref, command_id
        """,
        (run_id,),
    )


def _ticket_bindings(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    tenant_id: UUID,
) -> list[dict[str, object]]:
    return _rows(
        connection,
        """
        SELECT binding.ticket_id, binding.source_namespace, binding.immutable_source_id,
            ticket.title, ticket.priority, ticket.custodian_principal_id, ticket.version
        FROM ticket_project_bindings AS binding
        JOIN tickets AS ticket
          ON ticket.ticket_id = binding.ticket_id
         AND ticket.tenant_id = binding.tenant_id
        WHERE binding.run_id = %s AND binding.tenant_id = %s
        ORDER BY binding.source_namespace, binding.immutable_source_id, binding.ticket_id
        """,
        (run_id, tenant_id),
    )


def _migration_target_rows(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    tenant_id: UUID,
    operation_results: list[dict[str, object]],
    ticket_bindings: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema": "ctower.migration-pass-two-target-snapshot/v1",
        "run_id": str(run_id),
        "tenant_id": str(tenant_id),
        "planned_operations": _rows(
            connection,
            """
            SELECT batch.batch_index, item.ordinality AS operation_ordinal,
                item.operation -> 'identity' AS identity,
                item.operation ->> 'operation' AS operation,
                item.operation AS operation_body
            FROM migration_import_plan_batches AS batch
            CROSS JOIN LATERAL jsonb_array_elements(batch.batch_body -> 'operations')
                WITH ORDINALITY AS item(operation, ordinality)
            WHERE batch.run_id = %s
            ORDER BY batch.batch_index, item.ordinality
            """,
            (run_id,),
        ),
        "operation_results": operation_results,
        "stable_aliases": _rows(
            connection,
            """
            SELECT stable_item_id, target_ticket_id, mapping_digest
            FROM migration_stable_alias_bindings
            WHERE run_id = %s ORDER BY stable_item_id
            """,
            (run_id,),
        ),
        "ticket_bindings": ticket_bindings,
        "alias_revisions": _rows(
            connection,
            """
            SELECT alias_id, revision, namespace, immutable_source_id,
                target_ticket_id, disposition, semantic_digest, supersedes_revision
            FROM migration_alias_revisions WHERE run_id = %s
            ORDER BY namespace, immutable_source_id, alias_id, revision
            """,
            (run_id,),
        ),
        "source_link_revisions": _rows(
            connection,
            """
            SELECT link_id, revision, namespace, immutable_source_id, link_class,
                target_kind, target_id, reason_code, semantic_digest, supersedes_revision
            FROM migration_source_link_revisions WHERE run_id = %s
            ORDER BY namespace, immutable_source_id, link_id, revision
            """,
            (run_id,),
        ),
    }


def _ticket_fact_rows(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    tenant_id: UUID,
    ticket_ids: list[object],
) -> dict[str, object]:
    return {
        "lifecycle_episodes": _ticket_rows(
            connection,
            """
            SELECT ticket_id, episode_number, state, opened_at, closed_at
            FROM lifecycle_episodes
            WHERE tenant_id = %s AND ticket_id = ANY(%s)
            ORDER BY ticket_id, episode_number
            """,
            tenant_id,
            ticket_ids,
        ),
        "priority_facts": _ticket_rows(
            connection,
            """
            SELECT ticket_id, fact_sequence, priority, changed_by, reason,
                client_command_id, recorded_at
            FROM priority_facts
            WHERE tenant_id = %s AND ticket_id = ANY(%s)
            ORDER BY ticket_id, fact_sequence
            """,
            tenant_id,
            ticket_ids,
        ),
        "custody_intervals": _ticket_rows(
            connection,
            """
            SELECT ticket_id, interval_sequence, assignment_kind, principal_id,
                assigned_at, released_at, changed_by, reason, client_command_id,
                episode_number
            FROM assignment_intervals
            WHERE tenant_id = %s AND ticket_id = ANY(%s)
            ORDER BY ticket_id, assignment_kind, interval_sequence
            """,
            tenant_id,
            ticket_ids,
        ),
        "relations": _ticket_rows(
            connection,
            """
            SELECT relation.relation_id, relation.source_ticket_id,
                relation.target_ticket_id, relation.relation_kind,
                relation.client_command_id, validity.revision, validity.active,
                validity.replacement_relation_id, validity.semantic_digest
            FROM ticket_relations AS relation
            JOIN migration_relation_validity_facts AS validity
              ON validity.relation_id = relation.relation_id
            WHERE relation.tenant_id = %s
              AND validity.run_id = %s
              AND relation.source_ticket_id = ANY(%s)
              AND relation.target_ticket_id = ANY(%s)
            ORDER BY relation.relation_id, validity.revision
            """,
            tenant_id,
            ticket_ids,
            extra=(run_id, ticket_ids),
        ),
    }


def _checkpoint_rows(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> dict[str, object]:
    return {
        "checkpoint_definitions": _rows(
            connection,
            """
            SELECT checkpoint_definition_id, company_key, project_key, checkpoint_key,
                definition_revision, catalog_revision, catalog_digest, checkpoint_label,
                outcome, accountable_owner, ordered_position, applicable_states
            FROM (
                SELECT DISTINCT ON (checkpoint_key) *
                FROM project_delivery_checkpoint_definitions
                WHERE tenant_id = %s AND project_key = 'ctower'
                ORDER BY checkpoint_key, definition_revision DESC
            ) AS definition
            ORDER BY checkpoint_key, definition_revision
            """,
            (tenant_id,),
        ),
        "checkpoint_criteria": _rows(
            connection,
            """
            SELECT criterion.checkpoint_definition_id, criterion.ordinal,
                criterion.criterion_key, criterion.description,
                criterion.proof_ticket_id, criterion.proof_criterion_key,
                criterion.source_ids
            FROM project_delivery_exit_criteria AS criterion
            JOIN (
                SELECT DISTINCT ON (checkpoint_key) *
                FROM project_delivery_checkpoint_definitions
                WHERE tenant_id = %s AND project_key = 'ctower'
                ORDER BY checkpoint_key, definition_revision DESC
            ) AS definition
              ON definition.checkpoint_definition_id = criterion.checkpoint_definition_id
             AND definition.tenant_id = criterion.tenant_id
            WHERE criterion.tenant_id = %s
            ORDER BY definition.checkpoint_key, definition.definition_revision,
                criterion.ordinal
            """,
            (tenant_id, tenant_id),
        ),
        "project_delivery_rows": _rows(
            connection,
            """
            SELECT project_key, checkpoint_key, row_payload, source_watermark,
                projection_watermark
            FROM project_delivery_projection_rows
            WHERE tenant_id = %s AND project_key = 'ctower'
            ORDER BY checkpoint_key
            """,
            (tenant_id,),
        ),
    }


def _snapshot(
    graph: dict[str, object],
    events: list[dict[str, object]],
    outbox: list[dict[str, object]],
) -> TargetSnapshot:
    graph = cast(dict[str, object], _normal(graph))
    body_bytes = rfc8785.dumps(cast(Any, graph))
    project_bytes = rfc8785.dumps(cast(Any, _project_delivery_values(graph)))
    domain_count = sum(
        len(cast(list[object], graph[key]))
        for key in (
            "operation_results",
            "stable_aliases",
            "ticket_bindings",
            "lifecycle_episodes",
            "priority_facts",
            "custody_intervals",
            "relations",
            "alias_revisions",
            "source_link_revisions",
            "checkpoint_definitions",
            "checkpoint_criteria",
            "project_delivery_rows",
        )
    )
    positions = [
        int(cast(int, cast(dict[str, object], row)["record_position"]))
        for row in cast(list[object], events)
    ]
    return TargetSnapshot(
        graph,
        hashlib.sha256(body_bytes).digest(),
        domain_count,
        len(events),
        len(outbox),
        max(positions, default=0),
        hashlib.sha256(project_bytes).digest(),
        _project_delivery_current(graph, positions),
    )


def _project_delivery_current(
    graph: dict[str, object],
    positions: list[int],
) -> bool:
    definitions = cast(list[dict[str, object]], graph["checkpoint_definitions"])
    criteria = cast(list[dict[str, object]], graph["checkpoint_criteria"])
    delivery_rows = cast(list[dict[str, object]], graph["project_delivery_rows"])
    stable_alias_ids = [
        str(row["stable_item_id"]) for row in cast(list[dict[str, object]], graph["stable_aliases"])
    ]
    definition_keys = [str(row["checkpoint_key"]) for row in definitions]
    delivery_keys = [str(row["checkpoint_key"]) for row in delivery_rows]
    definition_ids = [str(row["checkpoint_definition_id"]) for row in definitions]
    criteria_definition_ids = {str(row["checkpoint_definition_id"]) for row in criteria}
    return (
        _unique_identities(stable_alias_ids)
        and _same_identity_set(definition_keys, delivery_keys)
        and _unique_identities(definition_ids)
        and criteria_definition_ids == set(definition_ids)
        and all(str(row["accountable_owner"]).strip() for row in definitions)
        and all(
            int(cast(int, row["source_watermark"])) >= max(positions, default=0)
            and int(cast(int, row["projection_watermark"])) >= max(positions, default=0)
            for row in delivery_rows
        )
    )


def _same_identity_set(expected: Iterable[str], actual: Iterable[str]) -> bool:
    expected_values = tuple(expected)
    actual_values = tuple(actual)
    return (
        _unique_identities(expected_values)
        and _unique_identities(actual_values)
        and set(actual_values) == set(expected_values)
    )


def _unique_identities(values: Iterable[str]) -> bool:
    identities = tuple(values)
    return len(identities) == len(set(identities))


def persist(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    boundary: str,
    snapshot: TargetSnapshot,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_import_pass_two_snapshots (
            run_id, boundary, snapshot_digest, snapshot_body, domain_fact_count,
            event_count, outbox_count, record_position, project_delivery_digest,
            recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            boundary,
            snapshot.digest,
            Jsonb(snapshot.body),
            snapshot.domain_fact_count,
            snapshot.event_count,
            snapshot.outbox_count,
            snapshot.record_position,
            snapshot.project_delivery_digest,
            now,
        ),
    )


def zero_delta(before: TargetSnapshot, after: TargetSnapshot) -> bool:
    """Require exact identity-set equality, not merely equal aggregate counts."""

    return before.digest == after.digest and before.body == after.body


def ready_for_pass_two(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    snapshot: TargetSnapshot,
) -> bool:
    """Require the complete reviewed alias/Catalog projection at the run watermark."""

    measured = graph(snapshot.body)
    return (
        snapshot.project_delivery_current
        and _checkpoint_expectation_sql.matches(connection, run_id, snapshot.body)
        and not any(
            cast(list[object], measured[key])
            for key in ("unexpected", "forbidden", "unresolved", "cycles")
        )
    )


def evidence(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    rows = connection.execute(
        """
        SELECT boundary, snapshot_digest, snapshot_body, domain_fact_count,
            event_count, outbox_count, record_position, project_delivery_digest
        FROM migration_import_pass_two_snapshots
        WHERE run_id = %s ORDER BY boundary
        """,
        (run_id,),
    ).fetchall()
    by_boundary = {str(row["boundary"]): row for row in rows}
    start, end = by_boundary.get("start"), by_boundary.get("end")
    if start is None or end is None:
        return None, None
    measurement = {
        "start_snapshot_digest": _digest_text(start["snapshot_digest"]),
        "end_snapshot_digest": _digest_text(end["snapshot_digest"]),
        "start_domain_facts": int(cast(int, start["domain_fact_count"])),
        "end_domain_facts": int(cast(int, end["domain_fact_count"])),
        "new_domain_facts": int(cast(int, end["domain_fact_count"]))
        - int(cast(int, start["domain_fact_count"])),
        "start_events": int(cast(int, start["event_count"])),
        "end_events": int(cast(int, end["event_count"])),
        "new_events": int(cast(int, end["event_count"])) - int(cast(int, start["event_count"])),
        "start_outbox_rows": int(cast(int, start["outbox_count"])),
        "end_outbox_rows": int(cast(int, end["outbox_count"])),
        "new_outbox_rows": int(cast(int, end["outbox_count"]))
        - int(cast(int, start["outbox_count"])),
        "start_record_position": int(cast(int, start["record_position"])),
        "end_record_position": int(cast(int, end["record_position"])),
        "record_position_delta": int(cast(int, end["record_position"]))
        - int(cast(int, start["record_position"])),
        "start_project_delivery_digest": _digest_text(start["project_delivery_digest"]),
        "end_project_delivery_digest": _digest_text(end["project_delivery_digest"]),
        "projection_semantic_delta": (
            0
            if bytes(cast(bytes, start["project_delivery_digest"]))
            == bytes(cast(bytes, end["project_delivery_digest"]))
            else 1
        ),
    }
    end_body = cast(dict[str, object], end["snapshot_body"])
    return graph(end_body), measurement


def _signed_checkpoint_snapshot(snapshot_body: dict[str, object]) -> dict[str, object]:
    signed_keys = {
        str(value) for value in cast(list[object], snapshot_body.get("signed_checkpoint_keys", []))
    }
    if not signed_keys:
        return snapshot_body
    definitions = [
        row
        for row in cast(list[dict[str, object]], snapshot_body["checkpoint_definitions"])
        if str(row["checkpoint_key"]) in signed_keys
    ]
    definition_ids = {str(row["checkpoint_definition_id"]) for row in definitions}
    return {
        **snapshot_body,
        "checkpoint_definitions": definitions,
        "checkpoint_criteria": [
            row
            for row in cast(list[dict[str, object]], snapshot_body["checkpoint_criteria"])
            if str(row["checkpoint_definition_id"]) in definition_ids
        ],
        "project_delivery_rows": [
            row
            for row in cast(list[dict[str, object]], snapshot_body["project_delivery_rows"])
            if str(row["checkpoint_key"]) in signed_keys
        ],
    }


def graph(snapshot_body: dict[str, object]) -> dict[str, object]:
    """Project the exhaustive snapshot into stable, sorted reconciliation sets."""

    relations = _set(snapshot_body, "relations")
    custody = cast(list[dict[str, object]], snapshot_body["custody_intervals"])
    unexpected, forbidden, unresolved, cycles = _target_anomaly.sets(snapshot_body)
    signed_snapshot = _signed_checkpoint_snapshot(snapshot_body)
    checkpoint_definitions, checkpoint_criteria = _checkpoint_expectation_sql.graph_sets(
        signed_snapshot
    )
    value: dict[str, object] = {
        "stable_aliases": _set(snapshot_body, "stable_aliases"),
        "operation_identities": _set(snapshot_body, "planned_operations"),
        "operation_results": _set(snapshot_body, "operation_results"),
        "tickets": _set(snapshot_body, "ticket_bindings"),
        "lifecycle_facts": _set(snapshot_body, "lifecycle_episodes"),
        "priority_facts": _set(snapshot_body, "priority_facts"),
        "custody_intervals": _set(snapshot_body, "custody_intervals"),
        "active_claims": _canonical_set(row for row in custody if row.get("released_at") is None),
        "alias_revisions": _set(snapshot_body, "alias_revisions"),
        "relations": relations,
        "relation_endpoints": sorted(
            {
                f"{row['source_ticket_id']}->{row['target_ticket_id']}"
                for row in cast(list[dict[str, object]], snapshot_body["relations"])
            }
        ),
        "source_links": _set(snapshot_body, "source_link_revisions"),
        "checkpoint_definitions": checkpoint_definitions,
        "checkpoint_criteria": checkpoint_criteria,
        "project_delivery_rows": _canonical_set(_project_delivery_values(signed_snapshot)),
        "events": _set(snapshot_body, "event_ids"),
        "outbox_rows": _set(snapshot_body, "outbox_rows"),
        "unexpected": unexpected,
        "forbidden": forbidden,
        "unresolved": unresolved,
        "cycles": cycles,
    }
    digest = hashlib.sha256(rfc8785.dumps(cast(Any, value))).hexdigest()
    value["graph_digest"] = f"sha256:{digest}"
    return value


def _event_ids(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    operation_results: list[dict[str, object]],
) -> list[UUID]:
    identifiers = {
        cast(UUID, event_id)
        for result in operation_results
        for event_id in cast(list[object], result["event_ids"])
    }
    rows = connection.execute(
        """
        SELECT event_id FROM migration_import_run_facts
        WHERE run_id = %s
          AND state IN ('importing', 'pass_one_complete')
        ORDER BY fact_sequence
        """,
        (run_id,),
    ).fetchall()
    identifiers.update(cast(UUID, row["event_id"]) for row in rows)
    return sorted(identifiers, key=str)


def _scoped_events(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    event_ids: list[UUID],
) -> list[dict[str, object]]:
    if not event_ids:
        return []
    return _rows(
        connection,
        """
        SELECT event_id, stream_id, sequence, kind, aggregate_id,
            client_command_id,
            actor_principal_id, origin, payload, request_sha256, record_position
        FROM events
        WHERE tenant_id = %s AND event_id = ANY(%s)
        ORDER BY record_position, event_id
        """,
        (tenant_id, event_ids),
    )


def _scoped_outbox(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    event_ids: list[UUID],
) -> list[dict[str, object]]:
    if not event_ids:
        return []
    return _rows(
        connection,
        """
        SELECT outgoing.outbox_id, outgoing.event_id, outgoing.topic,
            outgoing.payload, event.record_position
        FROM outbox AS outgoing
        JOIN events AS event ON event.event_id = outgoing.event_id
        WHERE outgoing.tenant_id = %s AND outgoing.event_id = ANY(%s)
        ORDER BY event.record_position, outgoing.outbox_id
        """,
        (tenant_id, event_ids),
    )


def _ticket_rows(
    connection: psycopg.Connection[dict[str, object]],
    query: str,
    tenant_id: UUID,
    ticket_ids: list[object],
    *,
    extra: tuple[object, ...] = (),
) -> list[dict[str, object]]:
    if not ticket_ids:
        return []
    parameters = (tenant_id, *extra[:1], ticket_ids, *extra[1:])
    return _rows(connection, query, parameters)


def _rows(
    connection: psycopg.Connection[dict[str, object]],
    query: str,
    parameters: tuple[object, ...],
) -> list[dict[str, object]]:
    return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def _normal(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _normal(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normal(item) for item in value]
    return _normal_scalar(value)


def _normal_scalar(value: object) -> object:
    if isinstance(value, bytes):
        return f"sha256:{value.hex()}"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value)
    return value


def _set(snapshot_body: dict[str, object], key: str) -> list[str]:
    return _canonical_set(cast(list[object], snapshot_body[key]))


def _project_delivery_values(snapshot_body: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "project_key": row["project_key"],
            "checkpoint_key": row["checkpoint_key"],
            "row_payload": {
                key: value
                for key, value in cast(dict[str, object], row["row_payload"]).items()
                if key not in _PROJECT_DELIVERY_VOLATILE
            },
        }
        for row in cast(list[dict[str, object]], snapshot_body["project_delivery_rows"])
    ]


def _canonical_set(values: Iterable[object]) -> list[str]:
    return sorted({rfc8785.dumps(cast(Any, item)).decode("utf-8") for item in values})


def _digest_text(value: object) -> str:
    return f"sha256:{bytes(cast(bytes, value)).hex()}"
