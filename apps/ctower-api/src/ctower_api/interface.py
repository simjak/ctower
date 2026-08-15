"""Thin HTTP composition over generated boundaries and kernel Interfaces."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.responses import Response

from ctower_api._auth_routes import install_auth_routes
from ctower_api._beat_dispatch_routes import BeatDispatchRuntime, install_beat_dispatch_routes
from ctower_api._catalog_routes import BundleCatalog
from ctower_api._comment_routes import install_comment_routes
from ctower_api._credential_routes import install_credential_routes
from ctower_api._custody_routes import install_custody_route
from ctower_api._cutover_routes import install_cutover_routes
from ctower_api._dream_dispatch_routes import (
    DreamDispatchRuntime,
    install_dream_dispatch_routes,
)
from ctower_api._http_support import (
    UnscopedAuthentication as _UnscopedAuthentication,
)
from ctower_api._http_support import (
    authenticate as _authenticate,
)
from ctower_api._http_support import (
    emit_auth_denial as _emit_auth_denial,
)
from ctower_api._http_support import (
    encoded as _encoded,
)
from ctower_api._http_support import (
    problem_response as _problem_response,
)
from ctower_api._http_support import (
    telemetry_context as _telemetry,
)
from ctower_api._http_support import (
    ticket_reference as _ticket_reference,
)
from ctower_api._http_support import (
    uuid_value as _uuid,
)
from ctower_api._http_support import (
    validation_problem as _validation_problem,
)
from ctower_api._intake_routes import install_intake_routes
from ctower_api._login_gate import install_login_gate
from ctower_api._migration_port import MigrationPort
from ctower_api._morning_digest_routes import install_morning_digest_routes
from ctower_api._mutation_response import mutation_response as _mutation_response
from ctower_api._optional_routes import install_optional_routes
from ctower_api._project_event_routes import install_project_event_routes
from ctower_api._request_cutover_routes import install_request_cutover_routes
from ctower_api._request_proposal_routes import install_request_proposal_routes
from ctower_api._request_routes import install_request_routes
from ctower_api._ruling_routes import install_ruling_routes
from ctower_api._session_routes import install_session_routes
from ctower_api._spawn_record_routes import install_spawn_record_routes
from ctower_api._synthetic_routes import SyntheticRuntime, install_synthetic_routes
from ctower_api._task_routes import install_task_routes
from ctower_api.console_routes import ConsoleRuntime, install_console_routes
from ctower_api.estate_import_port import EstateImportPort
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import BootstrapReceipt as HttpBootstrapReceipt
from ctower_client.models import (
    BootstrapRequest,
    TicketCreateRequest,
    TicketResource,
    TimelineResponse,
)
from ctower_client.models import TicketCommandResult as HttpTicketCommandResult
from ctower_kernel.access import Access
from ctower_kernel.access.oidc import OidcProvider
from ctower_kernel.attention import Attention
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.inbox import Inbox
from ctower_kernel.knowledge import Knowledge
from ctower_kernel.projections import Projections
from ctower_kernel.proof import Proof
from ctower_kernel.record import (
    Actor,
    BootstrapCommand,
    Record,
    RecordProblem,
    SourceReference,
    Ticket,
    TicketCommand,
    TicketCommandResult,
    TicketTimeline,
)
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.runtime import RoutineRevision
from ctower_kernel.runtime.spawn_records import PostgresSpawnRecords
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Intake, Work
from ctower_kernel.work.request_cutover import RequestCutover
from ctower_kernel.work.request_proposals import RequestProposals
from ctower_kernel.work.requests import Requests
from ctower_kernel.work.rulings import Rulings
from ctower_kernel.workflow import Workflow

__all__ = ["OidcRuntimeConfig", "create_app"]

type _MigrationImporterResolver = Callable[[bytes, UUID, UUID, str, datetime], Actor | None]
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


@dataclass(frozen=True, slots=True)
class OidcRuntimeConfig:
    """Deploy-time human OIDC wiring; absent fields mean no configured providers."""

    providers: dict[str, OidcProvider] | None = None
    http_client_factory: Callable[[], httpx.Client] | None = None
    login_attempt_signing_key: bytes | None = None
    gate_enforcing: bool = False


_DARK_OIDC_CONFIG = OidcRuntimeConfig()


def _project_key(value: str | None) -> str:
    if value is None or _PROJECT_KEY.fullmatch(value) is None:
        raise ValueError("invalid project key")
    return value


def _install_telemetry_health(app: FastAPI, recorder: TelemetryRecorder) -> None:
    """Report the recorder's own health on every response rather than in a side channel."""

    @app.middleware("http")
    async def telemetry_health(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Ctower-Telemetry-Health"] = recorder.health
        return response


def _build_access(
    record: Record,
    recorder: TelemetryRecorder,
    oidc: OidcRuntimeConfig,
    *,
    migration_importer_resolver: _MigrationImporterResolver | None,
    migration_importer_credential_resolver: Callable[[bytes, datetime], Actor | None] | None,
    fence_observer_resolver: Callable[[bytes, datetime], Actor | None] | None,
) -> Access:
    return Access(
        record,
        importer_resolver=migration_importer_resolver,
        importer_credential_resolver=migration_importer_credential_resolver,
        fence_observer_resolver=fence_observer_resolver,
        oidc_providers=oidc.providers,
        oidc_http_client_factory=oidc.http_client_factory,
        login_attempt_signing_key=oidc.login_attempt_signing_key,
        telemetry=recorder,
    )


def _app_runtime(telemetry: TelemetryRecorder | None) -> tuple[FastAPI, TelemetryRecorder]:
    return FastAPI(title="ctower control API", version="0.0.0"), telemetry or TelemetryRecorder()


def create_app(
    record: Record,
    *,
    proof: Proof | None = None,
    workflow: Workflow | None = None,
    work: Work | None = None,
    requests: Requests | None = None,
    request_proposals: RequestProposals | None = None,
    rulings: Rulings | None = None,
    request_cutover: RequestCutover | None = None,
    projections: Projections | None = None,
    attention: Attention | None = None,
    board_context: BoardContextFacts | None = None,
    inbox: Inbox | None = None,
    knowledge: Knowledge | None = None,
    estate_imports: EstateImportPort | None = None,
    catalog: BundleCatalog | None = None,
    synthetic_runtime: SyntheticRuntime | None = None,
    synthetic_revision: RoutineRevision | None = None,
    dream_dispatch_runtime: DreamDispatchRuntime | None = None,
    beat_dispatch_runtime: BeatDispatchRuntime | None = None,
    migration: object | None = None,
    migration_importer_resolver: _MigrationImporterResolver | None = None,
    migration_importer_credential_resolver: Callable[[bytes, datetime], Actor | None] | None = None,
    fence_observer_resolver: Callable[[bytes, datetime], Actor | None] | None = None,
    oidc: OidcRuntimeConfig = _DARK_OIDC_CONFIG,
    telemetry: TelemetryRecorder | None = None,
    console: ConsoleRuntime | None = None,
    spawn_records: PostgresSpawnRecords | None = None,
) -> FastAPI:
    """Compose the private command API without embedding durable decisions."""

    app, recorder = _app_runtime(telemetry)
    access = _build_access(
        record,
        recorder,
        oidc,
        migration_importer_resolver=migration_importer_resolver,
        migration_importer_credential_resolver=migration_importer_credential_resolver,
        fence_observer_resolver=fence_observer_resolver,
    )
    _install_application_routes(
        *(app, access, record, recorder, oidc),
        proof=proof,
        workflow=workflow,
        work=work,
        requests=requests,
        request_proposals=request_proposals,
        rulings=rulings,
        request_cutover=request_cutover,
        projections=projections,
        attention=attention,
        board_context=board_context,
        inbox=inbox,
        knowledge=knowledge,
        estate_imports=estate_imports,
        catalog=catalog,
    )
    _install_cutover_boundary(app, access, record, projections, migration, recorder)
    _install_synthetic_boundary(
        app, access, record, synthetic_runtime, synthetic_revision, recorder
    )
    _install_runtime_boundaries(
        app, access, record, dream_dispatch_runtime, beat_dispatch_runtime, console, recorder
    )
    _install_spawn_boundary(app, access, record, spawn_records, recorder)
    return app


def _install_spawn_boundary(
    app: FastAPI,
    access: Access,
    record: Record,
    spawn_records: PostgresSpawnRecords | None,
    recorder: TelemetryRecorder,
) -> None:
    return (
        install_spawn_record_routes(app, access, record, spawn_records, recorder)
        if spawn_records is not None
        else None
    )


def _install_application_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
    oidc: OidcRuntimeConfig,
    *,
    proof: Proof | None,
    workflow: Workflow | None,
    work: Work | None,
    requests: Requests | None,
    request_proposals: RequestProposals | None,
    rulings: Rulings | None,
    request_cutover: RequestCutover | None,
    projections: Projections | None,
    attention: Attention | None,
    board_context: BoardContextFacts | None,
    inbox: Inbox | None,
    knowledge: Knowledge | None,
    estate_imports: EstateImportPort | None,
    catalog: BundleCatalog | None,
) -> None:
    work_module = work or Work(record, telemetry=recorder)
    _install_telemetry_health(app, recorder)
    _install_core_routes(
        app,
        access,
        record,
        work_module,
        workflow,
        recorder,
        oidc,
        requests=requests,
        request_proposals=request_proposals,
        rulings=rulings,
        request_cutover=request_cutover,
        catalog=catalog,
    )
    _install_optional_routes(
        app,
        access,
        record,
        proof=proof,
        workflow=workflow,
        projections=projections,
        attention=attention,
        board_context=board_context,
        inbox=inbox,
        knowledge=knowledge,
        estate_imports=estate_imports,
        catalog=catalog,
        recorder=recorder,
    )


def _install_core_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    work: Work,
    workflow: Workflow | None,
    recorder: TelemetryRecorder,
    oidc: OidcRuntimeConfig,
    *,
    requests: Requests | None,
    request_proposals: RequestProposals | None,
    rulings: Rulings | None,
    request_cutover: RequestCutover | None,
    catalog: BundleCatalog | None,
) -> None:
    install_auth_routes(app, access, recorder)
    install_login_gate(app, enforcing=oidc.gate_enforcing)
    _install_access_routes(app, access, record, recorder)
    _install_ticket_create_route(app, access, record, work, recorder)
    install_custody_route(app, access, record, work, recorder)
    _install_ticket_read_routes(app, access, record, recorder)
    install_intake_routes(app, access, record, Intake(record, telemetry=recorder), recorder)
    if requests is not None:
        install_request_routes(app, access, record, requests, recorder)
    if requests is not None and request_proposals is not None:
        install_request_proposal_routes(
            app, access, record, request_proposals, requests, catalog=catalog, recorder=recorder
        )
    if rulings is not None:
        install_ruling_routes(app, access, record, rulings, recorder)
    if requests is not None and rulings is not None:
        install_morning_digest_routes(app, access, requests, rulings, request_proposals, recorder)
    if request_cutover is not None:
        install_request_cutover_routes(app, access, record, request_cutover, recorder)
    install_comment_routes(app, access, record, recorder)
    install_session_routes(app, access, record, recorder)
    install_project_event_routes(app, access, record, recorder)
    install_task_routes(app, access, record, work, workflow, recorder)


def _install_optional_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    *,
    proof: Proof | None,
    workflow: Workflow | None,
    projections: Projections | None,
    attention: Attention | None,
    board_context: BoardContextFacts | None,
    inbox: Inbox | None,
    knowledge: Knowledge | None,
    estate_imports: EstateImportPort | None,
    catalog: BundleCatalog | None,
    recorder: TelemetryRecorder,
) -> None:
    install_optional_routes(
        app,
        access,
        record,
        proof=proof,
        workflow=workflow,
        projections=projections,
        attention=attention,
        board_context=board_context,
        inbox=inbox,
        knowledge=knowledge,
        estate_imports=estate_imports,
        catalog=catalog,
        recorder=recorder,
    )


def _install_synthetic_boundary(
    app: FastAPI,
    access: Access,
    record: Record,
    synthetic_runtime: SyntheticRuntime | None,
    synthetic_revision: RoutineRevision | None,
    recorder: TelemetryRecorder,
) -> None:
    if (synthetic_runtime is None) is not (synthetic_revision is None):
        raise ValueError("synthetic runtime and revision must be composed together")
    if synthetic_runtime is not None and synthetic_revision is not None:
        install_synthetic_routes(
            app,
            access,
            record,
            synthetic_runtime,
            synthetic_revision,
            recorder,
        )


def _install_runtime_boundaries(
    app: FastAPI,
    access: Access,
    record: Record,
    dream_runtime: DreamDispatchRuntime | None,
    beat_runtime: BeatDispatchRuntime | None,
    console_runtime: ConsoleRuntime | None,
    recorder: TelemetryRecorder,
) -> None:
    if dream_runtime is not None:
        install_dream_dispatch_routes(app, access, record, dream_runtime, recorder)
    if beat_runtime is not None:
        install_beat_dispatch_routes(app, access, record, beat_runtime, recorder)
    if console_runtime is not None:
        install_console_routes(app, access, console_runtime)


def _install_access_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    _install_bootstrap_route(app, access, record, recorder)
    install_credential_routes(app, access, record, recorder)


def _install_cutover_boundary(
    app: FastAPI,
    access: Access,
    record: Record,
    projections: Projections | None,
    migration: object | None,
    recorder: TelemetryRecorder,
) -> None:
    if projections is None and migration is None:
        return
    install_cutover_routes(
        app,
        access,
        record,
        projections,
        cast(MigrationPort | None, migration),
        recorder,
    )


def _install_bootstrap_route(
    app: FastAPI, access: Access, record: Record, telemetry_recorder: TelemetryRecorder
) -> None:
    """Bind the local-only bootstrap transport Adapter."""

    @app.post("/v1/bootstrap/first-tenant", status_code=201)
    async def bootstrap_first_tenant(request: Request) -> JSONResponse:
        origin = request.client.host if request.client is not None else ""
        capability = request.headers.get("X-Ctower-Bootstrap-Capability")
        refusal = access.authorize_bootstrap(capability, origin=origin)
        if refusal is not None:
            _emit_auth_denial(telemetry_recorder, "access.authorize_bootstrap", refusal)
            return _problem_response(refusal)
        try:
            telemetry = _telemetry(request)
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = BootstrapRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        if capability is None:
            raise RuntimeError("authorized bootstrap capability disappeared")
        telemetry = telemetry.bind(
            tenant_id="unresolved",
            actor_id="bootstrap-installer",
            command_id=str(command_id),
        )
        telemetry_recorder.emit(
            "access.authorize_bootstrap", telemetry, outcome="ok", reason="authorized"
        )
        outcome = access.bootstrap_first_tenant(
            BootstrapCommand(
                client_command_id=command_id,
                commander_name=payload.commander_name,
                commander_vault_ref=payload.commander_vault_ref,
                operator_credential_ref=payload.operator_credential_ref,
                operator_name=payload.operator_name,
                operator_vault_ref=payload.operator_vault_ref,
                tenant_name=payload.tenant_name,
                tenant_slug=payload.tenant_slug,
            ),
            capability=capability,
            origin=origin,
            telemetry=telemetry,
        )
        if isinstance(outcome, RecordProblem):
            return _problem_response(outcome)
        return _mutation_response(
            record,
            outcome,
            tenant_id=outcome.tenant_id,
            principal_id=outcome.principal_id,
            command_id=outcome.command_id,
            telemetry=telemetry.bind(
                tenant_id=str(outcome.tenant_id),
                actor_id="bootstrap-installer",
                command_id=str(outcome.command_id),
            ),
            boundary_model=HttpBootstrapReceipt,
            accepted_status=201,
        )


def _install_ticket_create_route(
    app: FastAPI,
    access: Access,
    record: Record,
    work: Work,
    telemetry_recorder: TelemetryRecorder,
) -> None:
    """Bind the authenticated ticket command Adapter."""

    @app.post("/v1/tickets", status_code=201)
    async def create_ticket(request: Request) -> JSONResponse:
        actor = _authenticate(
            access,
            telemetry_recorder,
            request,
            required_scope=CredentialScope.CAPTURE,
        )
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            telemetry = _telemetry(request)
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = TicketCreateRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        telemetry_recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = work.create_ticket(
            actor,
            TicketCommand(
                client_command_id=command_id,
                initial_custodian_id=(
                    payload.initial_custodian_id
                    if payload.initial_custodian_id is not None
                    else actor.principal_id
                ),
                priority=payload.priority.value,
                project_key=payload.project_key,
                source=SourceReference(payload.source.kind, payload.source.ref),
                title=payload.title,
            ),
            telemetry=telemetry,
        )
        return _ticket_command_response(
            record, outcome, actor, command_id, telemetry, status_code=201
        )


def _install_ticket_read_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    telemetry_recorder: TelemetryRecorder,
) -> None:
    """Bind tenant-scoped ticket and timeline queries."""

    @app.get("/v1/tickets/{ticket_id}")
    def get_ticket(
        ticket_id: str, request: Request, project_key: str | None = None
    ) -> JSONResponse:
        actor = _authenticate(
            access,
            telemetry_recorder,
            request,
            required_scope=_UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            telemetry = _telemetry(request)
            parsed_ticket_id = _ticket_reference(ticket_id)
            parsed_project_key = _project_key(project_key)
        except ValueError:
            return _problem_response(_validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            ticket_id=str(parsed_ticket_id),
        )
        telemetry_recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        return _ticket_response(
            record.tickets.get(actor, parsed_ticket_id, parsed_project_key, telemetry=telemetry)
        )

    @app.get("/v1/tickets/{ticket_id}/timeline")
    def get_ticket_timeline(
        ticket_id: str, request: Request, project_key: str | None = None
    ) -> JSONResponse:
        actor = _authenticate(
            access,
            telemetry_recorder,
            request,
            required_scope=_UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            telemetry = _telemetry(request)
            parsed_ticket_id = _ticket_reference(ticket_id)
            parsed_project_key = _project_key(project_key)
        except ValueError:
            return _problem_response(_validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            ticket_id=str(parsed_ticket_id),
        )
        telemetry_recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        return _timeline_response(
            record.tickets.timeline(
                actor, parsed_ticket_id, parsed_project_key, telemetry=telemetry
            )
        )


def _ticket_command_response(
    record: Record,
    outcome: TicketCommandResult | RecordProblem,
    actor: Actor,
    command_id: UUID,
    telemetry: TelemetryContext,
    *,
    status_code: int,
) -> JSONResponse:
    return _mutation_response(
        record,
        outcome,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        command_id=command_id,
        telemetry=telemetry,
        boundary_model=HttpTicketCommandResult,
        accepted_status=status_code,
    )


def _ticket_response(outcome: Ticket | RecordProblem) -> JSONResponse:
    if isinstance(outcome, RecordProblem):
        return _problem_response(outcome)
    boundary = TicketResource.model_validate_json(_encoded(outcome.response_payload()))
    return JSONResponse(status_code=200, content=boundary.model_dump(mode="json"))


def _timeline_response(outcome: TicketTimeline | RecordProblem) -> JSONResponse:
    if isinstance(outcome, RecordProblem):
        return _problem_response(outcome)
    boundary = TimelineResponse.model_validate_json(_encoded(outcome.response_payload()))
    return JSONResponse(status_code=200, content=boundary.model_dump(mode="json"))
