"""Append-only PostgreSQL authority for terminal fleet-beat retirement."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.routine_events import RoutineRetiredPayload
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.runtime.retirement import (
    BeatRoutineRetireCommand,
    BeatRoutineRetirementReceipt,
)

__all__: tuple[str, ...] = ()


def retire_beat_routine(
    dsn: str,
    actor: Actor,
    command: BeatRoutineRetireCommand,
) -> BeatRoutineRetirementReceipt | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        tenant = connection.execute(
            "SELECT tenant_id FROM tenants WHERE tenant_id = %s FOR UPDATE",
            (actor.tenant_id,),
        ).fetchone()
        if tenant is None:
            return _forbidden(command)
        authority_problem = _authority_problem(connection, actor, command)
        if authority_problem is not None:
            return authority_problem
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
            return _receipt(existing)
        problem = _target_problem(connection, actor, command)
        if problem is not None:
            transaction.refuse(
                actor.tenant_id,
                actor.principal_id,
                command.client_command_id,
                request_digest,
                problem,
                now=now,
            )
            return problem
        target = _active_target(connection, actor.tenant_id, command.routine_ref)
        if target is None:
            raise RuntimeError("beat retirement target disappeared after its refusal check")
        return _commit_retirement(
            connection,
            transaction,
            actor,
            command,
            target,
            request_digest,
            now,
        )


def _authority_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: BeatRoutineRetireCommand,
) -> RecordProblem | None:
    principal = connection.execute(
        """
        SELECT kind, disabled FROM principals
        WHERE tenant_id = %s AND principal_id = %s
        FOR SHARE
        """,
        (actor.tenant_id, actor.principal_id),
    ).fetchone()
    if principal is None or principal["kind"] != "operator" or bool(principal["disabled"]):
        return _forbidden(command)
    return None


def _target_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: BeatRoutineRetireCommand,
) -> RecordProblem | None:
    retired = connection.execute(
        """
        SELECT 1 FROM routine_retirements
        WHERE tenant_id = %s AND routine_ref = %s
        """,
        (actor.tenant_id, command.routine_ref),
    ).fetchone()
    if retired is not None:
        return _problem(
            command,
            "beat-routine-already-retired",
            "Beat Routine is already retired",
            409,
        )
    if _active_target(connection, actor.tenant_id, command.routine_ref) is None:
        return _problem(
            command,
            "beat-routine-not-found",
            "Beat Routine was not found",
            404,
        )
    return None


def _forbidden(command: BeatRoutineRetireCommand) -> RecordProblem:
    return _problem(
        command,
        "beat-routine-retire-forbidden",
        "Beat Routine retirement requires an active operator",
        403,
    )


def _active_target(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    routine_ref: str,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT trigger.revision_digest
        FROM routine_triggers AS trigger
        JOIN routine_revisions AS revision
          ON revision.revision_digest = trigger.revision_digest
        JOIN routine_beat_dispatch_specs AS beat
          ON beat.revision_digest = revision.revision_digest
        WHERE trigger.tenant_id = %s AND revision.routine_ref = %s
        FOR UPDATE OF trigger
        """,
        (tenant_id, routine_ref),
    ).fetchone()


def _commit_retirement(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: BeatRoutineRetireCommand,
    target: dict[str, object],
    request_digest: bytes,
    now: datetime,
) -> BeatRoutineRetirementReceipt:
    revision_bytes = bytes(cast(bytes, target["revision_digest"]))
    revision_digest = f"sha256:{revision_bytes.hex()}"
    retirement_id = _uuid7(now)
    event_id = _uuid7(now)
    receipt = BeatRoutineRetirementReceipt(
        command.client_command_id,
        retirement_id,
        event_id,
        command.routine_ref,
        revision_digest,
        now,
    )
    event = _retirement_event(actor, command, receipt, request_digest, now)
    transaction.commit_control(
        event,
        outbox_id=_uuid7(now),
        response_body=receipt.response_payload(),
        status_code=202,
        now=now,
        topic="runtime.routine-retirements",
    )
    connection.execute(
        """
        INSERT INTO routine_retirements (
            retirement_id, tenant_id, routine_ref, revision_digest,
            actor_principal_id, client_command_id, event_id, retired_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            retirement_id,
            actor.tenant_id,
            command.routine_ref,
            revision_bytes,
            actor.principal_id,
            command.client_command_id,
            event_id,
            now,
        ),
    )
    deleted = connection.execute(
        """
        DELETE FROM routine_triggers
        WHERE tenant_id = %s AND revision_digest = %s
        """,
        (actor.tenant_id, revision_bytes),
    )
    if deleted.rowcount != 1:
        raise RuntimeError("beat retirement lost its locked active trigger")
    return receipt


def _retirement_event(
    actor: Actor,
    command: BeatRoutineRetireCommand,
    receipt: BeatRoutineRetirementReceipt,
    request_digest: bytes,
    now: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=receipt.retirement_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=command.client_command_id,
        event_id=receipt.event_id,
        kind=EventKind.ROUTINE_RETIRED,
        origin=EventOrigin.API,
        payload=RoutineRetiredPayload(
            receipt.retirement_id,
            command.routine_ref,
            receipt.revision_digest,
            now,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"routine-retirement:{receipt.retirement_id}",
        tenant_id=actor.tenant_id,
    )


def _receipt(payload: dict[str, object]) -> BeatRoutineRetirementReceipt:
    return BeatRoutineRetirementReceipt(
        command_id=UUID(str(payload["command_id"])),
        retirement_id=UUID(str(payload["retirement_id"])),
        event_id=UUID(str(payload["event_id"])),
        routine_ref=str(payload["routine_ref"]),
        revision_digest=str(payload["revision_digest"]),
        retired_at=datetime.fromisoformat(str(payload["retired_at"])),
    )


def _problem(
    command: BeatRoutineRetireCommand,
    code: str,
    title: str,
    status: int,
) -> RecordProblem:
    return RecordProblem(code, title, status, title, command.client_command_id)


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = connection.execute("SELECT transaction_timestamp() AS value").fetchone()
    return cast(datetime, cast(dict[str, object], row)["value"])


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= secrets.randbits(12) << 64
    value |= 0b10 << 62
    value |= secrets.randbits(62)
    return UUID(int=value)
