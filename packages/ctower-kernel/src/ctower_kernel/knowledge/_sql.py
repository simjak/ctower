"""Record-owned SQL for knowledge commands and projection reads."""

from __future__ import annotations

import re
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
from ctower_kernel.knowledge.source import KnowledgeSource, KnowledgeSourceUnavailableError
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.events import EventOrigin
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    project_mutation_refusal,
    project_scope_refusal,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_SCOPES = frozenset({"org", "project"})
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def register_document(
    dsn: str,
    actor: Actor,
    command: KnowledgeAddCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
    source: KnowledgeSource | None,
) -> KnowledgeAddResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return (
                replay if isinstance(replay, RecordProblem) else add_result_from_committed(replay)
            )
        problem = _write_authority_problem(connection, actor, command)
        if problem is not None:
            return _refuse(transaction, actor, command, request_digest, problem, now)
        resolved = _resolve_content(source, command)
        if isinstance(resolved, RecordProblem):
            return _refuse(transaction, actor, command, request_digest, resolved, now)
        title, body = resolved
        recorded_at = command.recorded_at if command.recorded_at is not None else now
        document_id = command.document_id if command.document_id is not None else uuid7(recorded_at)
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
            actor,
            command,
            document_id,
            request_digest,
            recorded_at,
            now,
            telemetry,
            body=body,
            title=title,
        )
        result = _add_result(command, document_id, event.event_id, recorded_at, title)
        transaction.commit_batch(
            (EventCommit(event, uuid7(now)),),
            response_body=result.response_payload(),
            status_code=201,
            telemetry=telemetry,
            now=now,
            subjects=(("knowledge_document", document_id),),
        )
        _persist_documents(connection, actor, body, result)
        return result


def list_documents(
    dsn: str,
    actor: Actor,
    scope: str,
    project_key: str | None = None,
) -> KnowledgeDocumentListResult | RecordProblem:
    validation = _read_scope_problem(scope, project_key)
    if validation is not None:
        return validation
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        authorization = _read_authority_problem(connection, actor, scope, project_key)
        if authorization is not None:
            return authorization
        rows = connection.execute(
            """
            SELECT document_id, scope, title, body, registered_at, registered_by,
                   project_key, source_ref
            FROM knowledge_projection_documents
            WHERE tenant_id = %s AND scope = %s
              AND project_key IS NOT DISTINCT FROM %s
            ORDER BY registered_at, document_id
            """,
            (actor.tenant_id, scope, project_key),
        ).fetchall()
    return KnowledgeDocumentListResult(
        scope,
        tuple(_document_from_row(row) for row in rows),
        project_key,
    )


def get_document(
    dsn: str,
    actor: Actor,
    document_id: UUID,
    *,
    scope: str,
    project_key: str | None = None,
) -> KnowledgeDocument | RecordProblem:
    validation = _read_scope_problem(scope, project_key)
    if validation is not None:
        return validation
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        authorization = _read_authority_problem(connection, actor, scope, project_key)
        if authorization is not None:
            return authorization
        row = connection.execute(
            """
            SELECT document_id, scope, title, body, registered_at, registered_by,
                   project_key, source_ref
            FROM knowledge_projection_documents
            WHERE tenant_id = %s AND document_id = %s AND scope = %s
              AND project_key IS NOT DISTINCT FROM %s
            """,
            (actor.tenant_id, document_id, scope, project_key),
        ).fetchone()
    if row is None:
        return RecordProblem(
            "tenant-scope-denied",
            "The requested knowledge document is unavailable in the authenticated scope.",
            404,
            "Knowledge document unavailable",
        )
    return _document_from_row(row)


def _document_from_row(row: dict[str, object]) -> KnowledgeDocument:
    project_key = row.get("project_key")
    source_ref = row.get("source_ref")
    return KnowledgeDocument(
        UUID(str(row["document_id"])),
        str(row["scope"]),
        str(row["title"]),
        str(row["body"]),
        cast(datetime, row["registered_at"]),
        UUID(str(row["registered_by"])),
        str(project_key) if project_key is not None else None,
        str(source_ref) if source_ref is not None else None,
    )


def _add_result(
    command: KnowledgeAddCommand,
    document_id: UUID,
    event_id: UUID,
    recorded_at: datetime,
    title: str,
) -> KnowledgeAddResult:
    return KnowledgeAddResult(
        command.client_command_id,
        document_id,
        event_id,
        recorded_at,
        command.scope,
        title,
        command.project_key,
        command.source_ref,
    )


def _write_authority_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: KnowledgeAddCommand,
) -> RecordProblem | None:
    if command.scope == "org":
        if actor.kind is PrincipalKind.OPERATOR:
            return None
        return RecordProblem(
            "auth-role-denied",
            "Org-scoped knowledge registration requires operator authority.",
            403,
            "Knowledge registration refused",
            command.client_command_id,
        )
    project_key = cast(str, command.project_key)
    if actor.kind is PrincipalKind.OPERATOR and command.origin in {
        EventOrigin.MIGRATION_IMPORTER,
        EventOrigin.ESTATE_IMPORT,
    }:
        return None
    return project_mutation_refusal(
        connection,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        command_id=command.client_command_id,
        project_keys=(project_key,),
    )


def _read_authority_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    scope: str,
    project_key: str | None,
) -> RecordProblem | None:
    if scope == "org":
        return None
    return project_scope_refusal(
        connection,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        project_keys=(cast(str, project_key),),
        allow_operator_read=True,
    )


def _read_scope_problem(scope: str, project_key: str | None) -> RecordProblem | None:
    if scope not in _SCOPES:
        return RecordProblem(
            "knowledge-invalid-scope",
            "Knowledge scope must be org or project.",
            422,
            "Knowledge query refused",
        )
    if scope == "org" and project_key is not None:
        return RecordProblem(
            "knowledge-invalid-project",
            "Org-scoped knowledge must not name a project.",
            422,
            "Knowledge query refused",
        )
    if scope == "project" and (project_key is None or _PROJECT_KEY.fullmatch(project_key) is None):
        return RecordProblem(
            "knowledge-invalid-project",
            "Project-scoped knowledge requires a valid project key.",
            422,
            "Knowledge query refused",
        )
    return None


def _resolve_content(
    source: KnowledgeSource | None,
    command: KnowledgeAddCommand,
) -> tuple[str, str] | RecordProblem:
    if (
        command.origin in {EventOrigin.MIGRATION_IMPORTER, EventOrigin.ESTATE_IMPORT}
        and command.body is not None
    ):
        return cast(str, command.title), command.body
    if command.source_ref is None:
        return cast(str, command.title), cast(str, command.body)
    if source is None:
        return _source_problem(command, "knowledge-source-unavailable", 503)
    try:
        document = source.get(scope=command.scope, ref=command.source_ref)
    except KnowledgeSourceUnavailableError:
        return _source_problem(command, "knowledge-source-unavailable", 503)
    if document is None:
        return _source_problem(command, "knowledge-source-not-found", 404)
    return document.title, document.body


def _source_problem(command: KnowledgeAddCommand, code: str, status: int) -> RecordProblem:
    return RecordProblem(
        code,
        "The requested static knowledge source could not be resolved.",
        status,
        "Knowledge source unavailable",
        command.client_command_id,
    )


def _persist_documents(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    body: str,
    result: KnowledgeAddResult,
) -> None:
    values = (
        result.document_id,
        actor.tenant_id,
        result.scope,
        result.project_key,
        result.title,
        body,
        result.source_ref,
        actor.principal_id,
        result.registered_at,
        result.event_id,
    )
    connection.execute(
        """
        INSERT INTO knowledge_documents (
            document_id, tenant_id, scope, project_key, title, body, source_ref,
            registered_by, registered_at, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        values,
    )
    connection.execute(
        """
        INSERT INTO knowledge_projection_documents (
            document_id, tenant_id, scope, project_key, title, body, source_ref,
            registered_by, registered_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        values[:-1],
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: KnowledgeAddCommand,
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
