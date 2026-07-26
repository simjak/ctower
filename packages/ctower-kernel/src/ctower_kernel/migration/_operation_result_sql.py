"""Exact operation result, event, and replay receipt persistence."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
import rfc8785
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from ctower_client.models import (
    CtowerProjectExactAliasOperation,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportOperation,
    CtowerProjectSourceLinkOperation,
    CtowerProjectTicketSeedOperation,
    MigrationImportOperationResult,
)
from ctower_kernel.migration._event_sql import commit_event, migration_payload
from ctower_kernel.record import Actor
from ctower_kernel.record.events import (
    EventKind,
    MigrationChangedPayload,
    TicketCreatedPayload,
    WorkChangedPayload,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
type OperationPayload = MigrationChangedPayload | TicketCreatedPayload | WorkChangedPayload
type SourceOperation = (
    CtowerProjectTicketSeedOperation
    | CtowerProjectExactAliasOperation
    | CtowerProjectSourceLinkOperation
)


def commit_migration_result(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectImportOperation,
    *,
    target_id: str,
    now: datetime,
    telemetry: TelemetryContext,
) -> MigrationImportOperationResult:
    return commit_result(
        connection,
        actor,
        batch,
        operation,
        target_id=target_id,
        kind=EventKind.MIGRATION_CHANGED,
        payload=migration_payload(
            operation.operation,
            run_id=batch.run_id,
            cutover_id=batch.cutover_id,
            target_id=target_id,
        ),
        aggregate_id=batch.run_id,
        sequence=migration_sequence(connection, actor, batch.run_id),
        stream_id=f"migration:{batch.run_id}",
        now=now,
        telemetry=telemetry,
        subjects=(("migration", batch.run_id),),
    )


def commit_result(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectImportOperation,
    *,
    target_id: str,
    kind: EventKind,
    payload: OperationPayload,
    aggregate_id: UUID,
    sequence: int,
    stream_id: str,
    now: datetime,
    telemetry: TelemetryContext,
    subjects: tuple[tuple[str, UUID], ...],
) -> MigrationImportOperationResult:
    digest = hashlib.sha256(canonical(operation)).digest()
    captured: list[MigrationImportOperationResult] = []

    def response(event_id: UUID, position: int) -> dict[str, object]:
        result = MigrationImportOperationResult(
            command_id=operation.identity.command_id,
            operation_kind=operation.operation,
            replayed=False,
            target_id=target_id,
            event_ids=(event_id,),
            record_position=position,
            occurred_at=now,
        )
        captured.append(result)
        return cast(dict[str, object], result.model_dump(mode="json"))

    commit_event(
        connection,
        actor,
        aggregate_id=aggregate_id,
        command_id=operation.identity.command_id,
        kind=kind,
        payload=payload,
        request_digest=digest,
        sequence=sequence,
        stream_id=stream_id,
        now=now,
        telemetry=telemetry,
        response=response,
        subjects=subjects,
    )
    result = captured[0]
    _insert_result(
        connection,
        batch,
        operation,
        digest=digest,
        result=result,
        target_id=target_id,
        now=now,
    )
    return result


def _insert_result(
    connection: psycopg.Connection[dict[str, object]],
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectImportOperation,
    *,
    digest: bytes,
    result: MigrationImportOperationResult,
    target_id: str,
    now: datetime,
) -> None:
    identity = operation.identity
    connection.execute(
        """
        INSERT INTO migration_import_operation_results (
            run_id, command_id, namespace, immutable_source_id,
            source_version_or_digest, operation_kind, planned_target_ref,
            request_digest, target_id, event_ids, record_position,
            response_body, occurred_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            batch.run_id,
            identity.command_id,
            identity.namespace,
            identity.immutable_source_id,
            identity.source_version_or_digest,
            identity.operation_kind,
            identity.planned_target_ref,
            digest,
            target_id,
            list(result.event_ids),
            result.record_position,
            Jsonb(result.model_dump(mode="json")),
            now,
        ),
    )


def source_matches(operation: SourceOperation) -> bool:
    identity = operation.identity
    source = operation.source
    return (
        identity.namespace == source.namespace
        and identity.immutable_source_id == source.immutable_source_id
        and identity.source_version_or_digest in {source.source_version, source.source_digest}
    )


def canonical(model: BaseModel) -> bytes:
    try:
        return rfc8785.dumps(model.model_dump(mode="json", by_alias=True))
    except (rfc8785.CanonicalizationError, UnicodeError, ValueError) as error:
        raise ValueError("migration payload is outside the RFC 8785 JSON domain") from error


def migration_sequence(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, run_id: UUID
) -> int:
    row = connection.execute(
        """
        SELECT coalesce(max(sequence), 0) + 1 AS sequence FROM events
        WHERE tenant_id = %s AND stream_id = %s
        """,
        (actor.tenant_id, f"migration:{run_id}"),
    ).fetchone()
    if row is None:
        raise RuntimeError("migration event sequence is unavailable")
    return int(cast(int, row["sequence"]))
