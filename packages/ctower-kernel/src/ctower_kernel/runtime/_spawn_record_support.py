"""Private persistence helpers for the spawn-record runtime boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from os import urandom
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import RecordProblem
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.spawn_events import (
    INITIAL_SPAWN_STATE,
    SpawnRecordedPayload,
    SpawnState,
    SpawnTransitionedPayload,
    spawn_transition_allowed,
)
from ctower_kernel.record.transaction import RecordTransaction, project_scope_refusal
from ctower_kernel.runtime._spawn_record_sql import (
    APPEND_TRANSITION,
    CURRENT_DERIVED_STATE,
    INSERT_SPAWN_RECORD,
    SPAWN_PROJECT_KEY,
    TENANT_EXISTS,
)
from ctower_kernel.runtime._spawn_record_types import (
    SpawnRecordCreate,
    SpawnRecordGet,
    SpawnRecordProblem,
    SpawnRecordRow,
    SpawnRecordTransitionCommand,
    SpawnRecordTransitionRow,
)

__all__: tuple[str, ...] = ()

_ZERO_HASH = b"\x00" * 32
_STREAM_PREFIX = "spawn-record"
_SUBJECT_KIND = "spawn_record"


def create_scope_refusal(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    principal_id: UUID,
    command: SpawnRecordCreate,
) -> RecordProblem | None:
    tenant_exists = (
        connection.execute(TENANT_EXISTS, {"tenant_id": tenant_id}).fetchone() is not None
    )
    if tenant_exists:
        return project_scope_refusal(
            connection,
            tenant_id=tenant_id,
            principal_id=principal_id,
            project_keys=(command.project_key,),
            command_id=command.client_command_id,
        )
    return record_problem(command.client_command_id, "tenant-not-found", 404, "Tenant unavailable")


def transition_scope_refusal(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    principal_id: UUID,
    command: SpawnRecordTransitionCommand,
) -> RecordProblem | None:
    """Refuse a principal appending a transition outside its persisted project scope.

    Custody is one boundary across every seam: the spawn's own project is
    resolved here — the way the ticket mutation seam resolves ticket ownership —
    so a read and a write can never disagree about who may touch one project's
    spawns. An unknown spawn resolves to no project and is answered downstream by
    the derived-state read's `spawn-not-found`.
    """

    row = connection.execute(
        SPAWN_PROJECT_KEY,
        {"spawn_id": command.spawn_id, "tenant_id": tenant_id},
    ).fetchone()
    project_keys: tuple[str, ...] = () if row is None else (str(row["project_key"]),)
    return project_scope_refusal(
        connection,
        tenant_id=tenant_id,
        principal_id=principal_id,
        project_keys=project_keys,
        command_id=command.client_command_id,
    )


def insert_spawn(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    principal_id: UUID,
    command: SpawnRecordCreate,
    now: datetime,
) -> tuple[UUID, UUID, SpawnRecordedPayload] | None:
    spawn_id = uuid7(now)
    event_id = uuid7(now)
    payload = SpawnRecordedPayload(
        spawn_id=spawn_id,
        project_key=command.project_key,
        seat_key=command.seat_key,
        crew_name=command.crew_name,
        task_file_ref=command.task_file_ref,
        worktree_path=command.worktree_path,
        harness=command.harness,
        model=command.model,
        effort=command.effort,
        workspace_id=command.workspace_id,
    )
    inserted = connection.execute(
        INSERT_SPAWN_RECORD,
        {
            "spawn_id": spawn_id,
            "tenant_id": tenant_id,
            "project_key": command.project_key,
            "seat_key": command.seat_key,
            "crew_name": command.crew_name,
            "task_file_ref": command.task_file_ref,
            "worktree_path": command.worktree_path,
            "harness": command.harness,
            "model": command.model,
            "effort": command.effort,
            "workspace_id": command.workspace_id,
            "principal_id": principal_id,
            "command_id": command.client_command_id,
            "event_id": event_id,
            "now": now,
        },
    ).fetchone()
    return (spawn_id, event_id, payload) if inserted is not None else None


def create_input_refusal(command: SpawnRecordCreate) -> RecordProblem | None:
    return prohibited_data_refusal(
        [
            command.project_key,
            command.seat_key,
            command.crew_name,
            command.task_file_ref,
            command.worktree_path,
            command.harness,
            command.model,
            command.effort,
        ],
        command_id=command.client_command_id,
    )


def refuse_command(
    transaction: RecordTransaction,
    tenant_id: UUID,
    principal_id: UUID,
    command_id: UUID,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> SpawnRecordProblem:
    return refuse_spawn(
        transaction, tenant_id, principal_id, command_id, request_digest, problem, now
    )


def refuse_transition(
    transaction: RecordTransaction,
    tenant_id: UUID,
    principal_id: UUID,
    command: SpawnRecordTransitionCommand,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> SpawnRecordProblem:
    return refuse_spawn(
        transaction,
        tenant_id,
        principal_id,
        command.client_command_id,
        request_digest,
        problem,
        now,
    )


def replay_create_conflict(
    transaction: RecordTransaction,
    principal_id: UUID,
    command: SpawnRecordCreate,
    request_digest: bytes,
) -> SpawnRecordGet | SpawnRecordProblem:
    replayed = transaction.reserve(principal_id, command.client_command_id, request_digest)
    return (
        reserved_outcome(replayed)
        if replayed is not None
        else spawn_problem(
            command.client_command_id, "spawn-conflict", 409, "Spawn create conflict"
        )
    )


def transition_input_refusal(command: SpawnRecordTransitionCommand) -> RecordProblem | None:
    return prohibited_data_refusal(
        [command.to_status, command.reason],
        command_id=command.client_command_id,
    )


def transition_refusal(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    principal_id: UUID,
    command: SpawnRecordTransitionCommand,
) -> RecordProblem | None:
    """Every refusal the transition seam owes before it reads or appends a fact."""

    return transition_input_refusal(command) or transition_scope_refusal(
        connection, tenant_id, principal_id, command
    )


def transition_states(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    command: SpawnRecordTransitionCommand,
) -> tuple[SpawnState, SpawnState] | RecordProblem:
    current_row = connection.execute(
        CURRENT_DERIVED_STATE,
        {"spawn_id": command.spawn_id, "tenant_id": tenant_id},
    ).fetchone()
    if current_row is None:
        return record_problem(
            command.client_command_id, "spawn-not-found", 404, "Spawn record unavailable"
        )
    from_state = SpawnState(str(cast(str, current_row["status"])))
    to_state = SpawnState(command.to_status)
    if not spawn_transition_allowed(from_state, to_state):
        return record_problem(
            command.client_command_id,
            "invalid-transition",
            422,
            "Spawn transition is outside the authored lifecycle",
        )
    return from_state, to_state


def append_transition(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    principal_id: UUID,
    command: SpawnRecordTransitionCommand,
    now: datetime,
) -> tuple[int, UUID] | None:
    transition_id = uuid7(now)
    event_id = uuid7(now)
    inserted = connection.execute(
        APPEND_TRANSITION,
        {
            "transition_id": transition_id,
            "spawn_id": command.spawn_id,
            "tenant_id": tenant_id,
            "to_status": command.to_status,
            "reason": command.reason,
            "principal_id": principal_id,
            "command_id": command.client_command_id,
            "event_id": event_id,
            "now": now,
        },
    ).fetchone()
    if inserted is None:
        return None
    return int(cast(int, inserted["transition_number"])), event_id


def prepare_transition(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    principal_id: UUID,
    tenant_id: UUID,
    command: SpawnRecordTransitionCommand,
    request_digest: bytes,
    now: datetime,
) -> tuple[SpawnState, SpawnState, int, UUID] | SpawnRecordGet | SpawnRecordProblem:
    reserved = transaction.reserve(principal_id, command.client_command_id, request_digest)
    if reserved is not None:
        return reserved_outcome(reserved)
    refusal = transition_refusal(connection, tenant_id, principal_id, command)
    if refusal is not None:
        return refuse_transition(
            transaction, tenant_id, principal_id, command, request_digest, refusal, now
        )
    decision = transition_states(connection, tenant_id, command)
    if isinstance(decision, RecordProblem):
        return refuse_transition(
            transaction, tenant_id, principal_id, command, request_digest, decision, now
        )
    inserted = append_transition(connection, tenant_id, principal_id, command, now)
    if inserted is None:
        return refuse_transition(
            transaction,
            tenant_id,
            principal_id,
            command,
            request_digest,
            record_problem(
                command.client_command_id,
                "transition-conflict",
                409,
                "Spawn record state changed under the transition",
            ),
            now,
        )
    transition_number, event_id = inserted
    from_state, to_state = decision
    return from_state, to_state, transition_number, event_id


def event(
    principal_id: UUID,
    tenant_id: UUID,
    command_id: UUID,
    kind: EventKind,
    payload: SpawnRecordedPayload | SpawnTransitionedPayload,
    *,
    spawn_id: UUID,
    event_id: UUID,
    correlation_id: UUID,
    request_digest: bytes,
    now: datetime,
    prev_hash: bytes,
    sequence: int,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=principal_id,
        aggregate_id=spawn_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=correlation_id,
        event_id=event_id,
        kind=kind,
        origin=EventOrigin.API,
        payload=payload,
        prev_hash=prev_hash,
        request_sha256=request_digest,
        sequence=sequence,
        server_time=now,
        stream_id=f"{_STREAM_PREFIX}:{spawn_id}",
        tenant_id=tenant_id,
    )


def spawn_stream_state(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    spawn_id: UUID,
) -> tuple[bytes, int]:
    """Continue the spawn's event stream: previous hash and next sequence."""

    previous = connection.execute(
        """
        SELECT event_hash, sequence
        FROM events
        WHERE tenant_id = %s AND stream_id = %s
        ORDER BY sequence DESC LIMIT 1
        """,
        (tenant_id, f"{_STREAM_PREFIX}:{spawn_id}"),
    ).fetchone()
    if previous is None:
        return _ZERO_HASH, 1
    return (
        bytes(cast("bytes", previous["event_hash"])),
        int(cast(int, previous["sequence"])) + 1,
    )


def uuid7(now: datetime) -> UUID:
    """UUIDv7 identity: time-ordered, matching the house identity pattern."""

    unix_ms = int(now.timestamp() * 1000)
    rand = urandom(10)
    value = (unix_ms & 0xFFFFFFFFFFFF) << 80
    value |= int.from_bytes(rand, "big")
    value &= ~(0xF << 76)
    value |= 0x7 << 76
    value &= ~(0x3 << 62)
    value |= 0x2 << 62
    return UUID(int=value)


def row_from_database(
    row: dict[str, object],
    transitions: tuple[SpawnRecordTransitionRow, ...],
) -> SpawnRecordRow:
    return SpawnRecordRow(
        spawn_id=cast(UUID, row["spawn_id"]),
        project_key=str(cast(str, row["project_key"])),
        seat_key=str(cast(str, row["seat_key"])),
        crew_name=str(cast(str, row["crew_name"])),
        task_file_ref=str(cast(str, row["task_file_ref"])),
        worktree_path=str(cast(str, row["worktree_path"])),
        harness=str(cast(str, row["harness"])),
        model=str(cast(str, row["model"])),
        effort=cast("str | None", row["effort"]),
        workspace_id=cast("UUID | None", row["workspace_id"]),
        status=str(cast(str, row["status"])),
        principal_id=cast(UUID, row["principal_id"]),
        created_at=cast(datetime, row["created_at"]),
        updated_at=cast(
            datetime, row["updated_at"] if row["updated_at"] is not None else row["created_at"]
        ),
        transitions=transitions,
    )


def reserved_outcome(
    reserved: dict[str, object] | RecordProblem,
) -> SpawnRecordGet | SpawnRecordProblem:
    if isinstance(reserved, RecordProblem):
        return problem_from_record(reserved)
    payload = dict(reserved)
    payload.pop("command_id", None)
    return get_from_payload(payload)


def get_from_payload(payload: dict[str, object]) -> SpawnRecordGet:
    fallback_time = datetime.now(UTC)
    created_at = payload_datetime(payload.get("created_at"), fallback_time)
    updated_at = payload_datetime(payload.get("updated_at"), created_at)
    raw_transitions = payload.get("transitions") or ()
    if not isinstance(raw_transitions, (list, tuple)):
        raise TypeError("spawn replay transitions are malformed")
    transitions = tuple(
        transition_from_payload(cast(dict[str, object], transition))
        for transition in raw_transitions
    )
    return SpawnRecordGet(
        record=SpawnRecordRow(
            spawn_id=UUID(str(payload["spawn_id"])),
            project_key=str(payload.get("project_key", "")),
            seat_key=str(payload.get("seat_key", "")),
            crew_name=str(payload.get("crew_name", "")),
            task_file_ref=str(payload.get("task_file_ref", "")),
            worktree_path=str(payload.get("worktree_path", "")),
            harness=str(payload.get("harness", "")),
            model=str(payload.get("model", "")),
            effort=cast("str | None", payload.get("effort")),
            workspace_id=(
                UUID(str(payload["workspace_id"])) if payload.get("workspace_id") else None
            ),
            status=str(payload.get("status", INITIAL_SPAWN_STATE.value)),
            principal_id=UUID(str(payload["principal_id"]))
            if payload.get("principal_id")
            else UUID(str(payload["spawn_id"])),
            created_at=created_at,
            updated_at=updated_at,
            transitions=transitions,
        )
    )


def payload_datetime(value: object, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return fallback


def transition_from_payload(payload: dict[str, object]) -> SpawnRecordTransitionRow:
    return SpawnRecordTransitionRow(
        transition_id=UUID(str(payload["transition_id"])),
        spawn_id=UUID(str(payload["spawn_id"])),
        from_status=str(payload["from_status"]),
        to_status=str(payload["to_status"]),
        reason=cast("str | None", payload.get("reason")),
        principal_id=UUID(str(payload["principal_id"])),
        transitioned_at=payload_datetime(payload.get("transitioned_at"), datetime.now(UTC)),
    )


def refuse_spawn(
    transaction: RecordTransaction,
    tenant_id: UUID,
    principal_id: UUID,
    command_id: UUID,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> SpawnRecordProblem:
    transaction.refuse(
        tenant_id,
        principal_id,
        command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem_from_record(problem)


def record_problem(command_id: UUID | None, code: str, status: int, title: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=command_id,
    )


def spawn_problem(
    command_id: UUID | None, code: str, status: int, title: str
) -> SpawnRecordProblem:
    return SpawnRecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=command_id,
    )


def problem_from_record(problem: RecordProblem) -> SpawnRecordProblem:
    return SpawnRecordProblem(
        code=problem.code,
        detail=problem.detail,
        status=problem.status,
        title=problem.title,
        command_id=problem.command_id,
    )


def request_digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()
