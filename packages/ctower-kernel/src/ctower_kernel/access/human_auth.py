"""Human OIDC login, session lifecycle, and role-binding orchestration.

Split out of :class:`~ctower_kernel.access.interface.Access` to keep that class's own
public surface small: this is the human identity plane's cohesive behavior, reached
through the single ``Access.human`` attribute rather than a dozen more Access methods.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import httpx

from ctower_kernel.access import oidc
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.credentials import SeatCredentialReceipt
from ctower_kernel.record.human_identity import (
    HumanIdentityRecord,
    HumanRole,
    HumanRoleBindingIssue,
    HumanRoleBindingReceipt,
    HumanRoleBindingRevocation,
)
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__ = ["HumanAuthentication", "HumanBrowserSession", "HumanLoginResult", "LoginStart"]

_LOGIN_ATTEMPT_TTL_SECONDS = 600
_DEFAULT_SESSION_TTL_SECONDS = 43_200


@dataclass(frozen=True, slots=True)
class LoginStart:
    """What the login route needs to redirect the browser and set its attempt cookie."""

    authorization_url: str
    attempt_cookie: str


@dataclass(frozen=True, slots=True)
class HumanLoginResult:
    """What the callback route needs to set the session cookie and redirect."""

    actor: Actor
    csrf_token: str
    expires_at: datetime
    session_token: str


@dataclass(frozen=True, slots=True)
class HumanBrowserSession:
    """Exact browser authority proven by session cookie plus CSRF token."""

    actor: Actor
    human_binding_id: UUID
    human_session_id: UUID


class HumanAuthentication:
    """The human OIDC plane: PKCE login, opaque sessions, and role bindings."""

    def __init__(
        self,
        record: HumanIdentityRecord,
        *,
        oidc_providers: Mapping[str, oidc.OidcProvider] | None = None,
        oidc_http_client_factory: Callable[[], httpx.Client] | None = None,
        login_attempt_signing_key: bytes | None = None,
        session_ttl_seconds: int = _DEFAULT_SESSION_TTL_SECONDS,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._record = record
        self._oidc_providers = oidc_providers or {}
        self._oidc_http_client_factory = oidc_http_client_factory or httpx.Client
        self._login_attempt_signing_key = login_attempt_signing_key
        self._session_ttl_seconds = session_ttl_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    @property
    def provider_keys(self) -> frozenset[str]:
        """Return the configured provider keys without exposing their secrets."""

        return frozenset(self._oidc_providers)

    def begin_login(self, provider_key: str) -> LoginStart | RecordProblem:
        """Start one Authorization Code + PKCE S256 login against a configured provider."""

        signing_key = self._login_attempt_signing_key
        provider = self._oidc_providers.get(provider_key)
        if provider is None or signing_key is None:
            return _provider_unavailable("The requested OIDC provider is not configured.")
        with self._oidc_http_client_factory() as client:
            discovery = oidc.fetch_discovery_document(provider.issuer, client=client)
        if isinstance(discovery, RecordProblem):
            return discovery
        pkce = oidc.generate_pkce_pair()
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        url = oidc.authorization_url(
            provider, discovery, state=state, nonce=nonce, code_challenge=pkce.code_challenge
        )
        attempt_cookie = _sign_login_attempt(
            signing_key,
            provider_key=provider_key,
            state=state,
            nonce=nonce,
            code_verifier=pkce.code_verifier,
            expires_at=int(self._clock().timestamp()) + _LOGIN_ATTEMPT_TTL_SECONDS,
        )
        return LoginStart(authorization_url=url, attempt_cookie=attempt_cookie)

    def complete_login(
        self,
        attempt_cookie: str | None,
        *,
        code: str | None,
        state: str | None,
    ) -> HumanLoginResult | RecordProblem:
        """Exchange the callback code and resolve one bound human identity to an Actor."""

        attempt = self._verify_callback(attempt_cookie, code=code, state=state)
        if isinstance(attempt, RecordProblem):
            return attempt
        claims = self._exchange_and_verify(attempt, cast(str, code))
        if isinstance(claims, RecordProblem):
            return claims
        return self._issue_login_session(claims)

    def authenticate_session(self, session_cookie: str | None) -> Actor | RecordProblem:
        """Resolve one opaque human session cookie without retaining plaintext."""

        if not session_cookie:
            return _session_invalid("No session was presented.")
        digest = hashlib.sha256(session_cookie.encode()).digest()
        outcome = self._record.human_identity.actor_for_session(digest, now=self._clock())
        if outcome is None:
            return _session_invalid("The presented session is unknown.")
        return outcome

    def authenticate_browser_session(
        self, session_cookie: str | None, *, csrf_token: str | None
    ) -> HumanBrowserSession | RecordProblem:
        """Resolve a console browser only when cookie and CSRF proof match exactly."""

        if not session_cookie:
            return _session_invalid("No session was presented.")
        if not csrf_token or csrf_token.strip() != csrf_token:
            return _csrf_invalid()
        record = self._record.human_identity.browser_session(
            hashlib.sha256(session_cookie.encode()).digest(),
            hashlib.sha256(csrf_token.encode()).digest(),
            now=self._clock(),
        )
        if record is None:
            return _session_invalid("The presented session is unknown.")
        if isinstance(record, RecordProblem):
            return record
        actor = record.actor
        if (
            actor.human_binding_id != record.binding_id
            or actor.human_session_id != record.session_id
        ):
            raise RuntimeError("human browser session identity was not carried into Actor")
        return HumanBrowserSession(
            actor=actor,
            human_binding_id=record.binding_id,
            human_session_id=record.session_id,
        )

    def logout_session(self, session_cookie: str | None) -> None:
        """Revoke one human session; a missing or unknown cookie is a silent no-op."""

        if not session_cookie:
            return
        digest = hashlib.sha256(session_cookie.encode()).digest()
        self._record.human_identity.revoke_session(digest, reason="logout", now=self._clock())

    def bind_role(
        self,
        actor: Actor,
        command: HumanRoleBindingIssue,
        *,
        telemetry: TelemetryContext,
    ) -> HumanRoleBindingReceipt | RecordProblem:
        """Allow only the tenant operator to append one human role binding."""

        request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        outcome = self._record.human_identity.bind_role(
            actor, command, request_digest=request_digest, now=self._clock(), telemetry=telemetry
        )
        self._emit("access.bind_human_role", telemetry, outcome)
        return outcome

    def revoke_role(
        self,
        actor: Actor,
        command: HumanRoleBindingRevocation,
        *,
        telemetry: TelemetryContext,
    ) -> HumanRoleBindingReceipt | RecordProblem:
        """Allow only the tenant operator to append one human role binding revocation."""

        request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        outcome = self._record.human_identity.revoke_role(
            actor, command, request_digest=request_digest, now=self._clock(), telemetry=telemetry
        )
        self._emit("access.revoke_human_role", telemetry, outcome)
        return outcome

    def _verify_callback(
        self, attempt_cookie: str | None, *, code: str | None, state: str | None
    ) -> dict[str, str] | RecordProblem:
        if not code or not state:
            return _exchange_invalid("The callback carried no code or state.")
        attempt = self._verify_login_attempt(attempt_cookie)
        if isinstance(attempt, RecordProblem):
            return attempt
        if not hmac.compare_digest(attempt["state"], state):
            return _exchange_invalid("The callback state does not match the login attempt.")
        return attempt

    def _exchange_and_verify(
        self, attempt: dict[str, str], code: str
    ) -> oidc.IdTokenClaims | RecordProblem:
        provider = self._oidc_providers.get(attempt["provider_key"])
        if provider is None:
            return _provider_unavailable("The requested OIDC provider is not configured.")
        with self._oidc_http_client_factory() as client:
            discovery = oidc.fetch_discovery_document(provider.issuer, client=client)
            if isinstance(discovery, RecordProblem):
                return discovery
            tokens = oidc.exchange_code(
                provider,
                discovery,
                code=code,
                code_verifier=attempt["code_verifier"],
                client=client,
            )
            if isinstance(tokens, RecordProblem):
                return tokens
            jwks = oidc.fetch_jwks(discovery, client=client)
            if isinstance(jwks, RecordProblem):
                return jwks
            return oidc.verify_id_token(
                tokens.id_token,
                jwks=jwks,
                provider=provider,
                discovery=discovery,
                nonce=attempt["nonce"],
                now=int(self._clock().timestamp()),
            )

    def _issue_login_session(self, claims: oidc.IdTokenClaims) -> HumanLoginResult | RecordProblem:
        resolved = self._record.human_identity.resolve_role_binding(claims.issuer, claims.subject)
        if resolved is None:
            return RecordProblem(
                code="auth-identity-unresolved",
                detail="The verified identity has no active human role binding.",
                status=403,
                title="Identity unresolved",
            )
        binding_id, actor = resolved
        now = self._clock()
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        receipt = self._record.human_identity.issue_session(
            actor.principal_id,
            actor.tenant_id,
            binding_id,
            cast(HumanRole, actor.kind.value),
            session_digest=hashlib.sha256(session_token.encode()).digest(),
            csrf_digest=hashlib.sha256(csrf_token.encode()).digest(),
            now=now,
            ttl_seconds=self._session_ttl_seconds,
        )
        return HumanLoginResult(
            actor=actor,
            csrf_token=csrf_token,
            expires_at=receipt.expires_at,
            session_token=session_token,
        )

    def _verify_login_attempt(self, attempt_cookie: str | None) -> dict[str, str] | RecordProblem:
        signing_key = self._login_attempt_signing_key
        if not attempt_cookie or signing_key is None:
            return _exchange_invalid("No login attempt was presented.")
        decoded = _decode_login_attempt(signing_key, attempt_cookie)
        if isinstance(decoded, RecordProblem):
            return decoded
        expires_at = cast(int, decoded.get("expires_at", 0))
        if expires_at <= int(self._clock().timestamp()):
            return _exchange_invalid("The login attempt has expired.")
        return {
            "code_verifier": str(decoded["code_verifier"]),
            "nonce": str(decoded["nonce"]),
            "provider_key": str(decoded["provider_key"]),
            "state": str(decoded["state"]),
        }

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: SeatCredentialReceipt | HumanRoleBindingReceipt | RecordProblem,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    """Encode the string-only command contract in RFC 8785 canonical order."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _sign_login_attempt(
    signing_key: bytes,
    *,
    provider_key: str,
    state: str,
    nonce: str,
    code_verifier: str,
    expires_at: int,
) -> str:
    payload = _canonical_json(
        {
            "code_verifier": code_verifier,
            "expires_at": expires_at,
            "nonce": nonce,
            "provider_key": provider_key,
            "state": state,
        }
    )
    body = base64.urlsafe_b64encode(payload).decode("ascii")
    signature = hmac.new(signing_key, body.encode("ascii"), hashlib.sha256)
    return f"{body}.{signature.hexdigest()}"


def _decode_login_attempt(
    signing_key: bytes, attempt_cookie: str
) -> dict[str, object] | RecordProblem:
    body, _, signature = attempt_cookie.partition(".")
    if not body or not signature:
        return _exchange_invalid("The login attempt cookie is malformed.")
    expected = hmac.new(signing_key, body.encode("ascii"), hashlib.sha256)
    if not hmac.compare_digest(expected.hexdigest(), signature):
        return _exchange_invalid("The login attempt cookie failed verification.")
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode("ascii")))
    except ValueError:
        return _exchange_invalid("The login attempt cookie is malformed.")
    if not isinstance(payload, dict):
        return _exchange_invalid("The login attempt cookie is malformed.")
    return payload


def _provider_unavailable(detail: str) -> RecordProblem:
    return RecordProblem(
        code="auth-provider-unavailable",
        detail=detail,
        status=503,
        title="OIDC provider unavailable",
    )


def _exchange_invalid(detail: str) -> RecordProblem:
    return RecordProblem(
        code="auth-exchange-invalid", detail=detail, status=400, title="OIDC code exchange invalid"
    )


def _session_invalid(detail: str) -> RecordProblem:
    return RecordProblem(
        code="auth-session-invalid", detail=detail, status=401, title="Session invalid"
    )


def _csrf_invalid() -> RecordProblem:
    return RecordProblem(
        code="auth-csrf-invalid",
        detail="The browser CSRF proof is absent or does not match the session.",
        status=403,
        title="CSRF proof invalid",
    )
