"""PKCE login against a fake OIDC provider, and human session lifecycle."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256

from ctower_kernel.access import Access
from ctower_kernel.access.interface import HumanLoginResult, LoginStart
from ctower_kernel.access.oidc import OidcProvider
from ctower_kernel.record import Actor, PrincipalKind, Record, RecordProblem
from ctower_kernel.record.human_identity import HumanRoleBindingIssue
from ctower_kernel.telemetry import TelemetryContext

from ._fakes import FakeRecord

__all__: tuple[str, ...] = ()

_ISSUER = "https://fake-idp.example.test"
_CLIENT_ID = "ctower-test-client"
_REDIRECT_URI = "https://ctower.example.test/auth/callback"
_SIGNING_KEY = b"a-fixed-test-signing-key-not-a-real-secret"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class _FakeProvider:
    """A minimal but standard-shaped discovery/JWKS/token-endpoint trio.

    Authorization codes are single-use, matching real provider behavior, so a replayed
    code is refused exactly like an unknown one.
    """

    def __init__(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "kid-1"
        self._codes: dict[str, tuple[str, str, str]] = {}  # code -> (subject, challenge, nonce)

    def register_code(self, code: str, *, subject: str, code_challenge: str, nonce: str) -> None:
        self._codes[code] = (subject, code_challenge, nonce)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = urlsplit(str(request.url)).path
        if path == "/.well-known/openid-configuration":
            return self._discovery_response()
        if path == "/jwks":
            return self._jwks_response()
        if path == "/token":
            return self._token_response(request)
        raise AssertionError(f"unexpected fake-provider path: {path}")

    def _discovery_response(self) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "issuer": _ISSUER,
                "authorization_endpoint": f"{_ISSUER}/authorize",
                "token_endpoint": f"{_ISSUER}/token",
                "jwks_uri": f"{_ISSUER}/jwks",
            },
        )

    def _jwks_response(self) -> httpx.Response:
        numbers = self.private_key.public_key().public_numbers()
        n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
        e = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
        return httpx.Response(
            200,
            json={
                "keys": [
                    {"kty": "RSA", "use": "sig", "kid": self.kid, "n": _b64url(n), "e": _b64url(e)}
                ]
            },
        )

    def _token_response(self, request: httpx.Request) -> httpx.Response:
        body = parse_qs(request.content.decode("ascii"))
        code = body["code"][0]
        entry = self._codes.pop(code, None)
        if entry is None:
            return httpx.Response(400, json={"error": "invalid_grant"})
        subject, expected_challenge, nonce = entry
        verifier = body["code_verifier"][0]
        actual_challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        if actual_challenge != expected_challenge:
            return httpx.Response(400, json={"error": "invalid_grant"})
        id_token = self._sign_id_token(subject=subject, audience=body["client_id"][0], nonce=nonce)
        return httpx.Response(200, json={"id_token": id_token})

    def _sign_id_token(self, *, subject: str, audience: str, nonce: str) -> str:
        now = int(time.time())
        claims = {
            "iss": _ISSUER,
            "sub": subject,
            "aud": audience,
            "exp": now + 300,
            "iat": now,
            "nonce": nonce,
        }
        header = _b64url(json.dumps({"alg": "RS256", "kid": self.kid}).encode())
        payload = _b64url(json.dumps(claims).encode())
        signing_input = f"{header}.{payload}".encode("ascii")
        signature = self.private_key.sign(signing_input, padding.PKCS1v15(), SHA256())
        return f"{header}.{payload}.{_b64url(signature)}"


def _provider_config() -> OidcProvider:
    return OidcProvider(
        provider_key="fake-idp",
        issuer=_ISSUER,
        client_id=_CLIENT_ID,
        client_secret="s3cr3t",  # noqa: S106 - fake test fixture, not a real secret
        redirect_uri=_REDIRECT_URI,
    )


def _build_access(
    fake_provider: _FakeProvider,
    *,
    record: FakeRecord,
    clock: Callable[[], datetime] | None = None,
) -> Access:
    def client_factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(fake_provider.handler))

    return Access(
        cast(Record, record),
        oidc_providers={"fake-idp": _provider_config()},
        oidc_http_client_factory=client_factory,
        login_attempt_signing_key=_SIGNING_KEY,
        clock=clock,
    )


def _bind_operator_role(record: FakeRecord, *, oidc_subject: str) -> None:
    operator = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    command = HumanRoleBindingIssue(
        client_command_id=uuid4(),
        display_name="Test Operator",
        oidc_issuer=_ISSUER,
        oidc_subject=oidc_subject,
        project_keys=(),
        role="operator",
    )
    receipt = record.human_identity.bind_role(
        operator, command, request_digest=b"0" * 32, now=datetime.now(UTC), telemetry=_telemetry()
    )
    assert not isinstance(receipt, RecordProblem)


def _telemetry() -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=0,
        correlation_id=str(uuid4()),
        causation_id=str(uuid4()),
        tenant_id="test",
        actor_id="test",
        command_id=str(uuid4()),
    )


def _begin_login(access: Access) -> tuple[LoginStart, str, str, str]:
    """Return the login start plus the code_challenge/state/nonce it embedded."""

    start = access.human.begin_login("fake-idp")
    assert isinstance(start, LoginStart)
    query = parse_qs(urlsplit(start.authorization_url).query)
    return start, query["code_challenge"][0], query["state"][0], query["nonce"][0]


def _complete_login(
    access: Access, fake_provider: _FakeProvider, *, subject: str
) -> HumanLoginResult | RecordProblem:
    start, code_challenge, state, nonce = _begin_login(access)
    code = "authorization-code-" + uuid4().hex
    fake_provider.register_code(code, subject=subject, code_challenge=code_challenge, nonce=nonce)
    return access.human.complete_login(start.attempt_cookie, code=code, state=state)


def test_pkce_login_resolves_a_bound_identity_to_its_role() -> None:
    record = FakeRecord()
    _bind_operator_role(record, oidc_subject="user-1")
    fake_provider = _FakeProvider()
    access = _build_access(fake_provider, record=record)

    outcome = _complete_login(access, fake_provider, subject="user-1")

    assert isinstance(outcome, HumanLoginResult)
    assert outcome.actor.kind is PrincipalKind.OPERATOR
    assert outcome.session_token


def test_pkce_login_refuses_a_replayed_authorization_code() -> None:
    record = FakeRecord()
    _bind_operator_role(record, oidc_subject="user-1")
    fake_provider = _FakeProvider()
    access = _build_access(fake_provider, record=record)
    start, code_challenge, state, nonce = _begin_login(access)
    code = "authorization-code-" + uuid4().hex
    fake_provider.register_code(code, subject="user-1", code_challenge=code_challenge, nonce=nonce)
    first = access.human.complete_login(start.attempt_cookie, code=code, state=state)
    assert isinstance(first, HumanLoginResult)

    replay = access.human.complete_login(start.attempt_cookie, code=code, state=state)

    assert isinstance(replay, RecordProblem)
    assert replay.code == "auth-exchange-invalid"


def test_login_refuses_unresolved_identity_with_named_code() -> None:
    record = FakeRecord()
    fake_provider = _FakeProvider()
    access = _build_access(fake_provider, record=record)

    outcome = _complete_login(access, fake_provider, subject="stranger")

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-identity-unresolved"


def test_login_refuses_unconfigured_provider_with_named_code() -> None:
    record = FakeRecord()
    access = _build_access(_FakeProvider(), record=record)

    outcome = access.human.begin_login("no-such-provider")

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unavailable"


def test_login_refuses_state_mismatch() -> None:
    record = FakeRecord()
    _bind_operator_role(record, oidc_subject="user-1")
    fake_provider = _FakeProvider()
    access = _build_access(fake_provider, record=record)
    start, code_challenge, state, nonce = _begin_login(access)
    code = "authorization-code-" + uuid4().hex
    fake_provider.register_code(code, subject="user-1", code_challenge=code_challenge, nonce=nonce)

    outcome = access.human.complete_login(
        start.attempt_cookie, code=code, state=state + "-tampered"
    )

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-exchange-invalid"


def test_login_refuses_missing_attempt_cookie() -> None:
    record = FakeRecord()
    access = _build_access(_FakeProvider(), record=record)

    outcome = access.human.complete_login(None, code="c", state="s")

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-exchange-invalid"


def test_login_refuses_expired_attempt_cookie() -> None:
    record = FakeRecord()
    _bind_operator_role(record, oidc_subject="user-1")
    fake_provider = _FakeProvider()
    clock_time = [datetime(2026, 1, 1, tzinfo=UTC)]
    access = _build_access(fake_provider, record=record, clock=lambda: clock_time[0])
    start, _code_challenge, state, _nonce = _begin_login(access)
    clock_time[0] = clock_time[0] + timedelta(hours=1)

    outcome = access.human.complete_login(start.attempt_cookie, code="whatever", state=state)

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-exchange-invalid"


def test_session_lifecycle_authenticate_then_logout_then_refused() -> None:
    record = FakeRecord()
    _bind_operator_role(record, oidc_subject="user-1")
    fake_provider = _FakeProvider()
    access = _build_access(fake_provider, record=record)
    login = _complete_login(access, fake_provider, subject="user-1")
    assert isinstance(login, HumanLoginResult)

    active = access.human.authenticate_session(login.session_token)
    assert not isinstance(active, RecordProblem)
    assert active.kind is PrincipalKind.OPERATOR

    access.human.logout_session(login.session_token)

    after_logout = access.human.authenticate_session(login.session_token)
    assert isinstance(after_logout, RecordProblem)
    assert after_logout.code == "auth-session-invalid"


def test_session_lifecycle_expiry_requires_reauthentication() -> None:
    # The fake provider signs ID tokens against real wall-clock time (like a real IdP
    # would), so the access clock must start there too or a fixed past clock makes the
    # token look "issued in the future" before expiry is ever exercised.
    record = FakeRecord()
    _bind_operator_role(record, oidc_subject="user-1")
    fake_provider = _FakeProvider()
    clock_time = [datetime.now(UTC)]
    access = _build_access(fake_provider, record=record, clock=lambda: clock_time[0])
    login = _complete_login(access, fake_provider, subject="user-1")
    assert isinstance(login, HumanLoginResult)
    clock_time[0] = clock_time[0] + timedelta(days=2)

    outcome = access.human.authenticate_session(login.session_token)

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "reauthentication-required"


def test_authenticate_session_refuses_missing_cookie() -> None:
    record = FakeRecord()
    access = _build_access(_FakeProvider(), record=record)

    outcome = access.human.authenticate_session(None)

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-session-invalid"


def test_logout_of_unknown_session_is_a_silent_no_op() -> None:
    record = FakeRecord()
    access = _build_access(_FakeProvider(), record=record)

    access.human.logout_session("never-issued-token")  # must not raise
