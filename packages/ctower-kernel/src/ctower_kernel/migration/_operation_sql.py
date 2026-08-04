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
    DurabilityState,
    MigrationImportOperationResult,
)
from ctower_kernel.migration import (
    _checkpoint_expectation_sql,
    _link_sql,
    _pass_state_sql,
    _pass_two_sql,
    _ticket_operation_sql,
)
from ctower_kernel.migration._event_sql import commit_event, migration_payload
from ctower_kernel.migration._operation_result_sql import canonical, migration_sequence
from ctower_kernel.migration._run_read_sql import load_run
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.transaction import (
    authority_connection,
    lock_project_delivery_scope,
    recover_ambiguous_commit,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
MAX_BATCH_BYTES = 256 * 1024


def apply_batch(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportBatchResult | RecordProblem:
    return recover_ambiguous_commit(
        lambda: _apply(
            dsn,
            actor,
            request,
            command_id=command_id,
            now=now,
            telemetry=telemetry,
        )
    )


def _apply(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportBatchResult | RecordProblem:
    request_bytes = canonical(request)
    if len(request_bytes) > MAX_BATCH_BYTES:
        return _problem(None, "migration-operation-drift", "Import batch exceeds 256 KiB", 413)
    request_digest = hashlib.sha256(request_bytes).digest()
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        guarded = _guard_batch(
            connection,
            actor,
            request,
            command_id=command_id,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        if not isinstance(guarded, CtowerProjectImportRun):
            return guarded
        run = guarded
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
        response, event_id, position = _commit_batch_response(
            connection,
            actor,
            request,
            results,
            command_id=command_id,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        _record_batch(connection, request, request_digest, response, now)
        state = _pass_one_state(connection, request)
        _record_run_state(
            connection,
            actor,
            run.semantic_digest,
            request,
            state=state,
            event_id=event_id,
            position=position,
            command_id=command_id,
            now=now,
        )
        return response


def _guard_batch(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    *,
    command_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportRun | CtowerProjectImportBatchResult | RecordProblem:
    lock_project_delivery_scope(connection, actor.tenant_id, "all-projects")
    run = load_run(connection, actor, request.run_id, lock=True)
    if isinstance(run, RecordProblem) or not _batch_scope(connection, actor, request, run, now):
        return _problem(None, "migration-capability-denied", "Import binding unavailable", 403)
    if not _expected_batch(connection, request, request_digest):
        return _problem(command_id, "migration-operation-drift", "Batch is outside signed plan")
    replay = _batch_replay(
        connection,
        actor,
        run,
        request,
        request_digest,
        now,
        telemetry,
    )
    if replay is not None:
        return replay
    if run.state not in {"alias_plan_bound", "importing"}:
        return _problem(None, "migration-run-conflict", "Pass one is already closed")
    return _preflight(connection, request) or run


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


def _expected_batch(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportBatchRequest,
    request_digest: bytes,
) -> bool:
    row = connection.execute(
        """
        SELECT batch_digest, request_digest, operation_count
        FROM migration_import_plan_batches
        WHERE run_id = %s AND batch_index = %s
        """,
        (request.run_id, request.batch_index),
    ).fetchone()
    return (
        row is not None
        and bytes(cast(bytes, row["batch_digest"])) == _digest_bytes(request.batch_digest)
        and bytes(cast(bytes, row["request_digest"])) == request_digest
        and int(cast(int, row["operation_count"])) == len(request.operations)
    )


def _batch_scope(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    run: CtowerProjectImportRun,
    now: datetime,
) -> bool:
    state = run.state
    if run.cutover_id != request.cutover_id or state not in {
        "alias_plan_bound",
        "importing",
        "pass_one_complete",
        "pass_two_started",
        "pass_two_noop",
    }:
        return False
    return (
        connection.execute(
            """
        SELECT 1 FROM migration_importer_bindings AS binding
        JOIN principal_credentials AS credential
          ON credential.principal_id = binding.principal_id
         AND credential.tenant_id = binding.tenant_id
         AND credential.credential_digest = binding.credential_digest
        JOIN LATERAL (
            SELECT lifecycle FROM migration_importer_credential_facts
            WHERE run_id = binding.run_id ORDER BY fact_sequence DESC LIMIT 1
        ) AS fact ON true
        WHERE binding.run_id = %s AND binding.cutover_id = %s
          AND binding.project_key = 'ctower' AND binding.principal_id = %s
          AND binding.tenant_id = %s AND binding.expires_at > %s
          AND fact.lifecycle = 'activated'
          AND credential.revoked_at IS NULL
        """,
            (request.run_id, request.cutover_id, actor.principal_id, actor.tenant_id, now),
        ).fetchone()
        is not None
    )


def _batch_replay(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run: CtowerProjectImportRun,
    request: CtowerProjectImportBatchRequest,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
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
    receipt = connection.execute(
        """
        SELECT request_digest FROM migration_import_replay_receipts
        WHERE run_id = %s AND batch_index = %s
        """,
        (request.run_id, request.batch_index),
    ).fetchone()
    if receipt is not None:
        return _existing_replay(receipt, request_digest, original)
    preparation = _prepare_pass_two(
        connection,
        actor,
        run,
        request,
        now=now,
        telemetry=telemetry,
    )
    if preparation is not None:
        return preparation
    measured = _measure_replay(connection, request, request_digest, now)
    if isinstance(measured, RecordProblem):
        return measured
    if _last_planned_batch(connection, request):
        _pass_two_sql.persist(connection, request.run_id, "end", measured, now=now)
        _pass_state_sql.transition(
            connection,
            actor,
            request,
            "pass_two_noop",
            now=now,
            telemetry=telemetry,
        )
    return _replayed(original)


def _existing_replay(
    receipt: dict[str, object],
    request_digest: bytes,
    original: CtowerProjectImportBatchResult,
) -> CtowerProjectImportBatchResult | RecordProblem:
    if bytes(cast(bytes, receipt["request_digest"])) != request_digest:
        return _problem(None, "migration-operation-drift", "Replay receipt changed")
    return _replayed(original)


def _prepare_pass_two(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run: CtowerProjectImportRun,
    request: CtowerProjectImportBatchRequest,
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> RecordProblem | None:
    if run.state == "pass_one_complete":
        if request.batch_index != 0:
            return _problem(None, "migration-run-conflict", "Pass two must start at batch zero")
        start = _pass_two_sql.capture(connection, request.run_id)
        readiness = _pass_two_sql.ready_for_pass_two(connection, request.run_id, start)
        if not readiness.ready:
            return _checkpoint_conflict(
                "Project Delivery target is not current for pass two",
                readiness.checkpoint_mismatches,
            )
        _pass_state_sql.transition(
            connection,
            actor,
            request,
            "pass_two_started",
            now=now,
            telemetry=telemetry,
        )
        _pass_two_sql.persist(
            connection,
            request.run_id,
            "start",
            start,
            now=now,
        )
    elif run.state != "pass_two_started":
        return _problem(None, "migration-run-conflict", "Pass two is not active")
    return None


def _measure_replay(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportBatchRequest,
    request_digest: bytes,
    now: datetime,
) -> _pass_two_sql.TargetSnapshot | RecordProblem:
    if not _next_replay_is_contiguous(connection, request):
        return _problem(None, "migration-run-conflict", "Pass-two batch is not contiguous")
    before = _pass_two_sql.capture(connection, request.run_id)
    after = _pass_two_sql.capture(connection, request.run_id)
    if not _pass_two_sql.zero_delta(before, after):
        connection.rollback()
        return _problem(None, "migration-pass-two-drift", "Pass-two target state changed")
    _record_replay(connection, request, request_digest, before, after, now)
    return after


def _next_replay_is_contiguous(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportBatchRequest,
) -> bool:
    row = connection.execute(
        """
        SELECT coalesce(max(batch_index), -1) + 1 AS next_index
        FROM migration_import_replay_receipts WHERE run_id = %s
        """,
        (request.run_id,),
    ).fetchone()
    return row is not None and int(cast(int, row["next_index"])) == request.batch_index


def _record_replay(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportBatchRequest,
    request_digest: bytes,
    before: _pass_two_sql.TargetSnapshot,
    after: _pass_two_sql.TargetSnapshot,
    now: datetime,
) -> None:
    measured = (
        after.domain_fact_count - before.domain_fact_count,
        after.event_count - before.event_count,
        after.outbox_count - before.outbox_count,
        after.record_position - before.record_position,
        0 if after.project_delivery_digest == before.project_delivery_digest else 1,
    )
    if measured != (0, 0, 0, 0, 0):
        raise RuntimeError("nonzero pass-two measurement escaped zero-delta validation")
    connection.execute(
        """
        INSERT INTO migration_import_replay_receipts (
            run_id, batch_index, batch_digest, request_digest, operation_count,
            new_domain_facts, new_events, new_outbox_rows, record_position_delta,
            projection_semantic_delta, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request.run_id,
            request.batch_index,
            _digest_bytes(request.batch_digest),
            request_digest,
            len(request.operations),
            *measured,
            now,
        ),
    )


def _replayed(original: CtowerProjectImportBatchResult) -> CtowerProjectImportBatchResult:
    return original.model_copy(
        update={
            "results": tuple(
                result.model_copy(update={"replayed": True}) for result in original.results
            )
        }
    )


def _last_planned_batch(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportBatchRequest,
) -> bool:
    row = connection.execute(
        """
        SELECT plan.batch_count,
            (SELECT count(*) FROM migration_import_replay_receipts AS receipt
             WHERE receipt.run_id = plan.run_id) AS replay_count
        FROM migration_import_plans AS plan WHERE plan.run_id = %s
        """,
        (request.run_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("signed import plan is unavailable")
    return int(cast(int, row["replay_count"])) == int(cast(int, row["batch_count"]))


def _commit_batch_response(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    results: list[MigrationImportOperationResult],
    *,
    command_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[CtowerProjectImportBatchResult, UUID, int]:
    captured: list[CtowerProjectImportBatchResult] = []

    def response(_event_id: UUID, position: int) -> dict[str, object]:
        result = CtowerProjectImportBatchResult(
            run_id=request.run_id,
            batch_index=request.batch_index,
            batch_digest=request.batch_digest,
            results=tuple(results),
            record_watermark=position,
            projection_watermark=0,
            durability_state=DurabilityState.DURABILITY_PENDING,
            accepted_position=None,
        )
        captured.append(result)
        return cast(dict[str, object], result.model_dump(mode="json", by_alias=True))

    event_id, position = commit_event(
        connection,
        actor,
        aggregate_id=request.run_id,
        command_id=command_id,
        kind=EventKind.MIGRATION_CHANGED,
        payload=migration_payload(
            "import_batch_applied",
            run_id=request.run_id,
            cutover_id=request.cutover_id,
            target_id=str(request.batch_index),
        ),
        request_digest=request_digest,
        sequence=migration_sequence(connection, actor, request.run_id),
        stream_id=f"migration:{request.run_id}",
        now=now,
        telemetry=telemetry,
        response=response,
        subjects=(("migration", request.run_id),),
    )
    return captured[0], event_id, position


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


def _record_run_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    previous_semantic: str,
    request: CtowerProjectImportBatchRequest,
    *,
    state: str,
    event_id: UUID,
    position: int,
    command_id: UUID,
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
        previous_semantic.encode() + canonical(request) + state.encode()
    ).digest()
    connection.execute(
        """
        INSERT INTO migration_import_run_facts (
            run_fact_id, run_id, fact_sequence, state, export_equality_digest,
            alias_map_digest, semantic_digest, record_watermark, projection_watermark,
            event_id, actor_principal_id, command_id, recorded_at
        ) SELECT %s, run.run_id, %s, %s, fact.export_equality_digest,
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
            state,
            semantic,
            position,
            event_id,
            actor.principal_id,
            command_id,
            now,
            request.run_id,
        ),
    )


def _pass_one_state(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportBatchRequest,
) -> str:
    row = connection.execute(
        "SELECT batch_count FROM migration_import_plans WHERE run_id = %s",
        (request.run_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("signed import plan is unavailable")
    return (
        "pass_one_complete"
        if request.batch_index + 1 == int(cast(int, row["batch_count"]))
        else "importing"
    )


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _digest_text(value: object) -> str:
    return f"sha256:{bytes(cast(bytes, value)).hex()}"


def _operation_drift(operation: CtowerProjectImportOperation, title: str) -> RecordProblem:
    return _problem(operation.identity.command_id, "migration-operation-drift", title)


def _problem(command_id: UUID | None, code: str, title: str, status: int = 409) -> RecordProblem:
    return RecordProblem(code, title, status, title, command_id)


def _checkpoint_conflict(
    title: str,
    mismatches: tuple[_checkpoint_expectation_sql.CheckpointMismatch, ...],
) -> RecordProblem:
    if not mismatches:
        return _problem(None, "migration-run-conflict", title)
    detail = f"{title}: " + "; ".join(
        f"{item.checkpoint_key} ({item.detail})" for item in mismatches
    )
    return RecordProblem(
        "migration-run-conflict",
        detail,
        409,
        title,
        None,
        unmet_facts=tuple(f"checkpoint:{item.checkpoint_key}" for item in mismatches),
    )


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
