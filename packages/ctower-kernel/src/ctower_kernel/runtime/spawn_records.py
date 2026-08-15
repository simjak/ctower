"""SpawnRecord operations: create, transition, list, get, and idempotency.

Spawn custody (R2982/R3000, CT-I1-034) on the house Record pattern: one
authority connection under ``ctower_svc``, command reservation, prohibited-data
refusal, typed canonical events through ``append_event``, and command results
committed atomically by ``RecordTransaction``. Lifecycle state is append-only
and DERIVED from the latest transition fact — ``spawn_records`` has no status
column and no UPDATE path exists.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record.events import EventKind
from ctower_kernel.record.spawn_events import (
    SpawnRecordedPayload,
    SpawnState,
    SpawnTransitionedPayload,
)
from ctower_kernel.record.spawn_telemetry import spawn_event_telemetry
from ctower_kernel.record.transaction import (
    RecordTransaction,
    authority_connection,
    project_scope_refusal,
)
from ctower_kernel.runtime._spawn_record_sql import (
    GET_SPAWN_RECORD,
    GET_TRANSITIONS,
    LIST_SPAWN_RECORDS,
)
from ctower_kernel.runtime._spawn_record_support import (
    create_input_refusal as _create_input_refusal,
)
from ctower_kernel.runtime._spawn_record_support import (
    create_scope_refusal as _create_scope_refusal,
)
from ctower_kernel.runtime._spawn_record_support import event as _event
from ctower_kernel.runtime._spawn_record_support import insert_spawn as _insert_spawn
from ctower_kernel.runtime._spawn_record_support import prepare_transition as _prepare_transition
from ctower_kernel.runtime._spawn_record_support import problem_from_record as _problem_from_record
from ctower_kernel.runtime._spawn_record_support import refuse_command as _refuse_command
from ctower_kernel.runtime._spawn_record_support import (
    replay_create_conflict as _replay_create_conflict,
)
from ctower_kernel.runtime._spawn_record_support import request_digest as _request_digest
from ctower_kernel.runtime._spawn_record_support import reserved_outcome as _reserved_outcome
from ctower_kernel.runtime._spawn_record_support import row_from_database as _row_from_database
from ctower_kernel.runtime._spawn_record_support import spawn_problem as _spawn_problem
from ctower_kernel.runtime._spawn_record_support import spawn_stream_state as _spawn_stream_state
from ctower_kernel.runtime._spawn_record_support import uuid7 as _uuid7
from ctower_kernel.runtime._spawn_record_types import (
    SpawnRecordCreate,
    SpawnRecordGet,
    SpawnRecordList,
    SpawnRecordProblem,
    SpawnRecordRow,
    SpawnRecordTransitionCommand,
    SpawnRecordTransitionRow,
)

__all__ = [
    "PostgresSpawnRecords",
    "SpawnRecordCreate",
    "SpawnRecordGet",
    "SpawnRecordList",
    "SpawnRecordProblem",
    "SpawnRecordRow",
    "SpawnRecordTransitionCommand",
    "SpawnRecordTransitionRow",
    "SpawnRecords",
]

_ZERO_HASH = b"\x00" * 32
_SUBJECT_KIND = "spawn_record"
_MAX_LIST_LIMIT = 200

VALID_STATUSES = frozenset({state.value for state in SpawnState})

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    from_state.value: frozenset(to.value for to in targets)
    for from_state, targets in {
        SpawnState.REQUESTED: frozenset({SpawnState.ACCEPTED, SpawnState.FAILED}),
        SpawnState.ACCEPTED: frozenset({SpawnState.RUNNING, SpawnState.FAILED}),
        SpawnState.RUNNING: frozenset({SpawnState.COMPLETED, SpawnState.FAILED, SpawnState.REAPED}),
        SpawnState.COMPLETED: frozenset(),
        SpawnState.FAILED: frozenset(),
        SpawnState.REAPED: frozenset(),
    }.items()
}


class SpawnRecords:
    """Interface for spawn record operations."""

    def create(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        command: SpawnRecordCreate,
        telemetry: object | None = None,
    ) -> SpawnRecordGet | SpawnRecordProblem:
        raise NotImplementedError

    def transition(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        command: SpawnRecordTransitionCommand,
        telemetry: object | None = None,
    ) -> SpawnRecordGet | SpawnRecordProblem:
        raise NotImplementedError

    def list(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        project_key: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SpawnRecordList | SpawnRecordProblem:
        raise NotImplementedError

    def get(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        spawn_id: UUID,
    ) -> SpawnRecordGet | SpawnRecordProblem:
        raise NotImplementedError


class PostgresSpawnRecords(SpawnRecords):
    """PostgreSQL implementation of SpawnRecords on the authority pattern."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def create(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        command: SpawnRecordCreate,
        telemetry: object | None = None,
    ) -> SpawnRecordGet | SpawnRecordProblem:
        request_digest = _request_digest(command.request_payload())
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            transaction = RecordTransaction(connection)
            now = datetime.now(UTC)

            reserved = transaction.reserve(principal_id, command.client_command_id, request_digest)
            if reserved is not None:
                return _reserved_outcome(reserved)

            refusal = _create_input_refusal(command)
            if refusal is not None:
                return _refuse_command(
                    transaction,
                    tenant_id,
                    principal_id,
                    command.client_command_id,
                    request_digest,
                    refusal,
                    now,
                )

            scope_refusal = _create_scope_refusal(connection, tenant_id, principal_id, command)
            if scope_refusal is not None:
                return _refuse_command(
                    transaction,
                    tenant_id,
                    principal_id,
                    command.client_command_id,
                    request_digest,
                    scope_refusal,
                    now,
                )

            inserted = _insert_spawn(connection, tenant_id, principal_id, command, now)
            if inserted is None:
                # Lost the reserve race on the unique key; replay returns it.
                return _replay_create_conflict(transaction, principal_id, command, request_digest)

            spawn_id, event_id, payload = inserted
            return self._commit_create(
                connection,
                transaction,
                principal_id,
                tenant_id,
                command,
                telemetry,
                request_digest,
                now,
                spawn_id,
                event_id,
                payload,
            )

    def _commit_create(
        self,
        connection: psycopg.Connection[dict[str, object]],
        transaction: RecordTransaction,
        principal_id: UUID,
        tenant_id: UUID,
        command: SpawnRecordCreate,
        telemetry: object | None,
        request_digest: bytes,
        now: datetime,
        spawn_id: UUID,
        event_id: UUID,
        payload: SpawnRecordedPayload,
    ) -> SpawnRecordGet | SpawnRecordProblem:
        row = self._row_for(connection, tenant_id, spawn_id)
        event_telemetry = spawn_event_telemetry(
            telemetry, principal_id, tenant_id, command.client_command_id
        )
        event = _event(
            principal_id,
            tenant_id,
            command.client_command_id,
            EventKind.SPAWN_RECORDED,
            payload,
            spawn_id=spawn_id,
            event_id=event_id,
            correlation_id=event_telemetry.correlation_uuid(command.client_command_id),
            request_digest=request_digest,
            now=now,
            prev_hash=_ZERO_HASH,
            sequence=1,
        )
        row_payload = row.response_payload() if row is not None else {}
        transaction.commit(
            event,
            outbox_id=_uuid7(now),
            response_body=dict(row_payload),
            status_code=201,
            telemetry=event_telemetry,
            now=now,
            subjects=((_SUBJECT_KIND, spawn_id),),
        )
        if row is None:  # pragma: no cover - INSERT..RETURNING succeeded
            return _spawn_problem(
                command.client_command_id,
                "spawn-not-found",
                404,
                "Spawn record unavailable",
            )
        return SpawnRecordGet(record=row)

    def transition(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        command: SpawnRecordTransitionCommand,
        telemetry: object | None = None,
    ) -> SpawnRecordGet | SpawnRecordProblem:
        request_digest = _request_digest(command.request_payload())
        if command.to_status not in VALID_STATUSES:
            return _spawn_problem(
                command.client_command_id,
                "invalid-status",
                422,
                "Transition target is outside the authored lifecycle",
            )
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            transaction = RecordTransaction(connection)
            now = datetime.now(UTC)

            prepared = _prepare_transition(
                connection, transaction, principal_id, tenant_id, command, request_digest, now
            )
            if not isinstance(prepared, tuple):
                return prepared
            from_state, to_state, transition_number, event_id = prepared

            return self._commit_transition(
                connection,
                transaction,
                principal_id,
                tenant_id,
                command,
                telemetry,
                request_digest,
                now,
                from_state,
                to_state,
                transition_number,
                event_id,
            )

    def _commit_transition(
        self,
        connection: psycopg.Connection[dict[str, object]],
        transaction: RecordTransaction,
        principal_id: UUID,
        tenant_id: UUID,
        command: SpawnRecordTransitionCommand,
        telemetry: object | None,
        request_digest: bytes,
        now: datetime,
        from_state: SpawnState,
        to_state: SpawnState,
        transition_number: int,
        event_id: UUID,
    ) -> SpawnRecordGet | SpawnRecordProblem:
        payload = SpawnTransitionedPayload(
            spawn_id=command.spawn_id,
            from_state=from_state,
            to_state=to_state,
            transition_number=transition_number,
            reason=command.reason,
        )
        prev_hash, next_sequence = _spawn_stream_state(connection, tenant_id, command.spawn_id)
        event_telemetry = spawn_event_telemetry(
            telemetry, principal_id, tenant_id, command.client_command_id
        )
        event = _event(
            principal_id,
            tenant_id,
            command.client_command_id,
            EventKind.SPAWN_TRANSITIONED,
            payload,
            spawn_id=command.spawn_id,
            event_id=event_id,
            correlation_id=event_telemetry.correlation_uuid(command.client_command_id),
            request_digest=request_digest,
            now=now,
            prev_hash=prev_hash,
            sequence=next_sequence,
        )
        row = self._row_for(connection, tenant_id, command.spawn_id)
        row_payload = row.response_payload() if row is not None else {}
        transaction.commit(
            event,
            outbox_id=_uuid7(now),
            response_body=dict(row_payload),
            status_code=200,
            telemetry=event_telemetry,
            now=now,
            subjects=((_SUBJECT_KIND, command.spawn_id),),
        )
        if row is None:  # pragma: no cover - APPEND_TRANSITION..RETURNING succeeded
            return _spawn_problem(
                command.client_command_id,
                "spawn-not-found",
                404,
                "Spawn record unavailable",
            )
        return SpawnRecordGet(record=row)

    def list(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        project_key: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SpawnRecordList | SpawnRecordProblem:
        if status is not None and status not in VALID_STATUSES:
            return _spawn_problem(None, "invalid-status", 422, "Status filter is not authored")
        bounded_limit = min(max(limit, 1), _MAX_LIST_LIMIT)
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            scope_refusal = project_scope_refusal(
                connection,
                tenant_id=tenant_id,
                principal_id=principal_id,
                project_keys=(project_key,),
            )
            if scope_refusal is not None:
                return _problem_from_record(scope_refusal)
            rows = connection.execute(
                LIST_SPAWN_RECORDS,
                {
                    "tenant_id": tenant_id,
                    "project_key": project_key,
                    "status_filter": status,
                    "limit": bounded_limit,
                    "offset": max(offset, 0),
                },
            ).fetchall()
            spawn_ids = tuple(cast(UUID, row["spawn_id"]) for row in rows)
            transitions_by_spawn = self._transitions_for(connection, tenant_id, spawn_ids)
            return SpawnRecordList(
                records=tuple(
                    _row_from_database(
                        row, transitions_by_spawn.get(cast(UUID, row["spawn_id"]), ())
                    )
                    for row in rows
                )
            )

    def get(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        spawn_id: UUID,
    ) -> SpawnRecordGet | SpawnRecordProblem:
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            row = connection.execute(
                GET_SPAWN_RECORD,
                {"spawn_id": spawn_id, "tenant_id": tenant_id},
            ).fetchone()
            if row is None:
                return _spawn_problem(None, "spawn-not-found", 404, "Spawn record unavailable")
            scope_refusal = project_scope_refusal(
                connection,
                tenant_id=tenant_id,
                principal_id=principal_id,
                project_keys=(str(row["project_key"]),),
            )
            if scope_refusal is not None:
                return _problem_from_record(scope_refusal)
            transitions = self._transitions_for(connection, tenant_id, (spawn_id,))
            return SpawnRecordGet(record=_row_from_database(row, transitions.get(spawn_id, ())))

    def _row_for(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        spawn_id: UUID,
    ) -> SpawnRecordRow | None:
        row = connection.execute(
            GET_SPAWN_RECORD,
            {"spawn_id": spawn_id, "tenant_id": tenant_id},
        ).fetchone()
        if row is None:
            return None
        transitions = self._transitions_for(connection, tenant_id, (spawn_id,))
        return _row_from_database(row, transitions.get(spawn_id, ()))

    def _transitions_for(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        spawn_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[SpawnRecordTransitionRow, ...]]:
        grouped: dict[UUID, list[SpawnRecordTransitionRow]] = {}
        for spawn_id in spawn_ids:
            rows = connection.execute(
                GET_TRANSITIONS,
                {"spawn_id": spawn_id, "tenant_id": tenant_id},
            ).fetchall()
            for row in rows:
                transition = SpawnRecordTransitionRow(
                    transition_id=cast(UUID, row["transition_id"]),
                    spawn_id=cast(UUID, row["spawn_id"]),
                    from_status=str(cast(str, row["from_status"])),
                    to_status=str(cast(str, row["to_status"])),
                    reason=cast("str | None", row["reason"]),
                    principal_id=cast(UUID, row["principal_id"]),
                    transitioned_at=cast(datetime, row["transitioned_at"]),
                )
                grouped.setdefault(spawn_id, []).append(transition)
        return {sid: tuple(items) for sid, items in grouped.items()}
