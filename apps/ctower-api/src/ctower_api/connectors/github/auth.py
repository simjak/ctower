"""Ephemeral GitHub App signing and process-memory installation-token lifecycle."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from ctower_api.connectors.github.config import GitHubConnectorConfig

__all__ = ["GITHUB_API_ORIGIN", "GITHUB_API_VERSION", "GitHubAppAuth", "GitHubAuthError"]

GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
_REFRESH_MARGIN = timedelta(minutes=5)
_MAX_TOKEN_LIFETIME = timedelta(hours=1, seconds=5)
_REDIRECT_START = 300
_REDIRECT_END = 400
_HTTP_SUCCESS_START = 200
_HTTP_SUCCESS_END = 300

PrivateKeyResolver = Callable[[str, str], str]
Clock = Callable[[], datetime]


class GitHubAuthError(RuntimeError):
    """A redacted, typed App authentication or token-lifecycle failure."""


class _StrictValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _Permissions(_StrictValue):
    issues: str
    metadata: str


class _Repository(_StrictValue):
    id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=3, max_length=201)


class _TokenResponse(_StrictValue):
    token: SecretStr
    expires_at: datetime
    permissions: _Permissions
    repositories: tuple[_Repository, ...] = Field(min_length=1, max_length=1)
    repository_selection: str

    @model_validator(mode="after")
    def _expiry_is_aware(self) -> _TokenResponse:
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("installation token expiry must be timezone-aware")
        return self


@dataclass(frozen=True, slots=True)
class _CachedToken:
    value: SecretStr = field(repr=False)
    expires_at: datetime
    binding_revision: str


class GitHubAppAuth:
    """Resolve the App key only while signing; cache only the short-lived token."""

    def __init__(
        self,
        config: GitHubConnectorConfig,
        *,
        resolve_private_key: PrivateKeyResolver,
        client: httpx.Client | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._resolve_private_key = resolve_private_key
        self._client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._binding = config.private_key_binding
        self._binding_revision = config.private_key_binding_revision
        self._cached_token: _CachedToken | None = None
        self._revoked = False

    def installation_token(self) -> SecretStr:
        now = self._aware_now()
        cached = self._cached_token
        if self._revoked:
            raise GitHubAuthError("GitHub App credential is revoked")
        if (
            cached is not None
            and cached.binding_revision == self._binding_revision
            and now + _REFRESH_MARGIN < cached.expires_at
        ):
            return cached.value
        minted = self._mint(
            now,
            binding=self._binding,
            binding_revision=self._binding_revision,
        )
        self._cached_token = minted
        return minted.value

    def rotate_private_key(self, *, binding: str, binding_revision: str) -> None:
        candidate = self._config.model_copy(
            update={
                "private_key_binding": binding,
                "private_key_binding_revision": binding_revision,
            }
        )
        GitHubConnectorConfig.model_validate(candidate.model_dump())
        if binding_revision == self._binding_revision:
            raise GitHubAuthError("GitHub App key rotation requires a new binding revision")
        self._cached_token = None
        self._revoked = True
        current_identity = self._key_identity(self._binding, self._binding_revision)
        replacement_identity = self._key_identity(binding, binding_revision)
        if replacement_identity == current_identity:
            raise GitHubAuthError("GitHub App key rotation cannot reuse the old private key")
        minted = self._mint(
            self._aware_now(),
            binding=binding,
            binding_revision=binding_revision,
        )
        self._binding = binding
        self._binding_revision = binding_revision
        self._cached_token = minted
        self._revoked = False

    def revoke(self) -> None:
        cached = self._cached_token
        self._cached_token = None
        self._revoked = True
        if cached is None:
            return
        try:
            response = self._request(
                "DELETE",
                "/installation/token",
                authorization=f"Bearer {cached.value.get_secret_value()}",
            )
        except (httpx.HTTPError, GitHubAuthError):
            raise GitHubAuthError("GitHub installation-token revocation failed closed") from None
        if response.status_code != httpx.codes.NO_CONTENT:
            raise GitHubAuthError("GitHub installation-token revocation failed closed")

    def _mint(
        self,
        now: datetime,
        *,
        binding: str,
        binding_revision: str,
    ) -> _CachedToken:
        jwt_value = self._signed_jwt(now, binding=binding, binding_revision=binding_revision)
        try:
            response = self._request(
                "POST",
                f"/app/installations/{self._config.installation_id}/access_tokens",
                authorization=f"Bearer {jwt_value}",
                json_body={
                    "repository_ids": [self._config.repository_id],
                    "permissions": {"issues": "write", "metadata": "read"},
                },
            )
        except httpx.HTTPError as error:
            status = (
                error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            )
            label = f" status {status}" if status is not None else ""
            raise GitHubAuthError(f"GitHub installation-token mint failed{label}") from None
        if response.status_code != httpx.codes.CREATED:
            raise GitHubAuthError("GitHub installation-token mint returned an unsupported status")
        try:
            parsed = _TokenResponse.model_validate_json(response.content)
        except (ValueError, TypeError):
            raise GitHubAuthError(
                "GitHub installation-token grant violated least privilege"
            ) from None
        self._verify_grant(parsed, now)
        return _CachedToken(parsed.token, parsed.expires_at, binding_revision)

    def _verify_grant(self, response: _TokenResponse, now: datetime) -> None:
        repository = response.repositories[0]
        if (
            response.repository_selection != "selected"
            or response.permissions.model_dump() != {"issues": "write", "metadata": "read"}
            or repository.id != self._config.repository_id
            or repository.name != self._config.repository_name
            or repository.full_name != self._config.repository_full_name
            or response.expires_at <= now + _REFRESH_MARGIN
            or response.expires_at - now > _MAX_TOKEN_LIFETIME
        ):
            raise GitHubAuthError("GitHub installation-token grant violated least privilege")

    def _signed_jwt(self, now: datetime, *, binding: str, binding_revision: str) -> str:
        header = _base64_json({"alg": "RS256", "typ": "JWT"})
        claims = _base64_json(
            {
                "exp": int(now.timestamp()) + 540,
                "iat": int(now.timestamp()) - 60,
                "iss": self._config.app_client_id,
            }
        )
        signing_input = f"{header}.{claims}".encode("ascii")
        try:
            pem = self._resolve_private_key(binding, binding_revision)
            key = _rsa_private_key(pem)
            signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        except (LookupError, OSError, RuntimeError, TypeError, UnicodeError, ValueError):
            raise GitHubAuthError("GitHub App private-key resolution or signing failed") from None
        return f"{header}.{claims}.{_base64_bytes(signature)}"

    def _key_identity(self, binding: str, binding_revision: str) -> rsa.RSAPublicNumbers:
        try:
            pem = self._resolve_private_key(binding, binding_revision)
            return _rsa_private_key(pem).public_key().public_numbers()
        except (LookupError, OSError, RuntimeError, TypeError, UnicodeError, ValueError):
            raise GitHubAuthError("GitHub App private-key resolution or signing failed") from None

    def _request(
        self,
        method: str,
        path: str,
        *,
        authorization: str,
        json_body: dict[str, object] | None = None,
    ) -> httpx.Response:
        url = _pinned_url(path)
        response = self._client.request(
            method,
            url,
            headers=_headers(authorization),
            json=json_body,
            follow_redirects=False,
        )
        if _REDIRECT_START <= response.status_code < _REDIRECT_END:
            raise GitHubAuthError("GitHub egress redirect was refused")
        if not _HTTP_SUCCESS_START <= response.status_code < _HTTP_SUCCESS_END:
            response.raise_for_status()
        return response

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise GitHubAuthError("GitHub authentication clock must be timezone-aware")
        return value


def _headers(authorization: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": authorization,
        "User-Agent": "ctower-github-issues",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def _pinned_url(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        raise GitHubAuthError("GitHub egress destination drift was refused")
    url = httpx.URL(f"{GITHUB_API_ORIGIN}{path}")
    if url.scheme != "https" or url.host != "api.github.com" or url.port not in {None, 443}:
        raise GitHubAuthError("GitHub egress destination drift was refused")
    return str(url)


def _base64_json(value: dict[str, object]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _base64_bytes(raw)


def _base64_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _rsa_private_key(pem: str) -> rsa.RSAPrivateKey:
    key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError
    return key
