"""PostgreSQL append and accepted-read choreography for Ruling facts."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.ruling_events import RulingRecordedPayload
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    project_scope_refusal,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._ruling_types import (
    RulingAppend,
    RulingAppendResult,
    RulingList,
    RulingRow,
    append_result_from_committed,
)

__all__: tuple[str, ...] = ()


def append_ruling(
    dsn: str,
    actor: Actor,
    command: RulingAppend,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RulingAppendResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return (
                replay
                if isinstance(replay, RecordProblem)
                else append_result_from_committed(replay)
            )
        seat = _existing_seat(
            connection,
            actor,
            project_key=command.project_key,
            allow_operator=command.origin
            in {
                EventOrigin.MIGRATION_IMPORTER,
                EventOrigin.ESTATE_IMPORT,
            },
        )
        if seat is None:
            return _refuse(
                transaction,
                actor,
                command,
                request_digest,
                _problem(
                    "ruling-seat-not-found",
                    "The authenticated identity is not an active project seat.",
                    404,
                    "Ruling seat not found",
                    command.client_command_id,
                ),
                now,
            )
        project_key, seat_key = seat
        linked_request_id, decision_fact_id, relation_problem = _ruling_relation(
            connection,
            actor,
            command,
            project_key,
        )
        if relation_problem is not None:
            return _refuse(transaction, actor, command, request_digest, relation_problem, now)
        return _commit_ruling(
            connection,
            transaction,
            actor,
            command,
            request_digest=request_digest,
            project_key=project_key,
            request_id=linked_request_id,
            decision_blocker_fact_id=decision_fact_id,
            seat_key=seat_key,
            now=now,
            telemetry=telemetry,
        )


def _ruling_relation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RulingAppend,
    project_key: str,
) -> tuple[UUID | None, UUID | None, RecordProblem | None]:
    predecessor_request_id, predecessor_decision_fact_id, problem = _predecessor_link(
        connection, actor, command, project_key
    )
    if problem is not None:
        return None, None, problem
    request_id = (
        predecessor_request_id if command.supersedes_ruling_id is not None else command.request_id
    )
    decision_fact_id, problem = _decision_link(
        connection,
        actor,
        command,
        project_key=project_key,
        request_id=request_id,
        predecessor_decision_fact_id=predecessor_decision_fact_id,
    )
    return request_id, decision_fact_id, problem


def _commit_ruling(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RulingAppend,
    *,
    request_digest: bytes,
    project_key: str,
    request_id: UUID | None,
    decision_blocker_fact_id: UUID | None,
    seat_key: str,
    now: datetime,
    telemetry: TelemetryContext,
) -> RulingAppendResult | RecordProblem:
    recorded_at, ruling_id = _ruling_identity(command, now)
    subjects = _subjects(ruling_id, request_id)
    durable = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        subjects,
        now=now,
    )
    if durable is not None:
        return durable
    event = _ruling_event(
        actor,
        command,
        ruling_id,
        project_key=project_key,
        request_id=request_id,
        decision_blocker_fact_id=decision_blocker_fact_id,
        request_digest=request_digest,
        seat_key=seat_key,
        recorded_at=recorded_at,
        now=now,
        telemetry=telemetry,
    )
    result = RulingAppendResult(
        command.client_command_id,
        ruling_id,
        event.event_id,
        project_key,
        actor.principal_id,
        seat_key,
        recorded_at,
        command.supersedes_ruling_id,
        request_id,
    )
    transaction.commit_batch(
        (EventCommit(event, uuid7(now)),),
        response_body=result.response_payload(),
        status_code=201,
        telemetry=telemetry,
        now=now,
        subjects=subjects,
    )
    _persist_ruling(
        connection,
        actor,
        command,
        result,
        decision_blocker_fact_id=decision_blocker_fact_id,
    )
    return result


def _ruling_identity(command: RulingAppend, now: datetime) -> tuple[datetime, UUID]:
    recorded_at = command.recorded_at if command.recorded_at is not None else now
    ruling_id = command.ruling_id if command.ruling_id is not None else uuid7(recorded_at)
    return recorded_at, ruling_id


def list_rulings(
    dsn: str,
    actor: Actor,
    *,
    project_key: str | None,
    now: datetime,
) -> RulingList | RecordProblem:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("SET ROLE ctower_svc")
        requested = _requested_projects(connection, actor.tenant_id, project_key)
        if project_key is not None and not requested:
            return _problem(
                "ruling-project-unavailable",
                "The requested Project is not present in the active tenant hierarchy.",
                404,
                "Ruling Project unavailable",
            )
        scope = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=requested,
            operator_only=project_key is None and actor.kind is not PrincipalKind.OPERATOR,
            allow_operator_read=True,
        )
        if scope is not None:
            return scope
        watermark = _watermark(connection)
        rows = connection.execute(
            _ACCEPTED_RULINGS_SQL + " ORDER BY ruling.recorded_at DESC, ruling.ruling_id DESC",
            (actor.tenant_id, list(requested)),
        ).fetchall()
    return RulingList(
        tuple(_row(item) for item in rows),
        requested,
        requested,
        (),
        watermark,
        now,
    )


def get_ruling(
    dsn: str,
    actor: Actor,
    ruling_id: UUID,
) -> RulingRow | RecordProblem:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("SET ROLE ctower_svc")
        readable = _readable_projects(connection, actor)
        if readable == ():
            return _problem(
                "ruling-not-found",
                "The Ruling is not available in the authenticated scope.",
                404,
                "Ruling not found",
            )
        row = connection.execute(
            _ACCEPTED_RULINGS_SQL + " AND ruling.ruling_id = %s",
            (actor.tenant_id, list(readable), ruling_id),
        ).fetchone()
    if row is None:
        return _problem(
            "ruling-not-found",
            "The Ruling is not available in the authenticated scope.",
            404,
            "Ruling not found",
        )
    return _row(row)


def _existing_seat(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    *,
    project_key: str | None,
    allow_operator: bool,
) -> tuple[str, str] | None:
    principal_kind = "operator" if allow_operator else "commander"
    parameters: tuple[object, ...] = (
        actor.tenant_id,
        actor.principal_id,
        principal_kind,
        project_key,
        project_key,
    )
    row = connection.execute(
        """
        SELECT seat.project_key, seat.seat_key
        FROM project_seats AS seat
        JOIN principals AS principal
          ON principal.tenant_id = seat.tenant_id
         AND principal.principal_id = seat.principal_id
        WHERE seat.tenant_id = %s AND seat.principal_id = %s
          AND principal.kind = %s AND NOT principal.disabled
          AND (%s::text IS NULL OR seat.project_key = %s)
        """,
        parameters,
    ).fetchone()
    if row is None:
        return None
    return str(row["project_key"]), str(row["seat_key"])


def _predecessor_link(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RulingAppend,
    project_key: str,
) -> tuple[UUID | None, UUID | None, RecordProblem | None]:
    predecessor_id = command.supersedes_ruling_id
    if predecessor_id is None:
        return None, None, None
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s::text, 0))",
        (predecessor_id,),
    )
    predecessor = connection.execute(
        """
        SELECT ruling.ruling_id, ruling.request_id, ruling.decision_blocker_fact_id
        FROM rulings AS ruling
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = ruling.tenant_id
         AND confirmation.principal_id = ruling.recorded_by
         AND confirmation.client_command_id = ruling.command_id
        WHERE ruling.tenant_id = %s AND ruling.project_key = %s
          AND ruling.ruling_id = %s
        """,
        (actor.tenant_id, project_key, predecessor_id),
    ).fetchone()
    if predecessor is None:
        return (
            None,
            None,
            _problem(
                "ruling-not-found",
                "The superseded Ruling is not available in the authenticated scope.",
                404,
                "Ruling not found",
                command.client_command_id,
            ),
        )
    successor = connection.execute(
        "SELECT 1 FROM rulings WHERE supersedes_ruling_id = %s",
        (predecessor_id,),
    ).fetchone()
    if successor is not None:
        return (
            None,
            None,
            _problem(
                "ruling-already-superseded",
                "The Ruling already has a successor.",
                409,
                "Ruling already superseded",
                command.client_command_id,
            ),
        )
    return (
        cast(UUID | None, predecessor["request_id"]),
        cast(UUID | None, predecessor["decision_blocker_fact_id"]),
        None,
    )


def _decision_link(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RulingAppend,
    *,
    project_key: str,
    request_id: UUID | None,
    predecessor_decision_fact_id: UUID | None,
) -> tuple[UUID | None, RecordProblem | None]:
    if command.supersedes_ruling_id is not None:
        return predecessor_decision_fact_id, None
    if request_id is None:
        return None, None
    request = connection.execute(
        """
        SELECT request.request_number
        FROM requests AS request
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = request.tenant_id
         AND confirmation.principal_id = request.submitted_by
         AND confirmation.client_command_id = request.capture_command_id
        WHERE request.tenant_id = %s AND request.project_key = %s
          AND request.request_id = %s
        FOR UPDATE OF request
        """,
        (actor.tenant_id, project_key, request_id),
    ).fetchone()
    if request is None:
        return None, _problem(
            "ruling-request-not-found",
            "The linked Request is not available in the authenticated Project.",
            404,
            "Ruling Request not found",
            command.client_command_id,
        )
    decision = connection.execute(
        """
        SELECT fact.blocker_fact_id, fact.active
        FROM request_blocker_facts AS fact
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = fact.tenant_id
         AND confirmation.principal_id = fact.recorded_by
         AND confirmation.client_command_id = fact.command_id
        WHERE fact.tenant_id = %s AND fact.request_id = %s
          AND fact.blocker_key = 'operator-decision-required'
        ORDER BY fact.request_version DESC LIMIT 1
        """,
        (actor.tenant_id, request_id),
    ).fetchone()
    if decision is None or not bool(decision["active"]):
        return None, _problem(
            "ruling-request-not-decision",
            "The linked Request has no current operator decision need.",
            409,
            "Ruling Request does not need a decision",
            command.client_command_id,
        )
    decision_fact_id = cast(UUID, decision["blocker_fact_id"])
    existing = connection.execute(
        """
        SELECT 1 FROM rulings
        WHERE tenant_id = %s AND decision_blocker_fact_id = %s
          AND supersedes_ruling_id IS NULL
        """,
        (actor.tenant_id, decision_fact_id),
    ).fetchone()
    if existing is not None:
        return None, _problem(
            "ruling-request-already-answered",
            "The current Request decision occurrence already has a Ruling chain.",
            409,
            "Ruling Request already answered",
            command.client_command_id,
        )
    return decision_fact_id, None


def _ruling_event(
    actor: Actor,
    command: RulingAppend,
    ruling_id: UUID,
    *,
    project_key: str,
    request_id: UUID | None,
    decision_blocker_fact_id: UUID | None,
    request_digest: bytes,
    seat_key: str,
    recorded_at: datetime,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    verbatim_digest = hashlib.sha256(command.verbatim.encode("utf-8")).hexdigest()
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=ruling_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=uuid7(now),
        kind=EventKind.RULING_RECORDED,
        origin=command.origin,
        payload=RulingRecordedPayload(
            ruling_id,
            project_key,
            command.verbatim,
            f"sha256:{verbatim_digest}",
            actor.principal_id,
            seat_key,
            recorded_at,
            command.supersedes_ruling_id,
            request_id,
            decision_blocker_fact_id,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"ruling:{ruling_id}",
        tenant_id=actor.tenant_id,
    )


def _persist_ruling(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RulingAppend,
    result: RulingAppendResult,
    *,
    decision_blocker_fact_id: UUID | None,
) -> None:
    verbatim = command.verbatim.encode("utf-8")
    connection.execute(
        """
        INSERT INTO rulings (
            ruling_id, tenant_id, project_key, verbatim_bytes, verbatim_sha256,
            recorded_by, seat_key, recorded_at, command_id, event_id,
            supersedes_ruling_id, request_id, decision_blocker_fact_id, source_ref
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.ruling_id,
            actor.tenant_id,
            result.project_key,
            verbatim,
            hashlib.sha256(verbatim).digest(),
            actor.principal_id,
            result.seat_key,
            result.recorded_at,
            command.client_command_id,
            result.event_id,
            command.supersedes_ruling_id,
            result.request_id,
            decision_blocker_fact_id,
            command.source_ref,
        ),
    )


def _subjects(ruling_id: UUID, request_id: UUID | None) -> tuple[tuple[str, UUID], ...]:
    if request_id is None:
        return (("ruling", ruling_id),)
    return (("request", request_id), ("ruling", ruling_id))


def _requested_projects(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str | None,
) -> tuple[str, ...]:
    query = _ALL_PROJECTS_SQL
    parameters: tuple[object, ...] = (tenant_id, tenant_id)
    if project_key is not None:
        query = _ONE_PROJECT_SQL
        parameters += (project_key,)
    rows = connection.execute(query, parameters).fetchall()
    return tuple(str(row["project_key"]) for row in rows)


def _readable_projects(
    connection: psycopg.Connection[dict[str, object]], actor: Actor
) -> tuple[str, ...]:
    if actor.kind is PrincipalKind.OPERATOR:
        return _requested_projects(connection, actor.tenant_id, None)
    rows = connection.execute(
        """
        SELECT project_key FROM project_seats
        WHERE tenant_id = %s AND principal_id = %s
        UNION
        SELECT unnest(binding.project_keys) AS project_key
        FROM human_role_bindings AS binding
        LEFT JOIN human_role_binding_revocations AS revocation
          ON revocation.tenant_id = binding.tenant_id
         AND revocation.binding_id = binding.binding_id
        WHERE binding.tenant_id = %s AND binding.principal_id = %s
          AND revocation.binding_id IS NULL
        ORDER BY project_key
        """,
        (actor.tenant_id, actor.principal_id, actor.tenant_id, actor.principal_id),
    ).fetchall()
    return tuple(str(row["project_key"]) for row in rows)


def _watermark(connection: psycopg.Connection[dict[str, object]]) -> int:
    row = connection.execute(
        "SELECT last_position FROM record_position_ledger WHERE singleton"
    ).fetchone()
    return 0 if row is None else int(cast(int, row["last_position"]))


def _row(row: dict[str, object]) -> RulingRow:
    supersedes = row["supersedes_ruling_id"]
    superseded_by = row["superseded_by_ruling_id"]
    verbatim = bytes(cast(bytes, row["verbatim_bytes"])).decode("utf-8")
    return RulingRow(
        cast(UUID, row["ruling_id"]),
        str(row["project_key"]),
        verbatim,
        f"sha256:{bytes(cast(bytes, row['verbatim_sha256'])).hex()}",
        cast(UUID, row["recorded_by"]),
        str(row["seat_key"]),
        cast(datetime, row["recorded_at"]),
        cast(UUID | None, supersedes),
        cast(UUID | None, superseded_by),
        int(cast(int, row["freshness"])),
        cast(UUID | None, row["request_id"]),
        (None if row["request_number"] is None else f"R{int(cast(int, row['request_number']))}"),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: RulingAppend,
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


def _problem(
    code: str,
    detail: str,
    status: int,
    title: str,
    command_id: UUID | None = None,
) -> RecordProblem:
    return RecordProblem(code, detail, status, title, command_id)


_ACCEPTED_RULINGS_SQL = """
WITH accepted AS (
    SELECT ruling.*, confirmation.acceptance_position AS freshness
    FROM rulings AS ruling
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = ruling.tenant_id
     AND confirmation.principal_id = ruling.recorded_by
     AND confirmation.client_command_id = ruling.command_id
    WHERE ruling.tenant_id = %s
), accepted_successors AS (
    SELECT successor.supersedes_ruling_id, successor.ruling_id
    FROM accepted AS successor
    WHERE successor.supersedes_ruling_id IS NOT NULL
)
SELECT ruling.ruling_id, ruling.project_key, ruling.verbatim_bytes,
       ruling.verbatim_sha256, ruling.recorded_by, ruling.seat_key,
       ruling.recorded_at, ruling.supersedes_ruling_id,
       successor.ruling_id AS superseded_by_ruling_id, ruling.freshness,
       ruling.request_id, request.request_number
FROM accepted AS ruling
LEFT JOIN accepted_successors AS successor
  ON successor.supersedes_ruling_id = ruling.ruling_id
LEFT JOIN requests AS request
  ON request.tenant_id = ruling.tenant_id AND request.request_id = ruling.request_id
WHERE ruling.project_key = ANY(%s)
"""

_ALL_PROJECTS_SQL = """
SELECT project_key FROM (
    SELECT project_key FROM project_delivery_checkpoint_definitions WHERE tenant_id = %s
    UNION
    SELECT project_key FROM project_seats WHERE tenant_id = %s
) AS project
ORDER BY project_key
"""

_ONE_PROJECT_SQL = """
SELECT project_key FROM (
    SELECT project_key FROM project_delivery_checkpoint_definitions WHERE tenant_id = %s
    UNION
    SELECT project_key FROM project_seats WHERE tenant_id = %s
) AS project
WHERE project_key = %s
ORDER BY project_key
"""
