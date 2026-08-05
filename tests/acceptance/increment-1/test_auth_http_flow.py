"""End-to-end HTTP proof of the login/callback/session/logout cookie exchange.

Role binding uses the in-process ``Access.bind_human_role`` against a real Postgres
Record (there is no HTTP admin route for it yet — a named gap in the scaffold's status
file), and the OIDC provider is a fake discovery/JWKS/token-endpoint trio reached
through an injected ``httpx.MockTransport``. Everything else is the real FastAPI app.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import UTC, datetime
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256
from fastapi import FastAPI
from fastapi.testclient import TestClient
from support.tenant_fixture import TenantFixture

from ctower_api.interface import OidcRuntimeConfig, create_app
from ctower_kernel.access.oidc import OidcProvider
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.human_identity import HumanRoleBindingIssue
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_ISSUER = "https://fake-idp.example.test"
_CLIENT_ID = "ctower-test-client"
_REDIRECT_URI = "https://ctower.example.test/auth/callback"
_SIGNING_KEY = b"http-flow-fixed-test-signing-key-not-a-real-secret"
_SESSION_COOKIE = "__Host-ctower_session"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class _FakeProvider:
    def __init__(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "kid-1"
        self._codes: dict[str, tuple[str, str, str]] = {}

    def register_code(self, code: str, *, subject: str, code_challenge: str, nonce: str) -> None:
        self._codes[code] = (subject, code_challenge, nonce)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = urlsplit(str(request.url)).path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": _ISSUER,
                    "authorization_endpoint": f"{_ISSUER}/authorize",
                    "token_endpoint": f"{_ISSUER}/token",
                    "jwks_uri": f"{_ISSUER}/jwks",
                },
            )
        if path == "/jwks":
            numbers = self.private_key.public_key().public_numbers()
            n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
            e = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
            key = {"kty": "RSA", "use": "sig", "kid": self.kid, "n": _b64url(n), "e": _b64url(e)}
            return httpx.Response(200, json={"keys": [key]})
        if path == "/token":
            return self._token_response(request)
        raise AssertionError(f"unexpected fake-provider path: {path}")

    def _token_response(self, request: httpx.Request) -> httpx.Response:
        body = parse_qs(request.content.decode("ascii"))
        entry = self._codes.pop(body["code"][0], None)
        if entry is None:
            return httpx.Response(400, json={"error": "invalid_grant"})
        subject, expected_challenge, nonce = entry
        actual_challenge = _b64url(hashlib.sha256(body["code_verifier"][0].encode()).digest())
        if actual_challenge != expected_challenge:
            return httpx.Response(400, json={"error": "invalid_grant"})
        now = int(time.time())
        claims = {
            "iss": _ISSUER,
            "sub": subject,
            "aud": body["client_id"][0],
            "exp": now + 300,
            "iat": now,
            "nonce": nonce,
        }
        header = _b64url(json.dumps({"alg": "RS256", "kid": self.kid}).encode())
        payload = _b64url(json.dumps(claims).encode())
        signing_input = f"{header}.{payload}".encode("ascii")
        signature = self.private_key.sign(signing_input, padding.PKCS1v15(), SHA256())
        return httpx.Response(200, json={"id_token": f"{header}.{payload}.{_b64url(signature)}"})


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


def _build_app(fake_provider: _FakeProvider, *, record: PostgresRecord) -> FastAPI:
    def client_factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(fake_provider.handler))

    return create_app(
        record,
        oidc=OidcRuntimeConfig(
            providers={
                "fake-idp": OidcProvider(
                    provider_key="fake-idp",
                    issuer=_ISSUER,
                    client_id=_CLIENT_ID,
                    client_secret="s3cr3t",  # noqa: S106 - fake test fixture, not a real secret
                    redirect_uri=_REDIRECT_URI,
                )
            },
            http_client_factory=client_factory,
            login_attempt_signing_key=_SIGNING_KEY,
        ),
    )


def test_full_login_callback_session_logout_http_round_trip(tenant: TenantFixture) -> None:
    record = PostgresRecord(tenant.database.runtime_dsn)
    fake_provider = _FakeProvider()
    app = _build_app(fake_provider, record=record)

    with TestClient(app, base_url="https://testserver", follow_redirects=False) as client:
        started = client.get("/auth/login", params={"provider": "fake-idp"})
        assert started.status_code == HTTPStatus.FOUND
        location = urlsplit(started.headers["location"])
        query = parse_qs(location.query)
        code = "code-" + uuid4().hex
        fake_provider.register_code(
            code,
            subject="user-http-flow",
            code_challenge=query["code_challenge"][0],
            nonce=query["nonce"][0],
        )

        unresolved = client.get("/auth/callback", params={"code": code, "state": query["state"][0]})
        assert unresolved.status_code == HTTPStatus.FORBIDDEN
        assert unresolved.json()["code"] == "auth-identity-unresolved"

    # Now bind the identity out-of-band (no HTTP admin route exists yet) and log in again.
    _bind_role(record, tenant, subject="user-http-flow")
    with TestClient(app, base_url="https://testserver", follow_redirects=False) as client:
        started = client.get("/auth/login", params={"provider": "fake-idp"})
        query = parse_qs(urlsplit(started.headers["location"]).query)
        code = "code-" + uuid4().hex
        fake_provider.register_code(
            code,
            subject="user-http-flow",
            code_challenge=query["code_challenge"][0],
            nonce=query["nonce"][0],
        )

        callback = client.get("/auth/callback", params={"code": code, "state": query["state"][0]})
        assert callback.status_code == HTTPStatus.OK
        assert callback.json()["role"] == "viewer"
        assert _SESSION_COOKIE in client.cookies

        active = client.get("/auth/session")
        assert active.status_code == HTTPStatus.OK
        assert active.json()["role"] == "viewer"

        logged_out = client.post("/auth/logout")
        assert logged_out.status_code == HTTPStatus.NO_CONTENT

        after_logout = client.get("/auth/session")
        assert after_logout.status_code == HTTPStatus.UNAUTHORIZED
        assert after_logout.json()["code"] == "auth-session-invalid"


def _bind_role(record: PostgresRecord, tenant: TenantFixture, *, subject: str) -> None:
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    receipt = record.human_identity.bind_role(
        operator,
        HumanRoleBindingIssue(
            client_command_id=uuid4(),
            display_name=f"HTTP Flow Viewer {uuid4().hex[:8]}",
            oidc_issuer=_ISSUER,
            oidc_subject=subject,
            project_keys=(),
            role="viewer",
        ),
        request_digest=hashlib.sha256(b"http-flow-bind").digest(),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )
    assert not isinstance(receipt, RecordProblem)
