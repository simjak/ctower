"""Record-backed completion of Routine work items."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
)
from ctower_kernel.record.routine_work_item_events import RoutineWorkItemCompletedPayload
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.runtime._routine_ids import stable_uuid7
from ctower_kernel.runtime.items import (
    CompleteRoutineWorkItemCommand,
    RoutineWorkItemReceipt,
)

__all__: tuple[str, ...] = ()


def complete(
    dsn: str,
    actor: Actor,
    command: CompleteRoutineWorkItemCommand,
) -> RoutineWorkItemReceipt | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        request_digest = hashlib.sha256(_canonical_bytes(command.request_payload())).digest()
        transaction = RecordTransaction(connection)
        existing = _reserved_completion(transaction, actor, command, request_digest)
        if existing is not None:
            return existing
        if not command.artifact_ref:
            return _refuse_completion(
                transaction,
                actor,
                command,
                request_digest,
                "routine-work-item-artifact-required",
                "Routine work-item completion requires an artifact reference",
                400,
                now,
            )
        row = _validated_completion_row(
            connection,
            transaction,
            actor,
            command,
            request_digest,
            now,
        )
        if isinstance(row, RecordProblem):
            return row
        return _commit_completion(
            connection,
            transaction,
            actor,
            command,
            str(row["owner_seat"]),
            request_digest,
            now,
        )


def _validated_completion_row(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: CompleteRoutineWorkItemCommand,
    request_digest: bytes,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    row = _load_work_item(connection, actor.tenant_id, command.work_item_id)
    if row is None:
        return _refuse_completion(
            transaction,
            actor,
            command,
            request_digest,
            "routine-work-item-not-found",
            "Routine work item was not found",
            404,
            now,
        )
    if not _can_complete(connection, actor, row):
        return _refuse_completion(
            transaction,
            actor,
            command,
            request_digest,
            "routine-work-item-forbidden",
            "Routine work-item completion requires its owning seat",
            403,
            now,
        )
    if row["status"] != "open":
        return _refuse_completion(
            transaction,
            actor,
            command,
            request_digest,
            "routine-work-item-already-completed",
            "Routine work item already has a receipt",
            409,
            now,
        )
    return row


def _refuse_completion(
    transaction: RecordTransaction,
    actor: Actor,
    command: CompleteRoutineWorkItemCommand,
    request_digest: bytes,
    code: str,
    detail: str,
    status: int,
    now: datetime,
) -> RecordProblem:
    problem = _problem(command, code, detail, status)
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _reserved_completion(
    transaction: RecordTransaction,
    actor: Actor,
    command: CompleteRoutineWorkItemCommand,
    request_digest: bytes,
) -> RoutineWorkItemReceipt | RecordProblem | None:
    existing = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
    if isinstance(existing, RecordProblem):
        return existing
    if existing is not None:
        return _receipt_from_response(existing)
    return None


def _load_work_item(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    work_item_id: UUID,
) -> dict[str, object] | None:
    row = connection.execute(
        """
        SELECT work_item_id, routine_ref, owner_seat, status
        FROM inbox_work_items
        WHERE tenant_id = %s AND work_item_id = %s
        FOR UPDATE
        """,
        (tenant_id, work_item_id),
    ).fetchone()
    return row


def _can_complete(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    row: dict[str, object],
) -> bool:
    if actor.kind not in {PrincipalKind.COMMANDER, PrincipalKind.OPERATOR}:
        return False
    owner = connection.execute(
        """
        SELECT 1 FROM project_seats
        WHERE tenant_id = %s AND principal_id = %s AND seat_key = %s
        """,
        (actor.tenant_id, actor.principal_id, row["owner_seat"]),
    ).fetchone()
    return actor.kind is PrincipalKind.OPERATOR or owner is not None


def _commit_completion(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: CompleteRoutineWorkItemCommand,
    owner_seat: str,
    request_digest: bytes,
    now: datetime,
) -> RoutineWorkItemReceipt:
    receipt_id, event_id, outbox_id = _completion_ids(now, command.work_item_id)
    previous = _previous_event(connection, actor.tenant_id, command.work_item_id)
    if previous is None:
        raise RuntimeError("Routine work-item append event is unavailable")
    receipt = RoutineWorkItemReceipt(
        receipt_id=receipt_id,
        work_item_id=command.work_item_id,
        owner_seat=owner_seat,
        artifact_ref=command.artifact_ref,
        delivered_at=now,
        command_id=command.client_command_id,
        event_id=event_id,
    )
    event = _completion_event(
        actor,
        command,
        owner_seat,
        receipt_id,
        event_id,
        request_digest,
        now,
        previous,
    )
    transaction.commit_control(
        event,
        outbox_id=outbox_id,
        response_body=receipt.response_payload(),
        status_code=202,
        now=now,
        topic="runtime.routine-work-item-receipts",
    )
    _insert_receipt(connection, actor, command, owner_seat, receipt_id, event_id, now)
    _close_work_item(connection, actor.tenant_id, command, receipt_id)
    return receipt


def _completion_ids(now: datetime, work_item_id: UUID) -> tuple[UUID, UUID, UUID]:
    receipt_id = stable_uuid7(now, b"routine-work-item-receipt", work_item_id.bytes)
    event_id = stable_uuid7(now, b"routine-work-item-completion-event", receipt_id.bytes)
    outbox_id = stable_uuid7(now, b"routine-work-item-completion-outbox", receipt_id.bytes)
    return receipt_id, event_id, outbox_id


def _previous_event(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    work_item_id: UUID,
) -> dict[str, object] | None:
    row = connection.execute(
        """
        SELECT sequence, event_hash FROM events
        WHERE tenant_id = %s AND stream_id = %s
        ORDER BY sequence DESC
        LIMIT 1
        """,
        (tenant_id, f"routine-work-item:{work_item_id}"),
    ).fetchone()
    return row


def _completion_event(
    actor: Actor,
    command: CompleteRoutineWorkItemCommand,
    owner_seat: str,
    receipt_id: UUID,
    event_id: UUID,
    request_digest: bytes,
    now: datetime,
    previous: dict[str, object],
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=command.work_item_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=command.client_command_id,
        event_id=event_id,
        kind=EventKind.ROUTINE_WORK_ITEM_COMPLETED,
        origin=EventOrigin.API,
        payload=RoutineWorkItemCompletedPayload(
            work_item_id=command.work_item_id,
            receipt_id=receipt_id,
            owner_seat=owner_seat,
            artifact_ref=command.artifact_ref,
            delivered_at=now,
        ),
        prev_hash=cast(bytes, previous["event_hash"]),
        request_sha256=request_digest,
        sequence=int(cast(int, previous["sequence"])) + 1,
        server_time=now,
        stream_id=f"routine-work-item:{command.work_item_id}",
        tenant_id=actor.tenant_id,
    )


def _insert_receipt(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompleteRoutineWorkItemCommand,
    owner_seat: str,
    receipt_id: UUID,
    event_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO routine_work_item_receipts (
            receipt_id, work_item_id, tenant_id, owner_seat, artifact_ref,
            delivered_at, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            receipt_id,
            command.work_item_id,
            actor.tenant_id,
            owner_seat,
            command.artifact_ref,
            now,
            event_id,
        ),
    )


def _close_work_item(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    command: CompleteRoutineWorkItemCommand,
    receipt_id: UUID,
) -> None:
    connection.execute(
        """
        UPDATE inbox_work_items
        SET status = 'closed', receipt_id = %s, receipt_artifact_ref = %s
        WHERE tenant_id = %s AND work_item_id = %s AND status = 'open'
        """,
        (receipt_id, command.artifact_ref, tenant_id, command.work_item_id),
    )


def _receipt_from_response(response: dict[str, object]) -> RoutineWorkItemReceipt:
    return RoutineWorkItemReceipt(
        receipt_id=UUID(str(response["receipt_id"])),
        work_item_id=UUID(str(response["work_item_id"])),
        owner_seat=str(response.get("owner_seat", "ctower-commander")),
        artifact_ref=str(response["artifact_ref"]),
        delivered_at=datetime.fromisoformat(str(response["delivered_at"])),
        command_id=UUID(str(response["command_id"])) if response.get("command_id") else None,
        event_id=UUID(str(response["event_id"])) if response.get("event_id") else None,
    )


def _problem(
    command: CompleteRoutineWorkItemCommand, code: str, detail: str, status: int
) -> RecordProblem:
    return RecordProblem(code, detail, status, detail, command.client_command_id)


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = connection.execute("SELECT transaction_timestamp() AS value").fetchone()
    return cast(datetime, cast(dict[str, object], row)["value"])


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
