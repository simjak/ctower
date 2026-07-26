"""Append-only stale-safe alias, source-link, and relation corrections."""

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
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportRun,
    CtowerProjectMigrationReceipt,
    DurabilityState,
)
from ctower_kernel.migration._correction_revision_sql import (
    append_revision,
    current_revision,
)
from ctower_kernel.migration._event_sql import commit_event, migration_payload
from ctower_kernel.migration._operation_result_sql import canonical, migration_sequence
from ctower_kernel.migration._run_read_sql import load_run
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.transaction import authority_connection, recover_ambiguous_commit
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def append_correction(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectMigrationReceipt | RecordProblem:
    return recover_ambiguous_commit(
        lambda: _append(dsn, actor, request, command_id=command_id, now=now, telemetry=telemetry)
    )


def _append(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectMigrationReceipt | RecordProblem:
    request_digest = hashlib.sha256(canonical(request)).digest()
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        replay = _replay(connection, actor, command_id, request_digest)
        if replay is not None:
            return replay
        run = load_run(connection, actor, request.run_id, lock=True)
        if isinstance(run, RecordProblem) or not _scope(connection, actor, request, run):
            return _problem(command_id, "migration-correction-conflict", "Correction scope refused")
        current = current_revision(connection, request)
        if not _expected_revision(current, request):
            return _problem(command_id, "migration-correction-conflict", "Correction is stale")
        if current is None:
            raise RuntimeError("validated correction revision is unavailable")
        semantic = hashlib.sha256(canonical(request.replacement)).digest()
        next_revision = request.superseded_revision.revision + 1
        if not append_revision(
            connection,
            actor,
            request,
            current,
            semantic=semantic,
            command_id=command_id,
            now=now,
        ):
            return _problem(command_id, "migration-correction-conflict", "Replacement is invalid")
        return _commit_correction(
            connection,
            actor,
            request,
            command_id=command_id,
            request_digest=request_digest,
            semantic=semantic,
            revision=next_revision,
            previous_run_semantic=run.semantic_digest,
            now=now,
            telemetry=telemetry,
        )


def _commit_correction(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    *,
    command_id: UUID,
    request_digest: bytes,
    semantic: bytes,
    revision: int,
    previous_run_semantic: str,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectMigrationReceipt:
    captured: list[CtowerProjectMigrationReceipt] = []
    event_id, position = commit_event(
        connection,
        actor,
        aggregate_id=request.run_id,
        command_id=command_id,
        kind=EventKind.MIGRATION_CHANGED,
        payload=migration_payload(
            "correction_appended",
            run_id=request.run_id,
            cutover_id=request.cutover_id,
            target_id=str(request.superseded_revision.object_id),
        ),
        request_digest=request_digest,
        sequence=migration_sequence(connection, actor, request.run_id),
        stream_id=f"migration:{request.run_id}",
        now=now,
        telemetry=telemetry,
        response=_receipt_response(
            captured,
            request,
            revision=revision,
            command_id=command_id,
            semantic=semantic,
        ),
        subjects=(("migration", request.run_id),),
    )
    _insert_correction_fact(
        connection,
        actor,
        request,
        command_id=command_id,
        event_id=event_id,
        position=position,
        semantic=semantic,
        previous_run_semantic=previous_run_semantic,
        now=now,
    )
    return captured[0]


def _receipt_response(
    captured: list[CtowerProjectMigrationReceipt],
    request: CtowerProjectImportCorrectionRequest,
    *,
    revision: int,
    command_id: UUID,
    semantic: bytes,
) -> Callable[[UUID, int], dict[str, object]]:
    def response(event_id: UUID, position: int) -> dict[str, object]:
        receipt = CtowerProjectMigrationReceipt(
            object_id=request.superseded_revision.object_id,
            revision=revision,
            command_id=command_id,
            event_ids=(event_id,),
            record_position=position,
            semantic_digest=_digest_text(semantic),
            durability_state=DurabilityState.DURABILITY_PENDING,
            accepted_position=None,
        )
        captured.append(receipt)
        return cast(dict[str, object], receipt.model_dump(mode="json"))

    return response


def _insert_correction_fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    *,
    command_id: UUID,
    event_id: UUID,
    position: int,
    semantic: bytes,
    previous_run_semantic: str,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_corrections (
            correction_id, run_id, correction_kind, object_id, superseded_revision,
            expected_current_digest, replacement, reason, reviewer_id, command_id,
            event_id, semantic_digest, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request.correction_id,
            request.run_id,
            request.correction_kind,
            request.superseded_revision.object_id,
            request.superseded_revision.revision,
            _digest_bytes(request.expected_current_digest),
            Jsonb(request.replacement.model_dump(mode="json")),
            request.reason,
            request.reviewer_id,
            command_id,
            event_id,
            semantic,
            now,
        ),
    )
    _insert_run_fact(
        connection,
        actor,
        request,
        command_id=command_id,
        event_id=event_id,
        position=position,
        previous_run_semantic=previous_run_semantic,
        semantic=semantic,
        now=now,
    )


def _insert_run_fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    *,
    command_id: UUID,
    event_id: UUID,
    position: int,
    previous_run_semantic: str,
    semantic: bytes,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_import_run_facts (
            run_fact_id, run_id, fact_sequence, state, export_equality_digest,
            alias_map_digest, semantic_digest, record_watermark, projection_watermark,
            event_id, actor_principal_id, command_id, recorded_at
        ) SELECT %s, run_id, fact_sequence + 1, state, export_equality_digest,
            alias_map_digest, %s, %s, projection_watermark, %s, %s, %s, %s
        FROM migration_import_run_facts WHERE run_id = %s
        ORDER BY fact_sequence DESC LIMIT 1
        """,
        (
            _uuid7(now),
            hashlib.sha256(previous_run_semantic.encode() + semantic).digest(),
            position,
            event_id,
            actor.principal_id,
            command_id,
            now,
            request.run_id,
        ),
    )


def _scope(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    run: CtowerProjectImportRun,
) -> bool:
    if run.cutover_id != request.cutover_id or run.state != "importing":
        return False
    return (
        connection.execute(
            """
        SELECT 1 FROM principals WHERE principal_id = %s AND tenant_id = %s
          AND kind IN ('reviewer', 'operator') AND NOT disabled
        """,
            (request.reviewer_id, actor.tenant_id),
        ).fetchone()
        is not None
    )


def _expected_revision(
    current: dict[str, object] | None,
    request: CtowerProjectImportCorrectionRequest,
) -> bool:
    return (
        current is not None
        and int(cast(int, current["revision"])) == request.superseded_revision.revision
        and _digest_text(current["semantic_digest"]) == request.expected_current_digest
    )


def _replay(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
) -> CtowerProjectMigrationReceipt | RecordProblem | None:
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
        return _problem(command_id, "migration-operation-drift", "Correction replay changed")
    try:
        return CtowerProjectMigrationReceipt.model_validate_json(json.dumps(row["response_body"]))
    except ValidationError:
        return _problem(command_id, "migration-operation-drift", "Command identity was reused")


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _digest_text(value: object) -> str:
    return f"sha256:{bytes(cast(bytes, value)).hex()}"


def _problem(command_id: UUID, code: str, title: str) -> RecordProblem:
    return RecordProblem(code, title, 409, title, command_id)


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
