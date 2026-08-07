"""Authenticated HTTP Adapter for registered knowledge documents."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import (
    UnscopedAuthentication,
    authenticate,
    encoded,
    problem_response,
    telemetry_context,
    uuid_value,
    validation_problem,
)
from ctower_api._mutation_response import mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import KnowledgeAddRequest
from ctower_client.models import KnowledgeAddResult as HttpKnowledgeAddResult
from ctower_client.models import KnowledgeDocument as HttpKnowledgeDocument
from ctower_client.models import KnowledgeDocumentList as HttpKnowledgeDocumentList
from ctower_kernel.access import Access
from ctower_kernel.knowledge import Knowledge, KnowledgeAddCommand
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope

__all__: tuple[str, ...] = ()


def install_knowledge_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    knowledge: Knowledge,
    recorder: TelemetryRecorder,
) -> None:
    _install_add_route(app, access, record, knowledge, recorder)
    _install_list_route(app, access, knowledge, recorder)
    _install_get_route(app, access, knowledge, recorder)


def _install_add_route(
    app: FastAPI,
    access: Access,
    record: Record,
    knowledge: Knowledge,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/knowledge/documents", status_code=201)
    async def add_knowledge_document(request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request, required_scope=CredentialScope.CAPTURE)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            payload = KnowledgeAddRequest.model_validate_json(await request.body())
            command = KnowledgeAddCommand(
                client_command_id=command_id,
                scope=payload.scope.value,
                body=payload.body,
                project_key=payload.project_key,
                source_ref=payload.source_ref,
                title=payload.title,
            )
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
        except (ValidationError, TypeError, ValueError):
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = knowledge.register(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=datetime.now(UTC),
            telemetry=telemetry,
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpKnowledgeAddResult,
            accepted_status=201,
        )


def _install_list_route(
    app: FastAPI,
    access: Access,
    knowledge: Knowledge,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/knowledge/documents")
    def list_knowledge_documents(
        request: Request,
        *,
        scope: str,
        project_key: str | None = None,
    ) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        outcome = knowledge.list_by_scope(actor, scope, project_key)
        if isinstance(outcome, RecordProblem):
            return problem_response(outcome)
        boundary = HttpKnowledgeDocumentList.model_validate_json(
            encoded(outcome.response_payload())
        )
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))


def _install_get_route(
    app: FastAPI,
    access: Access,
    knowledge: Knowledge,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/knowledge/documents/{document_id}")
    def get_knowledge_document(
        document_id: str,
        request: Request,
        *,
        scope: str,
        project_key: str | None = None,
    ) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            parsed_document_id = uuid_value(document_id)
        except ValueError:
            return problem_response(validation_problem())
        outcome = knowledge.get(
            actor,
            parsed_document_id,
            scope=scope,
            project_key=project_key,
        )
        if isinstance(outcome, RecordProblem):
            return problem_response(outcome)
        boundary = HttpKnowledgeDocument.model_validate_json(encoded(outcome.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()
