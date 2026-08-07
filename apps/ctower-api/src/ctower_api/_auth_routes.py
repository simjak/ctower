"""The five browser-plane routes D31 authorizes ahead of the I2.4 product surfaces.

Login, callback, session, logout, and auth-error are the sole browser exception to D23
(SPEC ``CT-I1-013``). They are plain server-driven redirects and a cookie exchange, so no
``apps/ctower-web`` framework decision is required to serve them. A raw browser
navigation cannot attach the ``X-Ctower-Telemetry-Context`` header every other route
requires, so these routes mint their own synthetic context instead of demanding one.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.responses import Response

from ctower_api._auth_page import unavailable_auth_page
from ctower_api._http_support import problem_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_kernel.access import Access
from ctower_kernel.access.interface import HumanLoginResult, LoginStart
from ctower_kernel.record import RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

LOGIN_ATTEMPT_COOKIE = "ctower_login_attempt"
SESSION_COOKIE = "__Host-ctower_session"
_LOGIN_ATTEMPT_MAX_AGE_SECONDS = 600


def install_auth_routes(app: FastAPI, access: Access, recorder: TelemetryRecorder) -> None:
    """Install the login/callback/logout/session routes for the human OIDC plane."""

    _install_login(app, access, recorder)
    _install_callback(app, access, recorder)
    _install_logout(app, access, recorder)
    _install_session(app, access, recorder)


def _install_login(app: FastAPI, access: Access, recorder: TelemetryRecorder) -> None:
    @app.get("/auth/login", response_model=None)
    async def login(
        request: Request, provider: str | None = None
    ) -> JSONResponse | RedirectResponse | Response:
        provider_key = provider or _sole_configured_provider(access)
        outcome = access.human.begin_login(provider_key or "")
        if isinstance(outcome, RecordProblem):
            _emit(recorder, "access.begin_human_login", outcome)
            if outcome.code == "auth-provider-unavailable" and _prefers_html(
                request.headers.get("accept", "")
            ):
                return unavailable_auth_page()
            return problem_response(outcome)
        return _redirect_to_provider(outcome)


def _install_callback(app: FastAPI, access: Access, recorder: TelemetryRecorder) -> None:
    @app.get("/auth/callback")
    async def callback(
        request: Request, code: str | None = None, state: str | None = None
    ) -> JSONResponse:
        attempt_cookie = request.cookies.get(LOGIN_ATTEMPT_COOKIE)
        outcome = access.human.complete_login(attempt_cookie, code=code, state=state)
        if isinstance(outcome, RecordProblem):
            _emit(recorder, "access.complete_human_login", outcome)
            return problem_response(outcome)
        _emit(recorder, "access.complete_human_login", outcome=None)
        return _authenticated_response(outcome)


def _install_logout(app: FastAPI, access: Access, recorder: TelemetryRecorder) -> None:
    @app.post("/auth/logout", status_code=204)
    async def logout(request: Request) -> JSONResponse:
        access.human.logout_session(request.cookies.get(SESSION_COOKIE))
        recorder.emit(
            "access.logout_session", _synthetic_telemetry(), outcome="ok", reason="logout"
        )
        response = JSONResponse(status_code=204, content=None)
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(LOGIN_ATTEMPT_COOKIE, path="/auth")
        return response


def _install_session(app: FastAPI, access: Access, recorder: TelemetryRecorder) -> None:
    @app.get("/auth/session")
    async def session(request: Request) -> JSONResponse:
        outcome = access.human.authenticate_session(request.cookies.get(SESSION_COOKIE))
        if isinstance(outcome, RecordProblem):
            _emit(recorder, "access.authenticate_session", outcome)
            return problem_response(outcome)
        recorder.emit(
            "access.authenticate_session", _synthetic_telemetry(), outcome="ok", reason="active"
        )
        return JSONResponse({"principal_id": str(outcome.principal_id), "role": outcome.kind.value})


def _sole_configured_provider(access: Access) -> str | None:
    keys = access.human.provider_keys
    return next(iter(keys)) if len(keys) == 1 else None


def _prefers_html(accept: str) -> bool:
    """Prefer HTML only when the caller ranks it above the JSON problem shape."""

    parsed = tuple(_accepted_media_ranges(accept))
    html = _offered_preference(parsed, "text/html")
    json = max(
        _offered_preference(parsed, "application/json"),
        _offered_preference(parsed, "application/problem+json"),
    )
    if html[0] <= 0 or html == json:
        return False
    return html > json


def _accepted_media_ranges(accept: str) -> list[tuple[str, float, int]]:
    accepted: list[tuple[str, float, int]] = []
    for position, item in enumerate(accept.split(",")):
        media_type, *parameters = (part.strip().lower() for part in item.split(";"))
        accepted.append((media_type, _quality(parameters), position))
    return accepted


def _quality(parameters: list[str]) -> float:
    quality = next(
        (parameter.partition("=")[2] for parameter in parameters if parameter.startswith("q=")),
        None,
    )
    if quality is None:
        return 1.0
    try:
        return float(quality)
    except ValueError:
        return 0.0


def _offered_preference(
    accepted: tuple[tuple[str, float, int], ...], offered: str
) -> tuple[float, int, int]:
    offered_type, offered_subtype = offered.split("/", maxsplit=1)
    matches: list[tuple[int, float, int]] = []
    for media_range, quality, position in accepted:
        range_type, separator, range_subtype = media_range.partition("/")
        if (
            separator
            and range_type in {"*", offered_type}
            and range_subtype
            in {
                "*",
                offered_subtype,
            }
        ):
            specificity = int(range_type != "*") + int(range_subtype != "*")
            matches.append((specificity, quality, position))
    if not matches:
        return (0.0, -1, 0)
    specificity = max(match[0] for match in matches)
    _, quality, position = min(
        (match for match in matches if match[0] == specificity), key=lambda match: match[2]
    )
    return (quality, specificity, -position)


def _redirect_to_provider(outcome: LoginStart) -> RedirectResponse:
    response = RedirectResponse(outcome.authorization_url, status_code=302)
    response.set_cookie(
        LOGIN_ATTEMPT_COOKIE,
        outcome.attempt_cookie,
        max_age=_LOGIN_ATTEMPT_MAX_AGE_SECONDS,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/auth",
    )
    return response


def _authenticated_response(outcome: HumanLoginResult) -> JSONResponse:
    max_age = int((outcome.expires_at - datetime.now(UTC)).total_seconds())
    response = JSONResponse(
        {
            "principal_id": str(outcome.actor.principal_id),
            "role": outcome.actor.kind.value,
            "expires_at": outcome.expires_at.isoformat(),
        }
    )
    response.set_cookie(
        SESSION_COOKIE,
        outcome.session_token,
        max_age=max(max_age, 0),
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.delete_cookie(LOGIN_ATTEMPT_COOKIE, path="/auth")
    return response


def _emit(recorder: TelemetryRecorder, name: str, outcome: RecordProblem | None) -> None:
    reason = outcome.code if outcome is not None else "authenticated"
    status = "error" if outcome is not None else "ok"
    recorder.emit(name, _synthetic_telemetry(), outcome=status, reason=reason)


def _synthetic_telemetry() -> TelemetryContext:
    """Mint a fresh context for a raw browser navigation with no telemetry header."""

    correlation_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=secrets.token_hex(16),
        span_id=secrets.token_hex(8),
        trace_flags=0,
        correlation_id=correlation_id,
        causation_id=correlation_id,
        tenant_id="unauthenticated",
        actor_id="unauthenticated",
        command_id=correlation_id,
    )
