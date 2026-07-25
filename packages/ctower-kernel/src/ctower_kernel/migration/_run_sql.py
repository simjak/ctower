"""Import-run identity, digest binding, lifecycle facts, and exact reads."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from pydantic import BaseModel

from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectImportRun,
    CtowerProjectImportRunCreateRequest,
    MigrationPinnedDigests,
)
from ctower_kernel.migration._credential_sql import create_binding
from ctower_kernel.migration._event_sql import commit_event, migration_payload
from ctower_kernel.migration._operation_result_sql import canonical
from ctower_kernel.migration._run_read_sql import (
    ctower_scope_available,
    initial_model,
    load_run,
    replay_run,
    valid_alias,
    valid_export,
)
from ctower_kernel.migration._run_read_sql import get_run as _get_run
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.transaction import authority_connection, recover_ambiguous_commit
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def create_run(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportRunCreateRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportRun | RecordProblem:
    return recover_ambiguous_commit(
        lambda: _create(dsn, actor, request, command_id=command_id, now=now, telemetry=telemetry)
    )


def _create(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportRunCreateRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportRun | RecordProblem:
    digest = _request_digest(request)
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        replay = replay_run(connection, actor, command_id, digest)
        if replay is not None:
            return replay
        if request.importer_expires_at <= now or not ctower_scope_available(
            connection, actor, request.cutover_id
        ):
            return _problem(command_id, "migration-run-conflict", "Import scope is unavailable")
        run_id, principal_id = _uuid7(now), _uuid7(now)
        _insert_run(
            connection,
            actor,
            request,
            run_id=run_id,
            principal_id=principal_id,
            command_id=command_id,
            now=now,
        )
        current = initial_model(
            request,
            run_id,
            semantic_digest=_semantic(request.source_selection_digest, b"", "created"),
        )
        return _append_state(
            connection,
            actor,
            current,
            command_id=command_id,
            request_digest=digest,
            state="created",
            operation="run_created",
            export_digest=None,
            alias_digest=None,
            now=now,
            telemetry=telemetry,
        )


def bind_export_equality(
    dsn: str,
    actor: Actor,
    request: CtowerProjectExportEqualityBindRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportRun | RecordProblem:
    return recover_ambiguous_commit(
        lambda: _bind_export(
            dsn, actor, request, command_id=command_id, now=now, telemetry=telemetry
        )
    )


def _bind_export(
    dsn: str,
    actor: Actor,
    request: CtowerProjectExportEqualityBindRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportRun | RecordProblem:
    digest = _request_digest(request)
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        replay = replay_run(connection, actor, command_id, digest)
        if replay is not None:
            return replay
        current = load_run(connection, actor, request.run_id, lock=True)
        if isinstance(current, RecordProblem) or not valid_export(current, request):
            return _problem(command_id, "migration-digest-mismatch", "Export binding refused")
        return _append_state(
            connection,
            actor,
            current,
            command_id=command_id,
            request_digest=digest,
            state="export_equality_bound",
            operation="export_equality_bound",
            export_digest=request.equality_report_digest,
            alias_digest=None,
            now=now,
            telemetry=telemetry,
        )


def bind_alias_plan(
    dsn: str,
    actor: Actor,
    request: CtowerProjectAliasPlanBindRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportRun | RecordProblem:
    return recover_ambiguous_commit(
        lambda: _bind_alias(
            dsn, actor, request, command_id=command_id, now=now, telemetry=telemetry
        )
    )


def _bind_alias(
    dsn: str,
    actor: Actor,
    request: CtowerProjectAliasPlanBindRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportRun | RecordProblem:
    digest = _request_digest(request)
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        replay = replay_run(connection, actor, command_id, digest)
        if replay is not None:
            return replay
        current = load_run(connection, actor, request.run_id, lock=True)
        if isinstance(current, RecordProblem) or not valid_alias(current, request):
            return _problem(command_id, "migration-digest-mismatch", "Alias binding refused")
        return _append_state(
            connection,
            actor,
            current,
            command_id=command_id,
            request_digest=digest,
            state="alias_plan_bound",
            operation="alias_plan_bound",
            export_digest=current.pinned_digests.export_equality,
            alias_digest=request.alias_map_digest,
            now=now,
            telemetry=telemetry,
        )


def get_run(dsn: str, actor: Actor, run_id: UUID) -> CtowerProjectImportRun | RecordProblem:
    return _get_run(dsn, actor, run_id)


def _append_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    current: CtowerProjectImportRun,
    *,
    command_id: UUID,
    request_digest: bytes,
    state: str,
    operation: str,
    export_digest: str | None,
    alias_digest: str | None,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectImportRun:
    sequence = _next_fact_sequence(connection, current.run_id)
    semantic = _semantic(current.semantic_digest, request_digest, state)
    pinned = current.pinned_digests.model_copy(
        update={"export_equality": export_digest, "alias_map": alias_digest}
    )
    event_id, position, updated = _commit_state_event(
        connection,
        actor,
        current,
        pinned,
        command_id=command_id,
        request_digest=request_digest,
        state=state,
        operation=operation,
        semantic=semantic,
        sequence=sequence,
        now=now,
        telemetry=telemetry,
    )
    _insert_state_fact(
        connection,
        actor,
        current,
        command_id=command_id,
        event_id=event_id,
        position=position,
        sequence=sequence,
        state=state,
        semantic=semantic,
        export_digest=export_digest,
        alias_digest=alias_digest,
        now=now,
    )
    return updated


def _commit_state_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    current: CtowerProjectImportRun,
    pinned: MigrationPinnedDigests,
    *,
    command_id: UUID,
    request_digest: bytes,
    state: str,
    operation: str,
    semantic: str,
    sequence: int,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[UUID, int, CtowerProjectImportRun]:
    captured: list[CtowerProjectImportRun] = []

    def response(_event_id: UUID, position: int) -> dict[str, object]:
        updated = current.model_copy(
            update={
                "state": state,
                "pinned_digests": pinned,
                "semantic_digest": semantic,
                "record_watermark": position,
            }
        )
        captured.append(updated)
        return cast(dict[str, object], updated.model_dump(mode="json", by_alias=True))

    event_id, position = commit_event(
        connection,
        actor,
        aggregate_id=current.run_id,
        command_id=command_id,
        kind=EventKind.MIGRATION_CHANGED,
        payload=migration_payload(
            operation,
            run_id=current.run_id,
            cutover_id=current.cutover_id,
            target_id=str(current.run_id),
        ),
        request_digest=request_digest,
        sequence=sequence,
        stream_id=f"migration:{current.run_id}",
        now=now,
        telemetry=telemetry,
        response=response,
        subjects=(("migration", current.run_id),),
    )
    return event_id, position, captured[0]


def _insert_state_fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    current: CtowerProjectImportRun,
    *,
    command_id: UUID,
    event_id: UUID,
    position: int,
    sequence: int,
    state: str,
    semantic: str,
    export_digest: str | None,
    alias_digest: str | None,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_import_run_facts (
            run_fact_id, run_id, fact_sequence, state, export_equality_digest,
            alias_map_digest, semantic_digest, record_watermark, projection_watermark,
            event_id, actor_principal_id, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            _uuid7(now),
            current.run_id,
            sequence,
            state,
            _digest_bytes(export_digest),
            _digest_bytes(alias_digest),
            _digest_bytes(semantic),
            position,
            current.projection_watermark,
            event_id,
            actor.principal_id,
            command_id,
            now,
        ),
    )


def _insert_run(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportRunCreateRequest,
    *,
    run_id: UUID,
    principal_id: UUID,
    command_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_import_runs (
            run_id, tenant_id, cutover_id, tenant_key, project_key,
            source_selection_digest, build_digest, client_digest, schema_digest,
            operation_registry_digest, reviewer_public_key_digest, created_by, created_at
        ) VALUES (%s, %s, %s, 'ctower', 'ctower', %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            actor.tenant_id,
            request.cutover_id,
            _digest_bytes(request.source_selection_digest),
            _digest_bytes(request.build_digest),
            _digest_bytes(request.client_digest),
            _digest_bytes(request.schema_digest),
            _digest_bytes(request.operation_registry_digest),
            _digest_bytes(request.reviewer_public_key_digest),
            actor.principal_id,
            now,
        ),
    )
    create_binding(
        connection,
        actor,
        request,
        run_id=run_id,
        principal_id=principal_id,
        command_id=command_id,
        now=now,
    )


def _next_fact_sequence(connection: psycopg.Connection[dict[str, object]], run_id: UUID) -> int:
    row = connection.execute(
        """
        SELECT coalesce(max(fact_sequence), 0) + 1 AS sequence
        FROM migration_import_run_facts WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("run fact sequence is unavailable")
    return int(cast(int, row["sequence"]))


def _request_digest(request: BaseModel) -> bytes:
    return hashlib.sha256(canonical(request)).digest()


def _semantic(previous: str, digest: bytes, state: str) -> str:
    material = previous.encode() + digest + state.encode()
    return f"sha256:{hashlib.sha256(material).hexdigest()}"


def _digest_bytes(value: str | None) -> bytes | None:
    return bytes.fromhex(value.removeprefix("sha256:")) if value is not None else None


def _problem(command_id: UUID | None, code: str, title: str, *, status: int = 409) -> RecordProblem:
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
