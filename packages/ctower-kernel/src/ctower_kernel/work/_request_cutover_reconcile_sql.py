"""Every-row and count reconciliation for one Request import batch."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, cast

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.transaction import authority_connection
from ctower_kernel.work._request_cutover_artifacts import artifact_digest_bytes
from ctower_kernel.work._request_cutover_types import RequestImportReconciliation

__all__ = ["reconcile_import_batch"]

_BATCH_SIZE = 25


def reconcile_import_batch(
    dsn: str,
    actor: Actor,
    manifest: dict[str, Any],
    *,
    manifest_digest: str,
    batch_index: int,
) -> RequestImportReconciliation | RecordProblem:
    rows = cast(list[dict[str, object]], manifest["rows"])
    start, end = batch_index * _BATCH_SIZE, min((batch_index + 1) * _BATCH_SIZE, len(rows))
    if batch_index < 0 or start >= len(rows):
        return _problem("The requested Request import batch does not exist.")
    expected_batch = rows[start:end]
    expected_prefix = rows[:end]
    actual, prefix = _load_observed(
        dsn,
        actor,
        manifest_digest,
        expected_batch,
        expected_prefix,
    )
    if len(actual) != len(expected_batch):
        return _problem("The imported batch count differs from the frozen source batch.")
    comparisons = _compare_batch(expected_batch, actual)
    if isinstance(comparisons, RecordProblem):
        return comparisons
    cumulative_by_project = {
        str(item["project_key"]): int(cast(int, item["count"])) for item in prefix
    }
    expected_cumulative = dict(
        sorted(Counter(str(item["project_key"]) for item in expected_prefix).items())
    )
    if cumulative_by_project != expected_cumulative:
        return _problem("The cumulative per-project import counts differ from the frozen prefix.")
    return _reconciliation(
        manifest,
        manifest_digest,
        batch_index,
        end,
        expected_batch,
        actual,
        comparisons,
        expected_cumulative,
        cumulative_by_project,
    )


def _load_observed(
    dsn: str,
    actor: Actor,
    manifest_digest: str,
    expected_batch: list[dict[str, object]],
    expected_prefix: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        actual = connection.execute(
            """
            SELECT import.source_request_number, import.request_id, import.content_digest,
                   import.original_owner_digest, import.relationships_digest,
                   request.project_key, request.created_at, request.source_ref,
                   owner.owner_id, priority.priority, triage.disposition,
                   COALESCE(relation.ticket_count, 0) AS ticket_count,
                   confirmation.acceptance_position,
                   ledger.last_position
            FROM request_import_rows AS import
            JOIN requests AS request
              ON request.tenant_id = import.tenant_id
             AND request.request_id = import.request_id
            JOIN LATERAL (
                SELECT owner_id FROM request_owner_facts
                WHERE tenant_id = request.tenant_id AND request_id = request.request_id
                ORDER BY sequence DESC LIMIT 1
            ) AS owner ON true
            JOIN LATERAL (
                SELECT priority FROM request_priority_facts
                WHERE tenant_id = request.tenant_id AND request_id = request.request_id
                ORDER BY sequence DESC LIMIT 1
            ) AS priority ON true
            JOIN LATERAL (
                SELECT disposition FROM request_triage_facts
                WHERE tenant_id = request.tenant_id AND request_id = request.request_id
                ORDER BY sequence DESC LIMIT 1
            ) AS triage ON true
            LEFT JOIN LATERAL (
                SELECT count(DISTINCT ticket_id) AS ticket_count
                FROM request_ticket_relation_facts AS fact
                WHERE fact.tenant_id = request.tenant_id
                  AND fact.request_id = request.request_id AND fact.active
            ) AS relation ON true
            LEFT JOIN durability_acceptance_confirmations AS confirmation
              ON confirmation.tenant_id = import.tenant_id
             AND confirmation.principal_id = import.imported_by
             AND confirmation.client_command_id = import.command_id
            CROSS JOIN record_position_ledger AS ledger
            WHERE import.tenant_id = %s AND import.manifest_digest = %s
              AND import.source_request_number = ANY(%s)
            ORDER BY import.source_request_number
            """,
            (
                actor.tenant_id,
                artifact_digest_bytes(manifest_digest),
                [cast(int, item["request_number"]) for item in expected_batch],
            ),
        ).fetchall()
        prefix = connection.execute(
            """
            SELECT count(*) AS count, request.project_key
            FROM request_import_rows AS import
            JOIN requests AS request
              ON request.tenant_id = import.tenant_id AND request.request_id = import.request_id
            WHERE import.tenant_id = %s AND import.manifest_digest = %s
              AND import.source_request_number = ANY(%s)
            GROUP BY request.project_key ORDER BY request.project_key
            """,
            (
                actor.tenant_id,
                artifact_digest_bytes(manifest_digest),
                [cast(int, item["request_number"]) for item in expected_prefix],
            ),
        ).fetchall()
    return actual, prefix


def _compare_batch(
    expected_batch: list[dict[str, object]], actual: list[dict[str, object]]
) -> list[dict[str, object]] | RecordProblem:
    actual_by_number = {int(cast(int, item["source_request_number"])): item for item in actual}
    comparisons: list[dict[str, object]] = []
    for expected in expected_batch:
        observed = actual_by_number.get(cast(int, expected["request_number"]))
        comparison = _comparison(expected, observed)
        if comparison is None:
            return _problem(f"The imported row differs from frozen {expected['id']}.")
        comparisons.append(comparison)
    return comparisons


def _reconciliation(
    manifest: dict[str, Any],
    manifest_digest: str,
    batch_index: int,
    end: int,
    expected_batch: list[dict[str, object]],
    actual: list[dict[str, object]],
    comparisons: list[dict[str, object]],
    expected_cumulative: dict[str, int],
    cumulative_by_project: dict[str, int],
) -> RequestImportReconciliation:
    batch_counts = dict(
        sorted(Counter(str(item["project_key"]) for item in expected_batch).items())
    )
    batch_plan = cast(list[dict[str, object]], manifest["batches"])[batch_index]
    sample_ids = tuple(cast(list[str], batch_plan["sample_ids"]))
    watermark = int(cast(int, actual[0]["last_position"]))
    return RequestImportReconciliation(
        manifest_digest,
        batch_index,
        len(expected_batch),
        batch_counts,
        len(actual),
        dict(Counter(str(item["project_key"]) for item in actual)),
        end,
        expected_cumulative,
        sum(cumulative_by_project.values()),
        cumulative_by_project,
        watermark,
        tuple(comparisons),
        sample_ids,
    )


def _comparison(
    expected: dict[str, object], observed: dict[str, object] | None
) -> dict[str, object] | None:
    if observed is None or observed["acceptance_position"] is None:
        return None
    triage = str(observed["disposition"])
    state = "NEW" if triage == "UNTRIAGED" else "TRIAGED"
    values = {
        "content_sha256": _stored_digest(observed["content_digest"]),
        "created_at": cast(datetime, observed["created_at"]).isoformat().replace("+00:00", "Z"),
        "durability_state": "accepted",
        "equal": True,
        "id": expected["id"],
        "implicit_ticket_count": int(cast(int, observed["ticket_count"])),
        "original_owner_sha256": _stored_digest(observed["original_owner_digest"]),
        "owner_id": str(observed["owner_id"]),
        "priority": str(observed["priority"]),
        "project_key": str(observed["project_key"]),
        "relationships_sha256": _stored_digest(observed["relationships_digest"]),
        "request_id": str(observed["request_id"]),
        "request_number": int(cast(int, observed["source_request_number"])),
        "source_alias": str(observed["source_ref"]),
        "state": state,
        "triage": triage,
    }
    projection = cast(dict[str, object], expected["projection"])
    expected_values = {
        "content_sha256": expected["content_sha256"],
        "id": expected["id"],
        "implicit_ticket_count": 0,
        "original_owner_sha256": expected["original_owner_sha256"],
        "owner_id": expected["mapped_principal_id"],
        "priority": projection["priority"],
        "project_key": expected["project_key"],
        "relationships_sha256": expected["relationships_sha256"],
        "request_id": expected["request_id"],
        "request_number": expected["request_number"],
        "source_alias": expected["id"],
        "state": projection["state"],
        "triage": projection["triage"],
    }
    if any(values[key] != expected_value for key, expected_value in expected_values.items()):
        return None
    return values


def _stored_digest(value: object) -> str:
    return f"sha256:{bytes(cast(bytes, value)).hex()}"


def _problem(detail: str) -> RecordProblem:
    return RecordProblem(
        code="migration-digest-mismatch",
        detail=detail,
        status=409,
        title="Request import reconciliation failed",
    )
