"""Atomic restricted import batches and four explicit operation implementations."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from ctower_client.models import (
    CtowerProjectExactAliasOperation,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportBatchResult,
    CtowerProjectImportOperation,
    CtowerProjectImportRun,
    CtowerProjectTicketRelationOperation,
    CtowerProjectTicketSeedOperation,
    MigrationImportOperationResult,
)
from ctower_kernel.migration import _link_sql, _ticket_operation_sql
from ctower_kernel.migration._operation_result_sql import canonical
from ctower_kernel.migration._run_read_sql import load_run
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.transaction import authority_connection, recover_ambiguous_commit
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
MAX_BATCH_BYTES = 256 * 1024


def apply_batch(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportBatchResult | RecordProblem:
    return recover_ambiguous_commit(
        lambda: _apply(dsn, actor, request, now=now, telemetry=telemetry)
    )


def _apply(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportBatchResult | RecordProblem:
    request_bytes = canonical(request)
    if len(request_bytes) > MAX_BATCH_BYTES:
        return _problem(None, "migration-operation-drift", "Import batch exceeds 256 KiB", 413)
    request_digest = hashlib.sha256(request_bytes).digest()
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        run = load_run(connection, actor, request.run_id, lock=True)
        if isinstance(run, RecordProblem) or not _batch_scope(connection, actor, request, run, now):
            return _problem(
                None, "migration-capability-denied", "Import binding is unavailable", 403
            )
        replay = _batch_replay(connection, request, request_digest)
        if replay is not None:
            return replay
        refusal = _preflight(connection, request)
        if refusal is not None:
            return refusal
        results: list[MigrationImportOperationResult] = []
        for operation in request.operations:
            outcome = _apply_operation(
                connection,
                actor,
                request,
                operation,
                now=now,
                telemetry=telemetry,
            )
            if isinstance(outcome, RecordProblem):
                connection.rollback()
                return outcome
            results.append(outcome)
        response = CtowerProjectImportBatchResult(
            run_id=request.run_id,
            batch_index=request.batch_index,
            batch_digest=request.batch_digest,
            results=tuple(results),
            record_watermark=max(result.record_position for result in results),
            projection_watermark=0,
            durability_state="durability_pending",
            accepted_position=None,
        )
        _record_batch(connection, request, request_digest, response, now)
        if run.state == "alias_plan_bound":
            _record_importing_state(
                connection, actor, run.semantic_digest, request, results, now=now
            )
        return response


def _apply_operation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectImportOperation,
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> MigrationImportOperationResult | RecordProblem:
    if isinstance(operation, CtowerProjectTicketSeedOperation):
        return _ticket_operation_sql.seed_ticket(
            connection, actor, batch, operation, now=now, telemetry=telemetry
        )
    if isinstance(operation, CtowerProjectExactAliasOperation):
        return _link_sql.bind_alias(
            connection, actor, batch, operation, now=now, telemetry=telemetry
        )
    if isinstance(operation, CtowerProjectTicketRelationOperation):
        return _ticket_operation_sql.add_relation(
            connection, actor, batch, operation, now=now, telemetry=telemetry
        )
    return _link_sql.add_source_link(
        connection, actor, batch, operation, now=now, telemetry=telemetry
    )


def _preflight(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportBatchRequest,
) -> RecordProblem | None:
    if len({item.identity.command_id for item in request.operations}) != len(request.operations):
        return _problem(None, "migration-operation-drift", "Batch command identities repeat")
    row = connection.execute(
        """
        SELECT coalesce(max(batch_index), -1) + 1 AS next_index
        FROM migration_import_batches WHERE run_id = %s
        """,
        (request.run_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("batch sequence is unavailable")
    if int(cast(int, row["next_index"])) != request.batch_index:
        return _problem(None, "migration-run-conflict", "Batch index is not contiguous")
    for operation in request.operations:
        if operation.identity.operation_kind != operation.operation:
            return _operation_drift(operation, "Operation identity kind changed")
        existing = connection.execute(
            """
            SELECT 1 FROM command_results WHERE principal_id = (
                SELECT principal_id FROM migration_importer_bindings WHERE run_id = %s
            ) AND client_command_id = %s
            """,
            (request.run_id, operation.identity.command_id),
        ).fetchone()
        identity = connection.execute(
            """
            SELECT 1 FROM migration_import_operation_results
            WHERE run_id = %s AND namespace = %s AND immutable_source_id = %s
              AND source_version_or_digest = %s AND operation_kind = %s
              AND planned_target_ref = %s
            """,
            (
                request.run_id,
                operation.identity.namespace,
                operation.identity.immutable_source_id,
                operation.identity.source_version_or_digest,
                operation.identity.operation_kind,
                operation.identity.planned_target_ref,
            ),
        ).fetchone()
        if existing is not None or identity is not None:
            return _operation_drift(operation, "Operation replay changed its batch")
    return None


def _batch_scope(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    run: CtowerProjectImportRun,
    now: datetime,
) -> bool:
    state = run.state
    if run.cutover_id != request.cutover_id or state not in {"alias_plan_bound", "importing"}:
        return False
    return (
        connection.execute(
            """
        SELECT 1 FROM migration_importer_bindings AS binding
        JOIN LATERAL (
            SELECT lifecycle FROM migration_importer_credential_facts
            WHERE run_id = binding.run_id ORDER BY fact_sequence DESC LIMIT 1
        ) AS fact ON true
        WHERE binding.run_id = %s AND binding.cutover_id = %s
          AND binding.project_key = 'ctower' AND binding.principal_id = %s
          AND binding.tenant_id = %s AND binding.expires_at > %s
          AND fact.lifecycle = 'activated'
        """,
            (request.run_id, request.cutover_id, actor.principal_id, actor.tenant_id, now),
        ).fetchone()
        is not None
    )


def _batch_replay(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportBatchRequest,
    request_digest: bytes,
) -> CtowerProjectImportBatchResult | RecordProblem | None:
    row = connection.execute(
        """
        SELECT batch_digest, request_digest, response_body FROM migration_import_batches
        WHERE run_id = %s AND batch_index = %s
        """,
        (request.run_id, request.batch_index),
    ).fetchone()
    if row is None:
        return None
    if (
        bytes(cast(bytes, row["request_digest"])) != request_digest
        or _digest_text(row["batch_digest"]) != request.batch_digest
    ):
        return _problem(None, "migration-operation-drift", "Batch replay changed")
    original = CtowerProjectImportBatchResult.model_validate_json(json.dumps(row["response_body"]))
    return original.model_copy(
        update={
            "results": tuple(
                result.model_copy(update={"replayed": True}) for result in original.results
            )
        }
    )


def _record_batch(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportBatchRequest,
    request_digest: bytes,
    response: CtowerProjectImportBatchResult,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_import_batches (
            run_id, batch_index, batch_digest, request_digest,
            operation_count, response_body, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request.run_id,
            request.batch_index,
            _digest_bytes(request.batch_digest),
            request_digest,
            len(request.operations),
            Jsonb(response.model_dump(mode="json", by_alias=True)),
            now,
        ),
    )


def _record_importing_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    previous_semantic: str,
    request: CtowerProjectImportBatchRequest,
    results: list[MigrationImportOperationResult],
    *,
    now: datetime,
) -> None:
    row = connection.execute(
        """
        SELECT coalesce(max(fact_sequence), 0) + 1 AS sequence
        FROM migration_import_run_facts WHERE run_id = %s
        """,
        (request.run_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("run state sequence is unavailable")
    semantic = hashlib.sha256(
        previous_semantic.encode() + canonical(request) + b"importing"
    ).digest()
    connection.execute(
        """
        INSERT INTO migration_import_run_facts (
            run_fact_id, run_id, fact_sequence, state, export_equality_digest,
            alias_map_digest, semantic_digest, record_watermark, projection_watermark,
            event_id, actor_principal_id, command_id, recorded_at
        ) SELECT %s, run.run_id, %s, 'importing', fact.export_equality_digest,
            fact.alias_map_digest, %s, %s, fact.projection_watermark, %s, %s, %s, %s
        FROM migration_import_runs AS run
        JOIN LATERAL (
            SELECT * FROM migration_import_run_facts WHERE run_id = run.run_id
            ORDER BY fact_sequence DESC LIMIT 1
        ) AS fact ON true WHERE run.run_id = %s
        """,
        (
            _uuid7(now),
            int(cast(int, row["sequence"])),
            semantic,
            max(item.record_position for item in results),
            results[0].event_ids[0],
            actor.principal_id,
            results[0].command_id,
            now,
            request.run_id,
        ),
    )


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _digest_text(value: object) -> str:
    return f"sha256:{bytes(cast(bytes, value)).hex()}"


def _operation_drift(operation: CtowerProjectImportOperation, title: str) -> RecordProblem:
    return _problem(operation.identity.command_id, "migration-operation-drift", title)


def _problem(command_id: UUID | None, code: str, title: str, status: int = 409) -> RecordProblem:
    return RecordProblem(code, title, status, title, command_id)


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
