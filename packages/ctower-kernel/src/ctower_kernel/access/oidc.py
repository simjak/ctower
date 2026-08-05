"""Provider-agnostic OIDC discovery, PKCE, and RS256 ID-token verification.

Every provider is described entirely by its issuer URL plus a registered client
id/secret/redirect URI (deploy-time configuration read by the caller). This module
speaks only standard OIDC discovery, Authorization Code + PKCE S256, and RS256 JWS
verification; it contains no provider SDK and no Entra/Google/Okta-specific branch, and
none may be added here or in any caller.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ctower_kernel.record import RecordProblem

__all__ = [
    "DiscoveryDocument",
    "IdTokenClaims",
    "Jwks",
    "JwksKey",
    "OidcProvider",
    "PkcePair",
    "TokenResponse",
    "authorization_url",
    "exchange_code",
    "fetch_discovery_document",
    "fetch_jwks",
    "generate_pkce_pair",
    "verify_id_token",
]

_MAX_ATTEMPTS = 2
_TIMEOUT_SECONDS = 5.0
_RETRY_BACKOFF_SECONDS = 0.05
_CLOCK_SKEW_SECONDS = 300
_RS256 = "RS256"


@dataclass(frozen=True, slots=True)
class OidcProvider:
    """One deploy-time-configured OIDC relying-party registration."""

    provider_key: str
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass(frozen=True, slots=True)
class DiscoveryDocument:
    """The subset of the discovery document this module actually uses."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


@dataclass(frozen=True, slots=True)
class JwksKey:
    kid: str
    public_key: rsa.RSAPublicKey


@dataclass(frozen=True, slots=True)
class Jwks:
    keys: tuple[JwksKey, ...]

    def key_for_kid(self, kid: str) -> rsa.RSAPublicKey | None:
        for key in self.keys:
            if key.kid == kid:
                return key.public_key
        return None


@dataclass(frozen=True, slots=True)
class PkcePair:
    code_verifier: str
    code_challenge: str


@dataclass(frozen=True, slots=True)
class TokenResponse:
    """The provider token response reduced to what v1 ever reads.

    The access token is verified only insofar as TLS/HTTP delivered it from the
    registered token endpoint, then discarded immediately: it is never stored, logged,
    or returned. Any ``refresh_token``/``offline_access`` the provider returns anyway is
    likewise never captured here.
    """

    id_token: str


@dataclass(frozen=True, slots=True)
class IdTokenClaims:
    issuer: str
    subject: str
    expires_at: int


def generate_pkce_pair() -> PkcePair:
    """Generate one RFC 7636 S256 verifier/challenge pair."""

    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PkcePair(code_verifier=verifier, code_challenge=challenge)


def authorization_url(
    provider: OidcProvider,
    discovery: DiscoveryDocument,
    *,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    """Build the exact Authorization Code + PKCE S256 redirect target."""

    query = urlencode(
        {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": provider.redirect_uri,
            "scope": "openid",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{discovery.authorization_endpoint}?{query}"


def fetch_discovery_document(
    issuer: str, *, client: httpx.Client
) -> DiscoveryDocument | RecordProblem:
    """Fetch and pin the discovery document to its own registered issuer origin."""

    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    payload = _bounded_get_json(client, url)
    if isinstance(payload, RecordProblem):
        return payload
    try:
        document = DiscoveryDocument(
            issuer=str(payload["issuer"]),
            authorization_endpoint=str(payload["authorization_endpoint"]),
            token_endpoint=str(payload["token_endpoint"]),
            jwks_uri=str(payload["jwks_uri"]),
        )
    except KeyError:
        return _provider_unavailable("The discovery document is missing a required field.")
    if document.issuer != issuer:
        return _provider_unavailable(
            "The discovery document issuer does not match the configured issuer."
        )
    for endpoint in (document.authorization_endpoint, document.token_endpoint, document.jwks_uri):
        if _origin(endpoint) != _origin(issuer):
            return _provider_unavailable(
                "A discovery endpoint is off the issuer's registered origin."
            )
    return document


def fetch_jwks(discovery: DiscoveryDocument, *, client: httpx.Client) -> Jwks | RecordProblem:
    """Fetch the signing key set, confined to the discovery document's own origin."""

    if _origin(discovery.jwks_uri) != _origin(discovery.issuer):
        return _provider_unavailable("The JWKS URI is off the issuer's registered origin.")
    payload = _bounded_get_json(client, discovery.jwks_uri)
    if isinstance(payload, RecordProblem):
        return payload
    raw_keys = payload.get("keys")
    if not isinstance(raw_keys, list):
        return _provider_unavailable("The JWKS document has no keys.")
    keys: list[JwksKey] = []
    for raw in raw_keys:
        if not isinstance(raw, dict) or not _is_usable_rsa_key(raw):
            continue
        try:
            key = _rsa_public_key_from_jwk(raw)
        except (KeyError, ValueError):
            continue
        keys.append(JwksKey(kid=str(raw["kid"]), public_key=key))
    return Jwks(keys=tuple(keys))


def exchange_code(
    provider: OidcProvider,
    discovery: DiscoveryDocument,
    *,
    code: str,
    code_verifier: str,
    client: httpx.Client,
) -> TokenResponse | RecordProblem:
    """Exchange one authorization code, confined to the discovery token endpoint origin."""

    if _origin(discovery.token_endpoint) != _origin(discovery.issuer):
        return _provider_unavailable("The token endpoint is off the issuer's registered origin.")
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": provider.redirect_uri,
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "code_verifier": code_verifier,
    }
    payload = _bounded_post_form(client, discovery.token_endpoint, body)
    if isinstance(payload, RecordProblem):
        return payload
    id_token = payload.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        return _exchange_invalid("The token response carried no ID token.")
    return TokenResponse(id_token=id_token)


def verify_id_token(
    id_token: str,
    *,
    jwks: Jwks,
    provider: OidcProvider,
    discovery: DiscoveryDocument,
    nonce: str,
    now: int,
) -> IdTokenClaims | RecordProblem:
    """Verify one RS256-signed ID token and its issuer/audience/expiry/nonce claims."""

    decoded = _decode_compact_jws(id_token)
    if isinstance(decoded, RecordProblem):
        return decoded
    header, payload, signing_input, signature = decoded
    verified = _verify_rs256_signature(header, signing_input, signature, jwks=jwks)
    if verified is not None:
        return verified
    return _validate_claims(payload, provider=provider, discovery=discovery, nonce=nonce, now=now)


_JWS_COMPACT_PARTS = 3


def _decode_compact_jws(
    id_token: str,
) -> tuple[dict[str, object], dict[str, object], bytes, bytes] | RecordProblem:
    parts = id_token.split(".")
    if len(parts) != _JWS_COMPACT_PARTS:
        return _provider_unverifiable("The ID token is not a compact JWS.")
    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(signature_b64)
    except (ValueError, UnicodeDecodeError):
        return _provider_unverifiable("The ID token is not valid base64url/JSON.")
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return _provider_unverifiable("The ID token header or payload is not a JSON object.")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    return header, payload, signing_input, signature


def _verify_rs256_signature(
    header: dict[str, object], signing_input: bytes, signature: bytes, *, jwks: Jwks
) -> RecordProblem | None:
    if header.get("alg") != _RS256:
        return _provider_unverifiable("The ID token algorithm is not exactly RS256.")
    kid = header.get("kid")
    public_key = jwks.key_for_kid(str(kid)) if kid is not None else None
    if public_key is None:
        return _provider_unverifiable("No JWKS key matches the ID token's key ID.")
    try:
        public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        return _provider_unverifiable("The ID token signature does not verify.")
    return None


def _validate_claims(
    payload: dict[str, object],
    *,
    provider: OidcProvider,
    discovery: DiscoveryDocument,
    nonce: str,
    now: int,
) -> IdTokenClaims | RecordProblem:
    subject = payload.get("sub")
    checks = (
        _check_issuer(payload.get("iss"), discovery.issuer),
        _check_subject(subject),
        _check_audience(payload.get("aud"), provider.client_id),
        _check_timing(payload.get("exp"), payload.get("iat"), now),
        _check_nonce(payload.get("nonce"), nonce),
    )
    for problem in checks:
        if problem is not None:
            return problem
    return IdTokenClaims(
        issuer=str(payload["iss"]),
        subject=cast(str, subject),
        expires_at=cast(int, payload["exp"]),
    )


def _check_issuer(issuer: object, expected: str) -> RecordProblem | None:
    if issuer != expected:
        return _provider_unverifiable("The ID token issuer does not match the configured issuer.")
    return None


def _check_subject(subject: object) -> RecordProblem | None:
    if not isinstance(subject, str) or not subject:
        return _provider_unverifiable("The ID token has no subject.")
    return None


def _check_audience(audience: object, client_id: str) -> RecordProblem | None:
    audiences = audience if isinstance(audience, list) else [audience]
    if client_id not in audiences:
        return _provider_unverifiable(
            "The ID token audience does not include the registered client."
        )
    return None


def _check_timing(expires_at: object, issued_at: object, now: int) -> RecordProblem | None:
    if not isinstance(expires_at, int) or expires_at <= now:
        return _provider_unverifiable("The ID token has expired.")
    if not isinstance(issued_at, int) or issued_at > now + _CLOCK_SKEW_SECONDS:
        return _provider_unverifiable("The ID token was issued in the future.")
    return None


def _check_nonce(token_nonce: object, expected: str) -> RecordProblem | None:
    if not isinstance(token_nonce, str) or token_nonce != expected:
        return _provider_unverifiable("The ID token nonce does not match the login attempt.")
    return None


def _is_usable_rsa_key(raw: dict[str, object]) -> bool:
    return raw.get("kty") == "RSA" and raw.get("use") in (None, "sig")


def _rsa_public_key_from_jwk(raw: dict[str, object]) -> rsa.RSAPublicKey:
    modulus = int.from_bytes(_b64url_decode(str(raw["n"])), "big")
    exponent = int.from_bytes(_b64url_decode(str(raw["e"])), "big")
    return rsa.RSAPublicNumbers(exponent, modulus).public_key()


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((-len(value)) % 4))


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    return (parts.scheme, (parts.hostname or "").lower(), parts.port)


def _bounded_get_json(client: httpx.Client, url: str) -> dict[str, object] | RecordProblem:
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        if attempt:
            time.sleep(_RETRY_BACKOFF_SECONDS)
        try:
            response = client.get(url, timeout=_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
            continue
        if not isinstance(data, dict):
            return _provider_unavailable("The provider response was not a JSON object.")
        return data
    return _provider_unavailable(f"The provider endpoint did not respond: {last_error}")


_CLIENT_ERROR_STATUS = 400
_SERVER_ERROR_STATUS = 500


def _bounded_post_form(
    client: httpx.Client, url: str, body: dict[str, str]
) -> dict[str, object] | RecordProblem:
    """Exchange a code with the token endpoint, one bounded-retry attempt at a time.

    A 4xx response (invalid/replayed code, PKCE mismatch, ...) is the provider's terminal
    verdict on this exact code and is never retried; only a network failure or 5xx
    consumes a retry before falling back to ``auth-provider-unavailable``.
    """

    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        if attempt:
            time.sleep(_RETRY_BACKOFF_SECONDS)
        try:
            response = client.post(url, data=body, timeout=_TIMEOUT_SECONDS)
        except httpx.HTTPError as error:
            last_error = error
            continue
        if _CLIENT_ERROR_STATUS <= response.status_code < _SERVER_ERROR_STATUS:
            return _exchange_invalid(
                f"The token endpoint refused the code exchange: HTTP {response.status_code}."
            )
        try:
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
            continue
        if not isinstance(data, dict):
            return _exchange_invalid("The token endpoint response was not a JSON object.")
        return data
    return _provider_unavailable(f"The token endpoint did not respond: {last_error}")


def _provider_unavailable(detail: str) -> RecordProblem:
    return RecordProblem(
        code="auth-provider-unavailable",
        detail=detail,
        status=503,
        title="OIDC provider unavailable",
    )


def _provider_unverifiable(detail: str) -> RecordProblem:
    return RecordProblem(
        code="auth-provider-unverifiable",
        detail=detail,
        status=401,
        title="OIDC provider token unverifiable",
    )


def _exchange_invalid(detail: str) -> RecordProblem:
    return RecordProblem(
        code="auth-exchange-invalid", detail=detail, status=400, title="OIDC code exchange invalid"
    )
