"""Authenticated same-origin browser and operator routes for Console Phase 1."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Annotated, Literal
from urllib.parse import SplitResult, urlsplit
from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ctower_api._auth_routes import CSRF_COOKIE, SESSION_COOKIE
from ctower_api._http_support import problem_response
from ctower_api.console_network import ConsoleListenerError, validate_bind_host
from ctower_kernel.access import Access
from ctower_kernel.console import (
    ConsoleGlobalSwitchCommand,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleViewer,
    ConsoleViewGrant,
)
from ctower_kernel.record import Actor, RecordProblem

__all__ = ["ConsoleRuntime", "install_console_routes", "validate_console_origin"]

_CSRF_HEADER = "X-Ctower-CSRF"


@dataclass(frozen=True, slots=True)
class ConsoleRuntime:
    """Paired server viewer and its one exact private browser origin."""

    viewer: ConsoleViewer
    expected_origin: str

    def __post_init__(self) -> None:
        """Reject any origin that cannot also be the exact private listener."""

        _console_origin_listener(self.expected_origin)

    @property
    def listener_host(self) -> str:
        """Return the already-validated literal listener host."""

        return _console_origin_listener(self.expected_origin)[0]

    @property
    def listener_port(self) -> int:
        """Return the already-validated exact listener port."""

        return _console_origin_listener(self.expected_origin)[1]


def _console_origin_listener(origin: str) -> tuple[str, int]:
    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError as error:
        raise ConsoleListenerError("console origin port is invalid") from error
    if not _is_exact_https_origin(parsed, port):
        raise ConsoleListenerError("console origin must be an exact HTTPS private address and port")
    hostname = parsed.hostname
    if hostname is None or port is None:  # pragma: no cover - predicate proves both
        raise ConsoleListenerError("console origin has no listener address")
    validate_bind_host(hostname)
    return hostname, port


def _is_exact_https_origin(origin: SplitResult, port: int | None) -> bool:
    return (
        origin.scheme == "https"
        and origin.hostname is not None
        and origin.username is None
        and origin.password is None
        and port is not None
        and not origin.path
        and not origin.query
        and not origin.fragment
    )


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _AllowRequest(_StrictModel):
    adapter_key: Literal["tmux-v1"]
    assignment_interval_sequence: int = Field(ge=1)
    assignment_kind: str = Field(min_length=1, max_length=128)
    assignment_ticket_id: UUID
    backend_incarnation: str = Field(min_length=1, max_length=128)
    crew_name: str = Field(pattern=r"^[a-z][a-z0-9._-]{1,95}$")
    loop_kind: Literal["standard"]
    opaque_backend_ref: str = Field(min_length=1, max_length=256)
    project_key: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    recorded_work_session_id: UUID
    runner_epoch: int = Field(ge=1)
    runner_id: str = Field(min_length=1, max_length=128)
    runtime_attempt_id: UUID
    seat_principal_id: UUID
    sensitivity_class: Literal["restricted"]


class _RevocationRequest(_StrictModel):
    reason: str = Field(min_length=1, max_length=500)


class _SwitchRequest(_StrictModel):
    enabled: bool
    reason: str = Field(min_length=1, max_length=500)


def install_console_routes(
    app: FastAPI,
    access: Access,
    runtime: ConsoleRuntime,
) -> None:
    """Mount the exact browser and operator Console boundary."""

    _install_admin_routes(app, access, runtime.viewer)
    _install_browser_routes(app, access, runtime.viewer, expected_origin=runtime.expected_origin)


def _install_admin_routes(app: FastAPI, access: Access, console: ConsoleViewer) -> None:
    """Mount the bearer-authenticated operator fact routes."""

    @app.post("/v1/admin/console/sessions", status_code=201)
    async def allow_session(request: Request) -> JSONResponse:
        return await _allow_session_response(request, access, console)

    @app.post("/v1/admin/console/sessions/{console_session_id}/revocation", status_code=204)
    async def revoke_session(console_session_id: UUID, request: Request) -> Response:
        return await _revoke_session_response(request, access, console, console_session_id)

    @app.post("/v1/admin/console/kill-switch", status_code=204)
    async def set_kill_switch(request: Request) -> Response:
        return await _switch_response(request, access, console)


async def _allow_session_response(
    request: Request, access: Access, console: ConsoleViewer
) -> JSONResponse:
    actor = access.authenticate(request.headers.get("Authorization"))
    if isinstance(actor, RecordProblem):
        return problem_response(actor)
    try:
        payload = _AllowRequest.model_validate_json(await request.body())
        ref = _session_ref(actor, payload)
    except (ValidationError, TypeError, ValueError):
        return problem_response(_validation_problem())
    outcome = console.allow_session(
        actor,
        ConsoleSessionAllowCommand(ref, payload.sensitivity_class, payload.loop_kind),
    )
    return (
        problem_response(outcome)
        if isinstance(outcome, RecordProblem)
        else JSONResponse(outcome.response_payload(), status_code=201)
    )


def _session_ref(actor: Actor, payload: _AllowRequest) -> ConsoleSessionRef:
    return ConsoleSessionRef(
        tenant_id=actor.tenant_id,
        project_key=payload.project_key,
        seat_principal_id=payload.seat_principal_id,
        crew_name=payload.crew_name,
        assignment_ticket_id=payload.assignment_ticket_id,
        assignment_kind=payload.assignment_kind,
        assignment_interval_sequence=payload.assignment_interval_sequence,
        recorded_work_session_id=payload.recorded_work_session_id,
        runtime_attempt_id=payload.runtime_attempt_id,
        runner_id=payload.runner_id,
        runner_epoch=payload.runner_epoch,
        adapter_key=payload.adapter_key,
        opaque_backend_ref=payload.opaque_backend_ref,
        backend_incarnation=payload.backend_incarnation,
    )


async def _revoke_session_response(
    request: Request,
    access: Access,
    console: ConsoleViewer,
    console_session_id: UUID,
) -> Response:
    actor = access.authenticate(request.headers.get("Authorization"))
    if isinstance(actor, RecordProblem):
        return problem_response(actor)
    try:
        payload = _RevocationRequest.model_validate_json(await request.body())
    except ValidationError:
        return problem_response(_validation_problem())
    outcome = console.revoke_session(
        actor, ConsoleSessionRevocation(console_session_id, payload.reason)
    )
    return _empty_response(outcome)


async def _switch_response(request: Request, access: Access, console: ConsoleViewer) -> Response:
    actor = access.authenticate(request.headers.get("Authorization"))
    if isinstance(actor, RecordProblem):
        return problem_response(actor)
    try:
        payload = _SwitchRequest.model_validate_json(await request.body())
    except ValidationError:
        return problem_response(_validation_problem())
    outcome = console.set_global_switch(
        actor, ConsoleGlobalSwitchCommand(payload.enabled, payload.reason)
    )
    return _empty_response(outcome)


def _empty_response(outcome: RecordProblem | None) -> Response:
    return (
        problem_response(outcome)
        if isinstance(outcome, RecordProblem)
        else Response(status_code=204)
    )


def _install_browser_routes(
    app: FastAPI,
    access: Access,
    console: ConsoleViewer,
    *,
    expected_origin: str,
) -> None:
    """Mount the exact-origin session/CSRF browser routes."""

    @app.get("/v1/console/sessions")
    async def visible_sessions(
        request: Request,
        csrf: Annotated[str | None, Header(alias=_CSRF_HEADER)] = None,
    ) -> JSONResponse:
        return _visible_sessions_response(
            request, access, console, csrf=csrf, expected_origin=expected_origin
        )

    @app.post("/v1/console/sessions/{console_session_id}/grants")
    async def mint_grant(
        console_session_id: UUID,
        request: Request,
        csrf: Annotated[str | None, Header(alias=_CSRF_HEADER)] = None,
    ) -> JSONResponse:
        return _grant_response(
            request,
            access,
            console,
            console_session_id,
            csrf=csrf,
            expected_origin=expected_origin,
            renewal=False,
        )

    @app.post("/v1/console/sessions/{console_session_id}/renewals")
    async def renew_grant(
        console_session_id: UUID,
        request: Request,
        csrf: Annotated[str | None, Header(alias=_CSRF_HEADER)] = None,
    ) -> JSONResponse:
        return _grant_response(
            request,
            access,
            console,
            console_session_id,
            csrf=csrf,
            expected_origin=expected_origin,
            renewal=True,
        )

    @app.get("/v1/console/sessions/{console_session_id}/events", response_model=None)
    async def stream_events(
        console_session_id: UUID,
        request: Request,
        csrf: Annotated[str | None, Header(alias=_CSRF_HEADER)] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> JSONResponse | StreamingResponse:
        return _stream_response(
            request,
            access,
            console,
            console_session_id,
            csrf=csrf,
            expected_origin=expected_origin,
            last_event_id=last_event_id,
        )


def _visible_sessions_response(
    request: Request,
    access: Access,
    console: ConsoleViewer,
    *,
    csrf: str | None,
    expected_origin: str,
) -> JSONResponse:
    actor = _browser_actor(request, access, csrf=csrf, expected_origin=expected_origin)
    if isinstance(actor, RecordProblem):
        return problem_response(actor)
    outcome = console.visible_sessions(actor)
    if isinstance(outcome, RecordProblem):
        return problem_response(outcome)
    return JSONResponse({"sessions": [item.response_payload() for item in outcome]})


def _stream_response(
    request: Request,
    access: Access,
    console: ConsoleViewer,
    console_session_id: UUID,
    *,
    csrf: str | None,
    expected_origin: str,
    last_event_id: str | None,
) -> JSONResponse | StreamingResponse:
    if request.url.query:
        return problem_response(
            RecordProblem(
                code="console-stream-query-refused",
                detail="The Console stream URL cannot carry query parameters.",
                status=422,
                title="Console stream query refused",
            )
        )
    actor = _browser_actor(request, access, csrf=csrf, expected_origin=expected_origin)
    if isinstance(actor, RecordProblem):
        return problem_response(actor)
    cursor = _last_event_cursor(last_event_id)
    if isinstance(cursor, RecordProblem):
        return problem_response(cursor)
    outcome = console.open_stream(actor, console_session_id, last_event_id=cursor)
    if isinstance(outcome, RecordProblem):
        return problem_response(outcome)
    return StreamingResponse(
        outcome.events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _last_event_cursor(value: str | None) -> int | RecordProblem | None:
    if value is None:
        return None
    try:
        cursor = int(value)
    except ValueError:
        cursor = -1
    if cursor < 0:
        return RecordProblem(
            code="console-cursor-invalid",
            detail="Last-Event-ID must be a non-negative durable cursor.",
            status=422,
            title="Console cursor invalid",
        )
    return cursor


def validate_console_origin(presented: str | None, *, expected: str) -> RecordProblem | None:
    """Require one exact Origin and reveal no prefix/wildcard comparison."""

    if presented is None or not hmac.compare_digest(presented, expected):
        return RecordProblem(
            code="console-origin-refused",
            detail="The browser Origin does not match the configured private Console origin.",
            status=403,
            title="Console Origin refused",
        )
    return None


def _browser_actor(
    request: Request,
    access: Access,
    *,
    csrf: str | None,
    expected_origin: str,
) -> Actor | RecordProblem:
    origin_problem = validate_console_origin(
        request.headers.get("Origin"), expected=expected_origin
    )
    if origin_problem is not None:
        return origin_problem
    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    if csrf is None or csrf_cookie is None or not hmac.compare_digest(csrf, csrf_cookie):
        return RecordProblem(
            code="console-csrf-invalid",
            detail="The browser CSRF proof is missing or does not match its secure cookie.",
            status=403,
            title="Console CSRF refused",
        )
    outcome = access.human.authenticate_browser_session(
        request.cookies.get(SESSION_COOKIE), csrf_token=csrf
    )
    return outcome if isinstance(outcome, RecordProblem) else outcome.actor


def _grant_response(
    request: Request,
    access: Access,
    console: ConsoleViewer,
    console_session_id: UUID,
    *,
    csrf: str | None,
    expected_origin: str,
    renewal: bool,
) -> JSONResponse:
    actor = _browser_actor(request, access, csrf=csrf, expected_origin=expected_origin)
    if isinstance(actor, RecordProblem):
        return problem_response(actor)
    outcome = console.mint_grant(actor, console_session_id, renewal=renewal)
    if isinstance(outcome, RecordProblem):
        return problem_response(outcome)
    return JSONResponse(_grant_payload(outcome), status_code=201)


def _grant_payload(grant: ConsoleViewGrant) -> dict[str, object]:
    return {
        "grant_id": str(grant.grant_id),
        "console_session_id": str(grant.allowance_id),
        "project_key": grant.project_key,
        "policy_revision": grant.policy_revision,
        "not_before": grant.not_before.isoformat(),
        "expires_at": grant.expires_at.isoformat(),
        "maximum_uses": grant.maximum_uses,
        "renewed_from_grant_id": (
            None if grant.renewed_from_grant_id is None else str(grant.renewed_from_grant_id)
        ),
    }


def _validation_problem() -> RecordProblem:
    return RecordProblem(
        code="validation-error",
        detail="The request does not satisfy the strict Console contract.",
        status=422,
        title="Validation failed",
    )
