"""Server-recomputed reconciliation and importer credential finalization."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ctower_client.models import (
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRun,
    CtowerProjectReconciliationResult,
    DurabilityState,
    MigrationDispositions,
)
from ctower_kernel.migration._event_sql import commit_event, migration_payload
from ctower_kernel.migration._measurement_sql import MigrationMeasurement, measure
from ctower_kernel.migration._operation_result_sql import canonical, migration_sequence
from ctower_kernel.migration._run_read_sql import load_run
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.transaction import authority_connection, recover_ambiguous_commit
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def finalize_run(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportFinalizeRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectReconciliationResult | RecordProblem:
    return recover_ambiguous_commit(
        lambda: _finalize(dsn, actor, request, command_id=command_id, now=now, telemetry=telemetry)
    )


def _finalize(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportFinalizeRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectReconciliationResult | RecordProblem:
    request_digest = hashlib.sha256(canonical(request)).digest()
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        replay = _replay(connection, actor, command_id, request_digest)
        if replay is not None:
            return replay
        run = load_run(connection, actor, request.run_id, lock=True)
        if isinstance(run, RecordProblem) or not _scope(run, request):
            return _problem(command_id, "migration-import-finalization-refused")
        measured = measure(connection, request.run_id)
        if measured is None:
            return _problem(command_id, "migration-import-finalization-refused")
        dispositions = measured.dispositions
        selected = sum(dispositions.model_dump().values())
        if (
            selected != measured.conservation.selected_logical_items
            or run.counts.planned_operations < 1
            or run.counts.applied_operations != run.counts.planned_operations
            or run.counts.replayed_operations != run.counts.planned_operations
        ):
            return _problem(command_id, "migration-import-finalization-refused")
        report_digest = _report_digest(request_digest, run.semantic_digest, dispositions)
        return _commit_reconciliation(
            connection,
            actor,
            request,
            run=run,
            dispositions=dispositions,
            measured=measured,
            report_digest=report_digest,
            command_id=command_id,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _commit_reconciliation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportFinalizeRequest,
    *,
    run: CtowerProjectImportRun,
    dispositions: MigrationDispositions,
    measured: MigrationMeasurement,
    report_digest: str,
    command_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectReconciliationResult:
    reconciliation_id = _uuid7(now)
    captured: list[CtowerProjectReconciliationResult] = []
    event_id, position = commit_event(
        connection,
        actor,
        aggregate_id=request.run_id,
        command_id=command_id,
        kind=EventKind.MIGRATION_CHANGED,
        payload=migration_payload(
            "reconciled",
            run_id=request.run_id,
            cutover_id=request.cutover_id,
            target_id=str(reconciliation_id),
        ),
        request_digest=request_digest,
        sequence=migration_sequence(connection, actor, request.run_id),
        stream_id=f"migration:{request.run_id}",
        now=now,
        telemetry=telemetry,
        response=_result_response(
            captured,
            reconciliation_id,
            request,
            run=run,
            dispositions=dispositions,
            measured=measured,
            report_digest=report_digest,
        ),
        subjects=(("migration", request.run_id),),
    )
    _insert_facts(
        connection,
        actor,
        request,
        captured[0],
        event_id=event_id,
        position=position,
        command_id=command_id,
        now=now,
    )
    return captured[0]


def _result_response(
    captured: list[CtowerProjectReconciliationResult],
    reconciliation_id: UUID,
    request: CtowerProjectImportFinalizeRequest,
    *,
    run: CtowerProjectImportRun,
    dispositions: MigrationDispositions,
    measured: MigrationMeasurement,
    report_digest: str,
) -> Callable[[UUID, int], dict[str, object]]:
    def response(event_id: UUID, position: int) -> dict[str, object]:
        del event_id
        result = _result(
            reconciliation_id,
            request,
            run=run,
            dispositions=dispositions,
            measured=measured,
            report_digest=report_digest,
            record_position=position,
        )
        captured.append(result)
        return cast(dict[str, object], result.model_dump(mode="json", by_alias=True))

    return response


def _result(
    reconciliation_id: UUID,
    request: CtowerProjectImportFinalizeRequest,
    *,
    run: CtowerProjectImportRun,
    dispositions: MigrationDispositions,
    measured: MigrationMeasurement,
    report_digest: str,
    record_position: int,
) -> CtowerProjectReconciliationResult:
    return CtowerProjectReconciliationResult.model_validate(
        {
            "schema": "ctower.ctower-project-reconciliation/v1",
            "reconciliation_id": reconciliation_id,
            "run_id": request.run_id,
            "cutover_id": request.cutover_id,
            "project_key": "ctower",
            "pinned_digests": run.pinned_digests,
            "dispositions": dispositions,
            "conservation": measured.conservation,
            "source_native_watermark": measured.source_native_watermark,
            "export_native_watermark": measured.export_native_watermark,
            "record_watermark": record_position,
            "projection_watermark": 0,
            "target_semantic_digest": run.semantic_digest,
            "report_digest": report_digest,
            "durability_state": DurabilityState.DURABILITY_PENDING,
            "accepted_position": None,
        }
    )


def _insert_facts(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportFinalizeRequest,
    result: CtowerProjectReconciliationResult,
    *,
    event_id: UUID,
    position: int,
    command_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_reconciliation_facts (
            reconciliation_id, run_id, report_digest, target_semantic_digest,
            report_body, event_id, actor_principal_id, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.reconciliation_id,
            request.run_id,
            _digest_bytes(result.report_digest),
            _digest_bytes(result.target_semantic_digest),
            Jsonb(result.model_dump(mode="json", by_alias=True)),
            event_id,
            actor.principal_id,
            command_id,
            now,
        ),
    )
    _insert_run_finalization(
        connection,
        actor,
        request.run_id,
        event_id=event_id,
        position=position,
        semantic_digest=result.report_digest,
        command_id=command_id,
        now=now,
    )
    _revoke_importer(connection, actor, request.run_id, command_id, now)


def _insert_run_finalization(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run_id: UUID,
    *,
    event_id: UUID,
    position: int,
    semantic_digest: str,
    command_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_import_run_facts (
            run_fact_id, run_id, fact_sequence, state, export_equality_digest,
            alias_map_digest, semantic_digest, record_watermark, projection_watermark,
            event_id, actor_principal_id, command_id, recorded_at
        ) SELECT %s, run_id, fact_sequence + 1, 'reconciled', export_equality_digest,
            alias_map_digest, %s, %s, projection_watermark, %s, %s, %s, %s
        FROM migration_import_run_facts WHERE run_id = %s
        ORDER BY fact_sequence DESC LIMIT 1
        """,
        (
            _uuid7(now),
            _digest_bytes(semantic_digest),
            position,
            event_id,
            actor.principal_id,
            command_id,
            now,
            run_id,
        ),
    )


def _revoke_importer(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run_id: UUID,
    command_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_importer_credential_facts (
            credential_fact_id, run_id, principal_id, fact_sequence, lifecycle,
            actor_principal_id, command_id, recorded_at
        ) SELECT %s, binding.run_id, binding.principal_id,
            lifecycle.fact_sequence + 1, 'revoked', %s, %s, %s
        FROM migration_importer_bindings AS binding
        JOIN LATERAL (
            SELECT max(fact_sequence) AS fact_sequence
            FROM migration_importer_credential_facts
            WHERE run_id = binding.run_id
        ) AS lifecycle ON true
        WHERE binding.run_id = %s
        """,
        (_uuid7(now), actor.principal_id, command_id, now, run_id),
    )


def _scope(run: CtowerProjectImportRun, request: CtowerProjectImportFinalizeRequest) -> bool:
    return (
        run.state == "pass_two_noop"
        and run.cutover_id == request.cutover_id
        and run.semantic_digest == request.expected_run_semantic_digest
    )


def _replay(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
) -> CtowerProjectReconciliationResult | RecordProblem | None:
    row = connection.execute(
        """
        SELECT request_sha256, response_body FROM command_results
        WHERE principal_id = %s AND client_command_id = %s
        """,
        (actor.principal_id, command_id),
    ).fetchone()
    if row is None:
        return None
    if bytes(cast(bytes, row["request_sha256"])) != request_digest:
        return _problem(command_id, "migration-operation-drift")
    try:
        return CtowerProjectReconciliationResult.model_validate_json(
            json.dumps(row["response_body"])
        )
    except ValidationError:
        return _problem(command_id, "migration-operation-drift")


def _report_digest(
    request_digest: bytes,
    semantic_digest: str,
    dispositions: MigrationDispositions,
) -> str:
    body = json.dumps(dispositions.model_dump(), separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(request_digest + semantic_digest.encode() + body).hexdigest()}"


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _problem(command_id: UUID, code: str) -> RecordProblem:
    return RecordProblem(
        code,
        "Import run finalization refused",
        409,
        "Finalization refused",
        command_id,
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
