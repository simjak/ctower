"""Canonical Record command persistence for poison dispositions."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.attention import (
    PoisonDisposition,
    PoisonDispositionReceipt,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    PoisonDispositionRecordedPayload,
)
from ctower_kernel.record.transaction import RecordTransaction, authority_connection

__all__: tuple[str, ...] = ()


def disposition(
    dsn: str, actor: Actor, command: PoisonDisposition
) -> PoisonDispositionReceipt | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        request_digest = hashlib.sha256(_canonical_bytes(command.request_payload())).digest()
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id,
            command.client_command_id,
            request_digest,
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _receipt_from_payload(actor, command, existing)
        if not _target_exists(connection, actor.tenant_id, command):
            return _refuse_missing(transaction, actor, command, request_digest, now)
        return _record_disposition(connection, transaction, actor, command, request_digest, now)


def _target_exists(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    command: PoisonDisposition,
) -> bool:
    target = connection.execute(
        """
        SELECT 1 FROM outbox_poison
        WHERE consumer_key = %s AND tenant_id = %s AND topic = %s AND outbox_id = %s
        """,
        (command.consumer_key, tenant_id, command.topic, command.outbox_id),
    ).fetchone()
    return target is not None


def _refuse_missing(
    transaction: RecordTransaction,
    actor: Actor,
    command: PoisonDisposition,
    request_digest: bytes,
    now: datetime,
) -> RecordProblem:
    problem = RecordProblem(
        code="poison-not-found",
        detail="The tenant-scoped poison disposition target does not exist.",
        status=404,
        title="Poison target not found",
        command_id=command.client_command_id,
    )
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _record_disposition(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: PoisonDisposition,
    request_digest: bytes,
    now: datetime,
) -> PoisonDispositionReceipt:
    event_id = _uuid7(now)
    receipt = PoisonDispositionReceipt(
        actor.tenant_id, actor.principal_id, command, now, (event_id,)
    )
    event = _disposition_event(actor, command, request_digest, event_id, now)
    transaction.commit_control(
        event,
        outbox_id=_uuid7(now),
        response_body=receipt.response_payload(),
        status_code=202,
        now=now,
        topic="attention.dispositions",
    )
    _insert_disposition(connection, actor, command, event_id, now)
    return receipt


def _disposition_event(
    actor: Actor,
    command: PoisonDisposition,
    request_digest: bytes,
    event_id: UUID,
    now: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=command.client_command_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=command.client_command_id,
        event_id=event_id,
        kind=EventKind.POISON_DISPOSITION_RECORDED,
        origin=EventOrigin.API,
        payload=PoisonDispositionRecordedPayload(
            outbox_id=command.outbox_id,
            consumer_key=command.consumer_key,
            topic=command.topic,
            action=command.action.value,
            reason=command.reason,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"poison-disposition:{command.client_command_id}",
        tenant_id=actor.tenant_id,
    )


def _insert_disposition(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: PoisonDisposition,
    event_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO outbox_poison_dispositions (
            tenant_id, actor_principal_id, client_command_id, event_id,
            consumer_key, topic, outbox_id, action, reason, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            event_id,
            command.consumer_key,
            command.topic,
            command.outbox_id,
            command.action.value,
            command.reason,
            now,
        ),
    )


def _receipt_from_payload(
    actor: Actor,
    command: PoisonDisposition,
    payload: dict[str, object],
) -> PoisonDispositionReceipt:
    event_ids = tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"]))
    return PoisonDispositionReceipt(
        actor.tenant_id,
        actor.principal_id,
        command,
        datetime.fromisoformat(str(payload["recorded_at"])),
        event_ids,
    )


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = cast(
        dict[str, object],
        connection.execute("SELECT transaction_timestamp() AS value").fetchone(),
    )
    return cast(datetime, row["value"])


def _uuid7(now: datetime | None = None) -> UUID:
    instant = now or datetime.now(UTC)
    milliseconds = int(instant.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
