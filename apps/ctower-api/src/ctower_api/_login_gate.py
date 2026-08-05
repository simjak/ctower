"""The gate middleware: present on every request, enforcing only when configured.

Unauthenticated browser navigations redirect to login; unauthenticated API requests
refuse with the same named ``unauthorized`` Problem every Bearer-less route already
returns. A request that presents *any* credential (a session cookie or an Authorization
header) always passes through unmodified — this gate only classifies the fully
unauthenticated case, so it can never re-decide a Bearer's validity behind a route's own
``access.authenticate`` call, and it can never disagree with that call.

Default state is present-but-not-enforcing: with ``enforcing=False`` (the default until
an operator flips it on) this middleware is a no-op, matching the interim tailnet-bind
guard rather than replacing it. It never widens the bind host, CORS, or network
boundary; it only adds a same-origin login redirect in front of what the tailnet/private
HTTPS boundary already restricts.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import quote

from fastapi import FastAPI, Request
from starlette.responses import RedirectResponse, Response

from ctower_api._auth_routes import SESSION_COOKIE
from ctower_api._http_support import problem_response
from ctower_kernel.record import RecordProblem

__all__: tuple[str, ...] = ()

_EXEMPT_PREFIXES = ("/auth/", "/health")


def install_login_gate(app: FastAPI, *, enforcing: bool) -> None:
    """Install the dark-by-default login gate as the outermost HTTP middleware."""

    @app.middleware("http")
    async def login_gate(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not enforcing or _is_exempt(request.url.path) or _presents_a_credential(request):
            return await call_next(request)
        if _wants_html(request):
            return RedirectResponse(_login_redirect_target(request), status_code=302)
        return problem_response(_unauthorized())


def _is_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


def _presents_a_credential(request: Request) -> bool:
    return (
        request.headers.get("authorization") is not None
        or request.cookies.get(SESSION_COOKIE) is not None
    )


def _wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


def _login_redirect_target(request: Request) -> str:
    return f"/auth/login?next={quote(str(request.url), safe='')}"


def _unauthorized() -> RecordProblem:
    return RecordProblem(
        code="unauthorized",
        detail="A valid tenant credential is required.",
        status=401,
        title="Authentication refused",
    )
