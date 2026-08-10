"""Work-owned Request policy, typed commands, and PostgreSQL authority."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    RecordProblem,
    credential_scope_refusal,
)
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    InboundEventRecordedPayload,
)
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.request_events import RequestChangedPayload
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    project_scope_refusal,
    recover_ambiguous_commit,
)
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__ = [
    "PostgresRequests",
    "RequestCapture",
    "RequestCaptureResult",
    "RequestList",
    "RequestRow",
    "Requests",
]

_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_MAX_CONTENT_LENGTH = 65536
_ZERO_HASH = bytes(32)


@dataclass(frozen=True, slots=True)
class RequestCapture:
    """Small capture command: the server derives source, Actor, and owner."""

    client_command_id: UUID
    project_key: str
    text: str

    def request_payload(self) -> dict[str, object]:
        return {"project_key": self.project_key, "text": self.text}


@dataclass(frozen=True, slots=True)
class RequestCaptureResult:
    """Exact semantic capture result retained for replay and durability overlay."""

    command_id: UUID
    event_ids: tuple[UUID, ...]
    inbound_event_id: UUID
    request_id: UUID
    request_number: int
    project_key: str
    submitted_by: UUID
    owner_id: UUID
    version: int = 1

    @property
    def reference(self) -> str:
        return f"R{self.request_number}"

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "inbound_event_id": str(self.inbound_event_id),
            "owner_id": str(self.owner_id),
            "project_key": self.project_key,
            "reference": self.reference,
            "request_id": str(self.request_id),
            "request_number": self.request_number,
            "submitted_by": str(self.submitted_by),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RequestRow:
    """Read-only accepted Request projection at a named Record watermark."""

    request_id: UUID
    request_number: int
    project_key: str
    content: str
    state: str
    triage: str
    owner_id: UUID
    owner: str
    priority: str
    priority_default: bool
    created_at: datetime
    required_ticket_ids: tuple[UUID, ...]
    optional_ticket_ids: tuple[UUID, ...]
    blocker: str | None
    proof_coverage: int | None
    durability_state: str
    freshness: int
    source_kind: str
    unknown_reason: str | None = None

    def response_payload(self, *, observed_at: datetime) -> dict[str, object]:
        return {
            "age_seconds": max(0, int((observed_at - self.created_at).total_seconds())),
            "blocker": self.blocker,
            "content": self.content,
            "durability_state": self.durability_state,
            "freshness": self.freshness,
            "optional_ticket_ids": [str(item) for item in self.optional_ticket_ids],
            "owner": self.owner,
            "owner_id": str(self.owner_id),
            "priority": self.priority,
            "priority_default": self.priority_default,
            "project_key": self.project_key,
            "proof_coverage": self.proof_coverage,
            "reference": f"R{self.request_number}",
            "request_id": str(self.request_id),
            "request_number": self.request_number,
            "required_ticket_ids": [str(item) for item in self.required_ticket_ids],
            "source_kind": self.source_kind,
            "state": self.state,
            "triage": self.triage,
            "unknown_reason": self.unknown_reason,
        }


@dataclass(frozen=True, slots=True)
class RequestList:
    """Epistemically explicit portfolio context; unanswered is never zero."""

    rows: tuple[RequestRow, ...]
    answered_projects: tuple[str, ...]
    requested_projects: tuple[str, ...]
    unanswered_projects: tuple[str, ...]
    watermark: int
    observed_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "answered_project_count": len(self.answered_projects),
            "answered_projects": list(self.answered_projects),
            "observed_at": self.observed_at.isoformat(),
            "requested_project_count": len(self.requested_projects),
            "requested_projects": list(self.requested_projects),
            "rows": [item.response_payload(observed_at=self.observed_at) for item in self.rows],
            "unanswered_projects": list(self.unanswered_projects),
            "watermark": self.watermark,
        }


class _RequestStore(Protocol):
    def capture(
        self,
        actor: Actor,
        command: RequestCapture,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCaptureResult | RecordProblem: ...

    def list(
        self,
        actor: Actor,
        *,
        project_key: str | None,
        now: datetime,
    ) -> RequestList | RecordProblem: ...


class Requests:
    """Authorize Request semantics while the store owns atomic SQL choreography."""

    def __init__(
        self,
        store: _RequestStore,
        *,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    def capture(
        self,
        actor: Actor,
        command: RequestCapture,
        *,
        telemetry: TelemetryContext,
    ) -> RequestCaptureResult | RecordProblem:
        refusal = _capture_refusal(actor, command)
        if refusal is not None:
            return refusal
        outcome = self._store.capture(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit("work.request.capture", telemetry, outcome)
        return outcome

    def list(
        self,
        actor: Actor,
        *,
        project_key: str | None = None,
        telemetry: TelemetryContext,
    ) -> RequestList | RecordProblem:
        if project_key is not None and _PROJECT_KEY.fullmatch(project_key) is None:
            return _invalid(None, "Request project key is invalid")
        outcome = self._store.list(actor, project_key=project_key, now=self._clock())
        self._emit("work.request.list", telemetry, outcome)
        return outcome

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: RequestCaptureResult | RequestList | RecordProblem,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )


class PostgresRequests:
    """Persist Work-owned Request facts through the existing Record transaction."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def capture(
        self,
        actor: Actor,
        command: RequestCapture,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCaptureResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: _capture_sql(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )

    def list(
        self,
        actor: Actor,
        *,
        project_key: str | None,
        now: datetime,
    ) -> RequestList | RecordProblem:
        return _list_sql(self._dsn, actor, project_key=project_key, now=now)


def _capture_refusal(actor: Actor, command: RequestCapture) -> RecordProblem | None:
    scope = credential_scope_refusal(
        actor, CredentialScope.CAPTURE, command_id=command.client_command_id
    )
    if scope is not None:
        return scope
    prohibited = prohibited_data_refusal((command.text,), command_id=command.client_command_id)
    if prohibited is not None:
        return prohibited
    if (
        _PROJECT_KEY.fullmatch(command.project_key) is None
        or not 1 <= len(command.text) <= _MAX_CONTENT_LENGTH
        or command.text.strip() != command.text
    ):
        return _invalid(command.client_command_id, "Request project or text is invalid")
    return None


def _capture_sql(
    dsn: str,
    actor: Actor,
    command: RequestCapture,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestCaptureResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _capture_result(replay)
        scope = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(command.project_key,),
            command_id=command.client_command_id,
        )
        if scope is not None:
            return _refuse(transaction, actor, command, request_digest, scope, now)
        if not _project_exists(connection, actor.tenant_id, command.project_key):
            return _refuse(
                transaction,
                actor,
                command,
                request_digest,
                RecordProblem(
                    code="request-project-unavailable",
                    detail="The target Project is not present in the active tenant hierarchy.",
                    status=404,
                    title="Request Project unavailable",
                    command_id=command.client_command_id,
                ),
                now,
            )
        owner_id = _initial_owner(connection, actor, command.project_key)
        request_id, thread_id, inbound_event_id = (uuid7(now) for _ in range(3))
        event_id, request_event_id = uuid7(now), uuid7(now)
        durable = transaction.require_durable_subjects(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (
                ("inbound_thread", thread_id),
                ("inbound_event", inbound_event_id),
                ("request", request_id),
            ),
            now=now,
        )
        if durable is not None:
            return durable
        request_number = _allocate_number(connection, actor.tenant_id, now)
        source_kind = "ctower-seat-request"
        source_ref = f"{actor.principal_id}:{command.client_command_id}"
        _insert_capture_state(
            connection,
            actor,
            command,
            request_id=request_id,
            request_number=request_number,
            thread_id=thread_id,
            inbound_event_id=inbound_event_id,
            owner_id=owner_id,
            source_kind=source_kind,
            source_ref=source_ref,
            now=now,
        )
        result = RequestCaptureResult(
            command.client_command_id,
            (event_id, request_event_id),
            inbound_event_id,
            request_id,
            request_number,
            command.project_key,
            actor.principal_id,
            owner_id,
        )
        commits = _capture_commits(
            actor,
            command,
            result,
            thread_id=thread_id,
            source_kind=source_kind,
            source_ref=source_ref,
            event_id=event_id,
            request_event_id=request_event_id,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        transaction.commit_batch(
            commits,
            response_body=result.response_payload(),
            status_code=201,
            telemetry=telemetry,
            now=now,
            subjects=(
                ("inbound_thread", thread_id),
                ("inbound_event", inbound_event_id),
                ("request", request_id),
            ),
        )
    return result


def _project_exists(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, project_key: str
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM (
                SELECT project_key FROM project_delivery_checkpoint_definitions
                WHERE tenant_id = %s
                UNION
                SELECT project_key FROM project_seats WHERE tenant_id = %s
            ) AS project
            WHERE project_key = %s LIMIT 1
            """,
            (tenant_id, tenant_id, project_key),
        ).fetchone()
        is not None
    )


def _initial_owner(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, project_key: str
) -> UUID:
    addressable = connection.execute(
        """
        SELECT principal_id FROM project_seats
        WHERE tenant_id = %s AND project_key = %s AND principal_id = %s
        """,
        (actor.tenant_id, project_key, actor.principal_id),
    ).fetchone()
    if addressable is not None:
        return actor.principal_id
    commander = connection.execute(
        """
        SELECT principal.principal_id
        FROM project_seats AS seat
        JOIN principals AS principal
          ON principal.tenant_id = seat.tenant_id AND principal.principal_id = seat.principal_id
        WHERE seat.tenant_id = %s AND seat.project_key = %s
          AND principal.kind = 'commander' AND NOT principal.disabled
        ORDER BY principal.created_at, principal.principal_id LIMIT 1
        """,
        (actor.tenant_id, project_key),
    ).fetchone()
    if commander is None:
        raise RuntimeError("Request project has no eligible Commander")
    return cast(UUID, commander["principal_id"])


def _allocate_number(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, now: datetime
) -> int:
    row = connection.execute(
        """
        INSERT INTO request_number_allocators (tenant_id, last_number, advanced_at)
        VALUES (%s, 1, %s)
        ON CONFLICT (tenant_id) DO UPDATE
        SET last_number = request_number_allocators.last_number + 1,
            advanced_at = EXCLUDED.advanced_at
        RETURNING last_number
        """,
        (tenant_id, now),
    ).fetchone()
    if row is None:
        raise RuntimeError("Request number allocator returned no authority row")
    return int(cast(int, row["last_number"]))


def _insert_capture_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCapture,
    *,
    request_id: UUID,
    request_number: int,
    thread_id: UUID,
    inbound_event_id: UUID,
    owner_id: UUID,
    source_kind: str,
    source_ref: str,
    now: datetime,
) -> None:
    content_digest = hashlib.sha256(command.text.encode()).digest()
    connection.execute(
        """
        INSERT INTO inbound_threads (
            thread_id, tenant_id, project_key, version, created_by, created_at
        ) VALUES (%s, %s, %s, 1, %s, %s)
        """,
        (thread_id, actor.tenant_id, command.project_key, actor.principal_id, now),
    )
    connection.execute(
        """
        INSERT INTO inbound_events (
            inbound_event_id, tenant_id, thread_id, position, source_kind, source_ref,
            content, content_digest, taint, initial_intent, initial_outcome,
            recorded_by, recorded_at
        ) VALUES (%s, %s, %s, 1, %s, %s, %s, %s, 'authenticated',
                  'create_request', 'request_created', %s, %s)
        """,
        (
            inbound_event_id,
            actor.tenant_id,
            thread_id,
            source_kind,
            source_ref,
            command.text,
            content_digest,
            actor.principal_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO inbound_source_aliases (
            tenant_id, source_kind, source_ref, inbound_event_id, thread_id,
            project_key, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor.tenant_id,
            source_kind,
            source_ref,
            inbound_event_id,
            thread_id,
            command.project_key,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO requests (
            request_id, tenant_id, request_number, project_key, content, content_digest,
            source_kind, source_ref, inbound_event_id, submitted_by, capture_command_id,
            version, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
        """,
        (
            request_id,
            actor.tenant_id,
            request_number,
            command.project_key,
            command.text,
            content_digest,
            source_kind,
            source_ref,
            inbound_event_id,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )
    common = (request_id, actor.tenant_id, actor.principal_id, command.client_command_id, now)
    connection.execute(
        """
        INSERT INTO request_owner_facts (
            request_id, tenant_id, sequence, owner_id, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, %s, 'initial accountable owner', %s, %s, %s)
        """,
        (request_id, actor.tenant_id, owner_id, actor.principal_id, command.client_command_id, now),
    )
    connection.execute(
        """
        INSERT INTO request_priority_facts (
            request_id, tenant_id, sequence, priority, is_default, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, 'P2', true, 'capture safety default', %s, %s, %s)
        """,
        common,
    )
    connection.execute(
        """
        INSERT INTO request_triage_facts (
            request_id, tenant_id, sequence, disposition, reason, canonical_request_id,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, 'UNTRIAGED', NULL, NULL, %s, %s, %s)
        """,
        common,
    )
    connection.execute(
        """
        INSERT INTO request_attention_facts (
            attention_id, request_id, tenant_id, kind, active, owner_id, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, 'request_triage_required', true, %s,
                  'Commander disposition is required', %s, %s, %s)
        """,
        (
            uuid7(now),
            request_id,
            actor.tenant_id,
            owner_id,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _capture_commits(
    actor: Actor,
    command: RequestCapture,
    result: RequestCaptureResult,
    *,
    thread_id: UUID,
    source_kind: str,
    source_ref: str,
    event_id: UUID,
    request_event_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[EventCommit, ...]:
    inbound = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=thread_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=event_id,
        kind=EventKind.INBOUND_EVENT_RECORDED,
        origin=EventOrigin.API,
        payload=InboundEventRecordedPayload(
            inbound_event_id=result.inbound_event_id,
            source_kind=source_kind,
            source_ref=source_ref,
            project_key=command.project_key,
            position=1,
            intent="create_request",
            taint="authenticated",
            outcome="request_created",
            content_digest=f"sha256:{hashlib.sha256(command.text.encode()).hexdigest()}",
            ticket_id=None,
        ),
        prev_hash=_ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"inbound-thread:{thread_id}",
        tenant_id=actor.tenant_id,
    )
    changed = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=result.request_id,
        causation_id=result.inbound_event_id,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=request_event_id,
        kind=EventKind.REQUEST_CHANGED,
        origin=EventOrigin.API,
        payload=RequestChangedPayload(
            operation="capture",
            request_id=result.request_id,
            request_number=result.request_number,
            project_key=command.project_key,
            version=1,
            content=command.text,
            content_digest=f"sha256:{hashlib.sha256(command.text.encode()).hexdigest()}",
            source_kind=source_kind,
            source_ref=source_ref,
            submitted_by=actor.principal_id,
            owner_id=result.owner_id,
            triage="UNTRIAGED",
            priority="P2",
            priority_default=True,
            required_ticket_ids=(),
            optional_ticket_ids=(),
            blockers=(),
            closure_outcome="open",
        ),
        prev_hash=_ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"request:{result.request_id}",
        tenant_id=actor.tenant_id,
    )
    return EventCommit(inbound, uuid7(now)), EventCommit(changed, uuid7(now))


def _list_sql(
    dsn: str,
    actor: Actor,
    *,
    project_key: str | None,
    now: datetime,
) -> RequestList | RecordProblem:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        requested = _requested_projects(connection, actor.tenant_id, project_key)
        scope = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=requested,
            operator_only=project_key is None and actor.kind is not PrincipalKind.OPERATOR,
        )
        if scope is not None:
            return scope
        watermark_row = connection.execute(
            "SELECT last_position FROM record_position_ledger WHERE singleton"
        ).fetchone()
        watermark = int(cast(int, watermark_row["last_position"])) if watermark_row else 0
        rows = connection.execute(
            _LIST_SQL,
            (actor.tenant_id, list(requested)),
        ).fetchall()
    return RequestList(
        tuple(_request_row(row) for row in rows),
        requested,
        requested,
        (),
        watermark,
        now,
    )


def _requested_projects(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str | None,
) -> tuple[str, ...]:
    if project_key is not None:
        return (project_key,)
    rows = connection.execute(
        """
        SELECT project_key FROM (
            SELECT project_key FROM project_delivery_checkpoint_definitions WHERE tenant_id = %s
            UNION
            SELECT project_key FROM project_seats WHERE tenant_id = %s
        ) AS project ORDER BY project_key
        """,
        (tenant_id, tenant_id),
    ).fetchall()
    return tuple(str(row["project_key"]) for row in rows)


_LIST_SQL = """
WITH accepted AS (
    SELECT request.*,
           confirmation.acceptance_position
    FROM requests AS request
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = request.tenant_id
     AND confirmation.principal_id = request.submitted_by
     AND confirmation.client_command_id = request.capture_command_id
    WHERE request.tenant_id = %s AND request.project_key = ANY(%s)
), latest_owner AS (
    SELECT DISTINCT ON (request_id) request_id, owner_id
    FROM request_owner_facts ORDER BY request_id, sequence DESC
), latest_priority AS (
    SELECT DISTINCT ON (request_id) request_id, priority, is_default
    FROM request_priority_facts ORDER BY request_id, sequence DESC
), latest_triage AS (
    SELECT DISTINCT ON (request_id) request_id, disposition
    FROM request_triage_facts ORDER BY request_id, sequence DESC
), relation AS (
    SELECT DISTINCT ON (request_id, ticket_id) request_id, ticket_id, purpose, active
    FROM request_ticket_relation_facts
    ORDER BY request_id, ticket_id, recorded_at DESC, relation_fact_id DESC
), blocker AS (
    SELECT DISTINCT ON (request_id, blocker_key) request_id, blocker_key, active
    FROM request_blocker_facts
    ORDER BY request_id, blocker_key, recorded_at DESC, blocker_fact_id DESC
), closure AS (
    SELECT DISTINCT ON (request_id) request_id, outcome, dependency_digest, request_version
    FROM request_closure_evaluations
    ORDER BY request_id, recorded_at DESC, evaluation_id DESC
)
SELECT accepted.request_id, accepted.request_number, accepted.project_key,
       accepted.content, accepted.source_kind, accepted.created_at,
       accepted.version, accepted.acceptance_position,
       latest_owner.owner_id, principal.display_name AS owner,
       latest_priority.priority, latest_priority.is_default,
       latest_triage.disposition,
       COALESCE(array_agg(relation.ticket_id ORDER BY relation.ticket_id)
           FILTER (WHERE relation.active AND relation.purpose = 'required'), ARRAY[]::uuid[])
           AS required_ticket_ids,
       COALESCE(array_agg(relation.ticket_id ORDER BY relation.ticket_id)
           FILTER (WHERE relation.active AND relation.purpose = 'optional'), ARRAY[]::uuid[])
           AS optional_ticket_ids,
       min(blocker.blocker_key) FILTER (WHERE blocker.active) AS blocker,
       closure.outcome AS closure_outcome
FROM accepted
JOIN latest_owner ON latest_owner.request_id = accepted.request_id
JOIN principals AS principal
  ON principal.tenant_id = accepted.tenant_id AND principal.principal_id = latest_owner.owner_id
JOIN latest_priority ON latest_priority.request_id = accepted.request_id
JOIN latest_triage ON latest_triage.request_id = accepted.request_id
LEFT JOIN relation ON relation.request_id = accepted.request_id
LEFT JOIN blocker ON blocker.request_id = accepted.request_id
LEFT JOIN closure ON closure.request_id = accepted.request_id
GROUP BY accepted.request_id, accepted.request_number, accepted.project_key,
         accepted.content, accepted.source_kind, accepted.created_at, accepted.version,
         accepted.acceptance_position, latest_owner.owner_id, principal.display_name,
         latest_priority.priority, latest_priority.is_default, latest_triage.disposition,
         closure.outcome
ORDER BY accepted.request_number
"""


def _request_row(row: dict[str, object]) -> RequestRow:
    triage = str(row["disposition"])
    required = tuple(cast(list[UUID], row["required_ticket_ids"]))
    optional = tuple(cast(list[UUID], row["optional_ticket_ids"]))
    blocker = cast(str | None, row["blocker"])
    closure = cast(str | None, row["closure_outcome"])
    state = (
        "DONE"
        if closure == "done"
        else "BLOCKED"
        if blocker is not None
        else "WIP"
        if triage == "ACCEPTED" and required
        else "TRIAGED"
        if triage != "UNTRIAGED"
        else "NEW"
    )
    return RequestRow(
        request_id=cast(UUID, row["request_id"]),
        request_number=int(cast(int, row["request_number"])),
        project_key=str(row["project_key"]),
        content=str(row["content"]),
        state=state,
        triage=triage,
        owner_id=cast(UUID, row["owner_id"]),
        owner=str(row["owner"]),
        priority=str(row["priority"]),
        priority_default=bool(row["is_default"]),
        created_at=cast(datetime, row["created_at"]),
        required_ticket_ids=required,
        optional_ticket_ids=optional,
        blocker=blocker,
        proof_coverage=None,
        durability_state="accepted",
        freshness=int(cast(int, row["acceptance_position"])),
        source_kind=str(row["source_kind"]),
    )


def _capture_result(payload: dict[str, object]) -> RequestCaptureResult:
    return RequestCaptureResult(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        inbound_event_id=UUID(str(payload["inbound_event_id"])),
        request_id=UUID(str(payload["request_id"])),
        request_number=int(cast(int, payload["request_number"])),
        project_key=str(payload["project_key"]),
        submitted_by=UUID(str(payload["submitted_by"])),
        owner_id=UUID(str(payload["owner_id"])),
        version=int(cast(int, payload["version"])),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestCapture,
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


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()


def _invalid(command_id: UUID | None, detail: str) -> RecordProblem:
    return RecordProblem(
        code="invalid-request",
        detail=detail,
        status=422,
        title="Invalid Request command",
        command_id=command_id,
    )
