"""Append-only PostgreSQL authority for fleet-beat retirement."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.routine_events import RoutineRetiredPayload
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.runtime._routine_ids import stable_uuid7
from ctower_kernel.runtime.retirement import (
    BeatRoutineRetireCommand,
    BeatRoutineRetirementReceipt,
)

__all__: tuple[str, ...] = ()


def retire(
    dsn: str,
    actor: Actor,
    command: BeatRoutineRetireCommand,
) -> BeatRoutineRetirementReceipt | RecordProblem:
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
            return _receipt(existing)
        lock_tenant(connection, actor.tenant_id)
        problem = _authorization_problem(connection, actor, command)
        if problem is not None:
            return _refuse(transaction, actor, command, request_digest, problem, now)
        target = _active_target(connection, actor.tenant_id, command.routine_ref)
        if target is None:
            problem = _unavailable_problem(connection, actor.tenant_id, command)
            return _refuse(transaction, actor, command, request_digest, problem, now)
        return _commit_retirement(
            connection,
            transaction,
            actor,
            command,
            target,
            request_digest,
            now,
        )


def fully_retired_routine_refs(dsn: str) -> tuple[str, ...]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        rows = connection.execute(
            """
            SELECT retirement.routine_ref
            FROM routine_retirements AS retirement
            GROUP BY retirement.routine_ref
            HAVING count(DISTINCT retirement.tenant_id) = (SELECT count(*) FROM tenants)
            ORDER BY retirement.routine_ref
            """
        ).fetchall()
    return tuple(str(row["routine_ref"]) for row in rows)


def activate_trigger_unless_retired(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    routine_ref: str,
    revision_digest: bytes,
    initial_fire: datetime,
) -> None:
    retired = connection.execute(
        "SELECT 1 FROM routine_retirements WHERE tenant_id = %s AND routine_ref = %s",
        (tenant_id, routine_ref),
    ).fetchone()
    if retired is not None:
        connection.execute(
            """
            DELETE FROM routine_triggers AS trigger
            USING routine_revisions AS registered
            WHERE trigger.tenant_id = %s
              AND trigger.revision_digest = registered.revision_digest
              AND registered.routine_ref = %s
            """,
            (tenant_id, routine_ref),
        )
        return
    connection.execute(
        """
        DELETE FROM routine_triggers AS trigger
        USING routine_revisions AS registered
        WHERE trigger.tenant_id = %s
          AND trigger.revision_digest = registered.revision_digest
          AND registered.routine_ref = %s
          AND registered.revision_digest <> %s
        """,
        (tenant_id, routine_ref, revision_digest),
    )
    connection.execute(
        """
        INSERT INTO routine_triggers (
            tenant_id, revision_digest, next_fire_at, updated_at
        ) VALUES (%s, %s, %s, transaction_timestamp())
        ON CONFLICT (tenant_id, revision_digest) DO NOTHING
        """,
        (tenant_id, revision_digest, initial_fire),
    )


def lock_tenant(connection: psycopg.Connection[dict[str, object]], tenant_id: UUID) -> None:
    row = connection.execute(
        "SELECT tenant_id FROM tenants WHERE tenant_id = %s FOR UPDATE",
        (tenant_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Routine tenant does not exist")


def _authorization_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: BeatRoutineRetireCommand,
) -> RecordProblem | None:
    principal = connection.execute(
        """
        SELECT 1 FROM principals
        WHERE tenant_id = %s AND principal_id = %s
          AND kind IN ('operator', 'commander') AND NOT disabled
        """,
        (actor.tenant_id, actor.principal_id),
    ).fetchone()
    if principal is not None:
        return None
    return RecordProblem(
        "beat-routine-retire-forbidden",
        "Only an active operator or Commander may retire a fleet-beat routine.",
        403,
        "Beat routine retirement forbidden",
        command.client_command_id,
    )


def _active_target(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    routine_ref: str,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT revision.revision_digest
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


def _unavailable_problem(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    command: BeatRoutineRetireCommand,
) -> RecordProblem:
    retired = connection.execute(
        """
        SELECT 1 FROM routine_retirements
        WHERE tenant_id = %s AND routine_ref = %s
        """,
        (tenant_id, command.routine_ref),
    ).fetchone()
    if retired is not None:
        return RecordProblem(
            "beat-routine-already-retired",
            "The tenant-scoped fleet-beat routine is already retired.",
            409,
            "Beat routine already retired",
            command.client_command_id,
        )
    return RecordProblem(
        "beat-routine-not-found",
        "The tenant-scoped fleet-beat routine is unavailable.",
        404,
        "Beat routine unavailable",
        command.client_command_id,
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: BeatRoutineRetireCommand,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _commit_retirement(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: BeatRoutineRetireCommand,
    target: dict[str, object],
    request_digest: bytes,
    now: datetime,
) -> BeatRoutineRetirementReceipt:
    identity = (actor.tenant_id.bytes, command.client_command_id.bytes)
    retirement_id = stable_uuid7(now, b"routine-retirement", *identity)
    event_id = stable_uuid7(now, b"routine-retirement-event", *identity)
    revision_digest = _digest(cast(bytes, target["revision_digest"]))
    receipt = BeatRoutineRetirementReceipt(
        command.client_command_id,
        event_id,
        retirement_id,
        command.routine_ref,
        revision_digest,
        now,
    )
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=retirement_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=command.client_command_id,
        event_id=event_id,
        kind=EventKind.ROUTINE_RETIRED,
        origin=EventOrigin.API,
        payload=RoutineRetiredPayload(retirement_id, command.routine_ref, revision_digest),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"routine-retirement:{retirement_id}",
        tenant_id=actor.tenant_id,
    )
    transaction.commit_control(
        event,
        outbox_id=stable_uuid7(now, b"routine-retirement-outbox", *identity),
        response_body=receipt.response_payload(),
        status_code=202,
        now=now,
        topic="runtime.routine-retirements",
    )
    connection.execute(
        """
        INSERT INTO routine_retirements (
            retirement_id, tenant_id, routine_ref, revision_digest,
            retired_by, command_id, event_id, retired_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            retirement_id,
            actor.tenant_id,
            command.routine_ref,
            cast(bytes, target["revision_digest"]),
            actor.principal_id,
            command.client_command_id,
            event_id,
            now,
        ),
    )
    connection.execute(
        """
        DELETE FROM routine_triggers AS trigger
        USING routine_revisions AS revision
        WHERE trigger.tenant_id = %s
          AND trigger.revision_digest = revision.revision_digest
          AND revision.routine_ref = %s
        """,
        (actor.tenant_id, command.routine_ref),
    )
    return receipt


def _receipt(payload: dict[str, object]) -> BeatRoutineRetirementReceipt:
    return BeatRoutineRetirementReceipt(
        UUID(str(payload["command_id"])),
        UUID(str(payload["event_id"])),
        UUID(str(payload["retirement_id"])),
        str(payload["routine_ref"]),
        str(payload["revision_digest"]),
        datetime.fromisoformat(str(payload["retired_at"])),
    )


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = connection.execute("SELECT transaction_timestamp() AS value").fetchone()
    return cast(datetime, cast(dict[str, object], row)["value"])


def _digest(value: bytes) -> str:
    return "sha256:" + value.hex()


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
