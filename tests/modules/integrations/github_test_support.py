"""Non-secret GitHub App test material created only in process memory."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ctower_api.connectors.github import GitHubConnectorConfig

__all__ = [
    "API_ORIGIN",
    "Clock",
    "MintingTransport",
    "SecretPath",
    "SecretPathTransport",
    "assert_jwt_signed_by",
    "connector_config",
    "decode_jwt_part",
    "live_tainted_private_key",
    "private_key_pem",
]

API_ORIGIN = "https://api.github.com"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 10, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class MintingTransport:
    """Mint exact repository-scoped tokens and serve a bounded empty issue page."""

    def __init__(
        self,
        clock: Clock,
        *,
        opaque_value: str = "opaque-token-value",
        owner: str = "ctower",
        repository: str = "feedback",
        repository_id: int = 98_765,
    ) -> None:
        self.clock = clock
        self.opaque_value = opaque_value
        self.owner = owner
        self.repository = repository
        self.repository_id = repository_id
        self.mint_requests: list[httpx.Request] = []
        self.issue_requests: list[httpx.Request] = []
        self.revoke_requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access_tokens"):
            self.mint_requests.append(request)
            return httpx.Response(
                201,
                request=request,
                json={
                    "token": self.opaque_value,
                    "expires_at": (self.clock.now + timedelta(hours=1)).isoformat(),
                    "permissions": {"issues": "write", "metadata": "read"},
                    "repositories": [
                        {
                            "id": self.repository_id,
                            "name": self.repository,
                            "full_name": f"{self.owner}/{self.repository}",
                        }
                    ],
                    "repository_selection": "selected",
                },
            )
        if request.method == "DELETE" and request.url.path == "/installation/token":
            self.revoke_requests.append(request)
            return httpx.Response(204, request=request)
        if request.method == "GET" and request.url.path.endswith("/issues"):
            self.issue_requests.append(request)
            return httpx.Response(200, request=request, json=[])
        raise AssertionError(f"unexpected GitHub request {request.method} {request.url}")


SecretPath = Literal[
    "success",
    "http-failure",
    "malformed-response",
    "refresh",
    "rotation",
    "revocation",
]


class SecretPathTransport:
    """Drive real credential paths while retaining only redacted fixture metadata."""

    def __init__(self, clock: Clock, *, path: SecretPath, canary: str) -> None:
        self.clock = clock
        self.path = path
        self.credential_canary = canary
        self.mint_count = 0
        self.issue_count = 0
        self.revoke_count = 0
        self.jwt_taints: list[str] = []
        self.token_taints: list[str] = []
        self.safe_requests: list[dict[str, object]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.safe_requests.append(
            {
                "method": request.method,
                "url": str(request.url),
                "headers": {
                    key: "[REDACTED]" if key.lower() == "authorization" else value
                    for key, value in request.headers.items()
                },
            }
        )
        if request.url.path.endswith("/access_tokens"):
            self.mint_count += 1
            self.jwt_taints.append(request.headers["authorization"].removeprefix("Bearer "))
            token = f"{self.credential_canary}-{self.mint_count}"
            self.token_taints.append(token)
            payload = self._token_payload(token)
            if self.path == "malformed-response":
                payload["repositories"] = []
            return httpx.Response(201, request=request, json=payload)
        if request.method == "DELETE" and request.url.path == "/installation/token":
            assert request.headers["authorization"].removeprefix("Bearer ") in self.token_taints
            self.revoke_count += 1
            return httpx.Response(204, request=request)
        if request.method == "GET" and request.url.path.endswith("/issues"):
            assert request.headers["authorization"].removeprefix("Bearer ") in self.token_taints
            self.issue_count += 1
            if self.path == "http-failure":
                return httpx.Response(
                    503,
                    request=request,
                    text=f"provider body {self.token_taints[-1]} {self.jwt_taints[-1]}",
                )
            return httpx.Response(200, request=request, json=[])
        raise AssertionError(f"unexpected GitHub request {request.method} {request.url}")

    def _token_payload(self, token: str) -> dict[str, object]:
        return {
            "token": token,
            "expires_at": (self.clock.now + timedelta(hours=1)).isoformat(),
            "permissions": {"issues": "write", "metadata": "read"},
            "repositories": [{"id": 98_765, "name": "feedback", "full_name": "ctower/feedback"}],
            "repository_selection": "selected",
        }


def live_tainted_private_key(taint: str) -> str:
    """Return a valid PEM whose exact signer input carries a unique trailing canary."""

    return f"{private_key_pem()}{taint}\n"


def connector_config(*, binding_revision: str | None = None) -> GitHubConnectorConfig:
    return GitHubConnectorConfig(
        app_client_id="Iv1.0123456789abcdef",
        installation_id=12_345,
        repository_id=98_765,
        repository_owner="ctower",
        repository_name="feedback",
        private_key_binding="GITHUB_FEEDBACK_APP_PRIVATE_KEY",
        private_key_binding_revision=binding_revision or "sha256:" + "a" * 64,
    )


def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    value = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return value.decode("ascii")


def decode_jwt_part(value: str) -> dict[str, object]:
    padded = value + "=" * (-len(value) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded))
    assert isinstance(decoded, dict)
    return cast(dict[str, object], decoded)


def assert_jwt_signed_by(jwt_value: str, private_key: str) -> None:
    header, claims, signature = jwt_value.split(".")
    key = serialization.load_pem_private_key(private_key.encode("ascii"), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    key.public_key().verify(
        base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)),
        f"{header}.{claims}".encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
