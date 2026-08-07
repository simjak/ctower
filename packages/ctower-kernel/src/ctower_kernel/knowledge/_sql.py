"""Record-owned SQL for the knowledge base commands and projection reads."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.knowledge._events import _document_registered_event
from ctower_kernel.knowledge.models import (
    KnowledgeAddCommand,
    KnowledgeAddResult,
    KnowledgeDocument,
    KnowledgeDocumentListResult,
    add_result_from_committed,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_SCOPES = frozenset({"org", "project"})
_MAX_TITLE_LENGTH = 1024
_MAX_BODY_LENGTH = 1_048_576


def register_document(
    dsn: str,
    actor: Actor,
    command: KnowledgeAddCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> KnowledgeAddResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return (
                replay if isinstance(replay, RecordProblem) else add_result_from_committed(replay)
            )
        problem = _validation_problem(command)
        if problem is not None:
            return _refuse(
                transaction, actor, command.client_command_id, request_digest, problem, now
            )
        document_id = uuid7(now)
        durable = transaction.require_durable_subjects(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (("knowledge_document", document_id),),
            now=now,
        )
        if durable is not None:
            return durable
        event = _document_registered_event(
            actor, command, document_id, request_digest, now, telemetry
        )
        result = KnowledgeAddResult(
            command.client_command_id,
            document_id,
            event.event_id,
            now,
            command.scope,
            command.title,
        )
        transaction.commit_batch(
            (EventCommit(event, uuid7(now)),),
            response_body=result.response_payload(),
            status_code=201,
            telemetry=telemetry,
            now=now,
            subjects=(("knowledge_document", document_id),),
        )
        _persist_documents(connection, actor, command.body, result)
        return result


def list_documents(dsn: str, actor: Actor, scope: str) -> KnowledgeDocumentListResult:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        rows = connection.execute(
            """
            SELECT document_id, scope, title, body, registered_at, registered_by
            FROM knowledge_projection_documents
            WHERE tenant_id = %s AND scope = %s
            ORDER BY registered_at, document_id
            """,
            (actor.tenant_id, scope),
        ).fetchall()
    documents = tuple(_document_from_row(row) for row in rows)
    return KnowledgeDocumentListResult(scope, documents)


def get_document(dsn: str, actor: Actor, document_id: UUID) -> KnowledgeDocument | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        row = connection.execute(
            """
            SELECT document_id, scope, title, body, registered_at, registered_by
            FROM knowledge_projection_documents
            WHERE tenant_id = %s AND document_id = %s
            """,
            (actor.tenant_id, document_id),
        ).fetchone()
    if row is not None:
        return _document_from_row(row)
    return None


def _document_from_row(row: dict[str, object]) -> KnowledgeDocument:
    return KnowledgeDocument(
        UUID(str(row["document_id"])),
        str(row["scope"]),
        str(row["title"]),
        str(row["body"]),
        cast(datetime, row["registered_at"]),
        UUID(str(row["registered_by"])),
    )


def _validation_problem(command: KnowledgeAddCommand) -> RecordProblem | None:
    if command.scope not in _SCOPES:
        return RecordProblem(
            "knowledge-invalid-scope",
            "Knowledge scope must be org or project.",
            422,
            "Knowledge command refused",
            command.client_command_id,
        )
    if not 1 <= len(command.title) <= _MAX_TITLE_LENGTH:
        return RecordProblem(
            "knowledge-invalid-title",
            "Knowledge title is outside the authored contract.",
            422,
            "Knowledge command refused",
            command.client_command_id,
        )
    if not 1 <= len(command.body) <= _MAX_BODY_LENGTH:
        return RecordProblem(
            "knowledge-invalid-body",
            "Knowledge body is outside the authored contract.",
            422,
            "Knowledge command refused",
            command.client_command_id,
        )
    return None


def _persist_documents(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    body: str,
    result: KnowledgeAddResult,
) -> None:
    connection.execute(
        """
        INSERT INTO knowledge_documents (
            document_id, tenant_id, scope, title, body, registered_by, registered_at, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.document_id,
            actor.tenant_id,
            result.scope,
            result.title,
            body,
            actor.principal_id,
            result.registered_at,
            result.event_id,
        ),
    )
    connection.execute(
        """
        INSERT INTO knowledge_projection_documents (
            tenant_id, document_id, scope, title, body, registered_at, registered_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor.tenant_id,
            result.document_id,
            result.scope,
            result.title,
            body,
            result.registered_at,
            actor.principal_id,
        ),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem
