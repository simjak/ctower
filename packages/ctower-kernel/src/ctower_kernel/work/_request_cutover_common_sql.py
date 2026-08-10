"""Shared PostgreSQL choreography for the one-way Request cutover."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid5

import psycopg
import rfc8785

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    MigrationChangedPayload,
)
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.transaction import EventCommit, RecordTransaction
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_cutover_artifacts import artifact_digest_bytes
from ctower_kernel.work._request_cutover_types import RequestCutoverResult

__all__ = [
    "CUTOVER_NAMESPACE",
    "commit_cutover_event",
    "cutover_id",
    "human_operator_refusal",
    "load_manifest",
    "owner_is_active_and_addressable",
    "refuse",
    "request_cutover_result",
    "target_authority_inventory",
    "target_watermark",
]

CUTOVER_NAMESPACE = UUID("4a4fa05a-15ee-55d5-942b-6427217ab3bf")
_ZERO_HASH = bytes(32)


def cutover_id(manifest_digest: str) -> UUID:
    return uuid5(CUTOVER_NAMESPACE, f"request-cutover:{manifest_digest}")


def human_operator_refusal(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, command_id: UUID
) -> RecordProblem | None:
    row = connection.execute(
        """
        SELECT 1
        FROM human_role_bindings AS binding
        JOIN principals AS principal
          ON principal.tenant_id = binding.tenant_id
         AND principal.principal_id = binding.principal_id
        LEFT JOIN human_role_binding_revocations AS revocation
          ON revocation.tenant_id = binding.tenant_id
         AND revocation.binding_id = binding.binding_id
        WHERE binding.tenant_id = %s AND binding.principal_id = %s
          AND binding.role = 'operator' AND principal.kind = 'operator'
          AND NOT principal.disabled AND revocation.binding_id IS NULL
        LIMIT 1
        """,
        (actor.tenant_id, actor.principal_id),
    ).fetchone()
    if row is not None:
        return None
    return RecordProblem(
        code="request-import-forbidden",
        detail="The Request import command requires an active authenticated human operator.",
        status=403,
        title="Request import forbidden",
        command_id=command_id,
    )


def owner_is_active_and_addressable(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    principal_id: UUID,
    project_key: str,
) -> bool:
    """Prove an import owner is active and addressable in the exact project."""

    row = connection.execute(
        """
        SELECT 1
        FROM principals AS principal
        WHERE principal.tenant_id = %s AND principal.principal_id = %s
          AND NOT principal.disabled
          AND (
            EXISTS (
                SELECT 1 FROM project_seats AS seat
                WHERE seat.tenant_id = principal.tenant_id
                  AND seat.principal_id = principal.principal_id
                  AND seat.project_key = %s
            ) OR EXISTS (
                SELECT 1 FROM human_role_bindings AS binding
                LEFT JOIN human_role_binding_revocations AS revocation
                  ON revocation.tenant_id = binding.tenant_id
                 AND revocation.binding_id = binding.binding_id
                WHERE binding.tenant_id = principal.tenant_id
                  AND binding.principal_id = principal.principal_id
                  AND %s = ANY(binding.project_keys)
                  AND revocation.binding_id IS NULL
            )
          )
        LIMIT 1
        """,
        (tenant_id, principal_id, project_key, project_key),
    ).fetchone()
    return row is not None


def target_authority_inventory(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID
) -> dict[str, object]:
    rows = connection.execute(
        """
        SELECT principal.principal_id, principal.kind, principal.disabled,
               COALESCE(array_agg(DISTINCT grant_row.project_key)
                        FILTER (WHERE grant_row.project_key IS NOT NULL), '{}') AS project_keys
        FROM principals AS principal
        LEFT JOIN (
            SELECT seat.tenant_id, seat.principal_id, seat.project_key
            FROM project_seats AS seat
            UNION ALL
            SELECT binding.tenant_id, binding.principal_id, project_key
            FROM human_role_bindings AS binding
            CROSS JOIN LATERAL unnest(binding.project_keys) AS project_key
            LEFT JOIN human_role_binding_revocations AS revocation
              ON revocation.tenant_id = binding.tenant_id
             AND revocation.binding_id = binding.binding_id
            WHERE revocation.binding_id IS NULL
        ) AS grant_row
          ON grant_row.tenant_id = principal.tenant_id
         AND grant_row.principal_id = principal.principal_id
        WHERE principal.tenant_id = %s
        GROUP BY principal.principal_id, principal.kind, principal.disabled
        ORDER BY principal.principal_id
        """,
        (tenant_id,),
    ).fetchall()
    principals = [
        {
            "disabled": bool(row["disabled"]),
            "kind": str(row["kind"]),
            "principal_id": str(row["principal_id"]),
            "project_keys": sorted(cast(list[str], row["project_keys"])),
        }
        for row in rows
    ]
    body: dict[str, object] = {"principals": principals, "tenant_id": str(tenant_id)}
    body["authority_digest"] = (
        f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, body))).hexdigest()}"
    )
    return body


def load_manifest(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, manifest_digest: str
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT manifest.manifest_artifact
        FROM request_import_manifests AS manifest
        WHERE manifest.tenant_id = %s AND manifest.manifest_digest = %s
          AND (
            SELECT state FROM request_cutover_epoch_facts AS fact
            WHERE fact.tenant_id = manifest.tenant_id
              AND fact.manifest_digest = manifest.manifest_digest
            ORDER BY sequence DESC LIMIT 1
          ) = 'prepared'
        """,
        (actor.tenant_id, artifact_digest_bytes(manifest_digest)),
    ).fetchone()
    return None if row is None else cast(dict[str, Any], row["manifest_artifact"])


def target_watermark(connection: psycopg.Connection[dict[str, object]]) -> int:
    row = connection.execute(
        "SELECT last_position FROM record_position_ledger WHERE singleton"
    ).fetchone()
    if row is None:
        raise RuntimeError("Record position ledger is unavailable")
    return int(cast(int, row["last_position"]))


def commit_cutover_event(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    *,
    command_id: UUID,
    manifest_digest: str,
    operation: str,
    request_digest: bytes,
    result: RequestCutoverResult,
    telemetry: TelemetryContext,
    now: datetime,
    status_code: int = 202,
) -> RequestCutoverResult:
    aggregate_id = cutover_id(manifest_digest)
    stream_id = f"migration:{aggregate_id}"
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (stream_id,))
    previous = connection.execute(
        """
        SELECT event_id, event_hash, sequence
        FROM events
        WHERE tenant_id = %s AND stream_id = %s
        ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, stream_id),
    ).fetchone()
    event_id = uuid7(now)
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=aggregate_id,
        causation_id=None if previous is None else cast(UUID, previous["event_id"]),
        client_command_id=command_id,
        correlation_id=telemetry.correlation_uuid(command_id),
        event_id=event_id,
        kind=EventKind.MIGRATION_CHANGED,
        origin=EventOrigin.API,
        payload=MigrationChangedPayload(
            operation,
            aggregate_id,
            aggregate_id,
            "ctower",
            manifest_digest,
        ),
        prev_hash=_ZERO_HASH if previous is None else bytes(cast(bytes, previous["event_hash"])),
        request_sha256=request_digest,
        sequence=1 if previous is None else int(cast(int, previous["sequence"])) + 1,
        server_time=now,
        stream_id=stream_id,
        tenant_id=actor.tenant_id,
    )
    committed = RequestCutoverResult(
        command_id=result.command_id,
        operation=result.operation,
        manifest_digest=result.manifest_digest,
        state=result.state,
        imported_count=result.imported_count,
        target_watermark=target_watermark(connection) + 1,
        request_id=result.request_id,
        request_number=result.request_number,
        event_ids=(event_id,),
    )
    transaction.commit_batch(
        (EventCommit(event, uuid7(now)),),
        response_body=committed.response_payload(),
        status_code=status_code,
        telemetry=telemetry,
        now=now,
        subjects=(("migration", aggregate_id),),
    )
    return committed


def request_cutover_result(payload: dict[str, object]) -> RequestCutoverResult:
    request_id = payload.get("request_id")
    request_number = payload.get("request_number")
    return RequestCutoverResult(
        command_id=UUID(str(payload["command_id"])),
        operation=str(payload["operation"]),
        manifest_digest=str(payload["manifest_digest"]),
        state=str(payload["state"]),
        imported_count=int(cast(int, payload["imported_count"])),
        target_watermark=int(cast(int, payload["target_watermark"])),
        request_id=None if request_id is None else UUID(str(request_id)),
        request_number=None if request_number is None else int(cast(int, request_number)),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
    )


def refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
    problem: RecordProblem,
    *,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem
