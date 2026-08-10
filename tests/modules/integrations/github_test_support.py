"""Non-secret GitHub App test material created only in process memory."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ctower_api.connectors.github import GitHubConnectorConfig

__all__ = [
    "API_ORIGIN",
    "Clock",
    "MintingTransport",
    "connector_config",
    "decode_jwt_part",
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
