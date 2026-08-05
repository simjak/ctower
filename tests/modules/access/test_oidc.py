"""Provider-agnostic OIDC discovery, PKCE, and RS256 ID-token verification."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Callable

import httpx
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256

from ctower_kernel.access import oidc
from ctower_kernel.record import RecordProblem

__all__: tuple[str, ...] = ()

_ISSUER = "https://fake-idp.example.test"
_MIN_VERIFIER_LEN = 43
_MAX_VERIFIER_LEN = 128
_BOUNDED_ATTEMPTS = 2
_CLIENT_ID = "ctower-test-client"
_REDIRECT_URI = "https://ctower.example.test/auth/callback"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _key_pair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, object]:
    numbers = key.public_key().public_numbers()
    n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return {"kty": "RSA", "use": "sig", "kid": kid, "n": _b64url(n), "e": _b64url(e)}


def _sign_jwt(key: rsa.RSAPrivateKey, *, kid: str, claims: dict[str, object]) -> str:
    header = _b64url(json.dumps({"alg": "RS256", "kid": kid}).encode())
    payload = _b64url(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = key.sign(signing_input, padding.PKCS1v15(), SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


def _provider() -> oidc.OidcProvider:
    return oidc.OidcProvider(
        provider_key="fake-idp",
        issuer=_ISSUER,
        client_id=_CLIENT_ID,
        client_secret="s3cr3t",  # noqa: S106 - fake test fixture, not a real secret
        redirect_uri=_REDIRECT_URI,
    )


def _discovery() -> oidc.DiscoveryDocument:
    return oidc.DiscoveryDocument(
        issuer=_ISSUER,
        authorization_endpoint=f"{_ISSUER}/authorize",
        token_endpoint=f"{_ISSUER}/token",
        jwks_uri=f"{_ISSUER}/jwks",
    )


def _client_for(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pkce_pair_matches_s256_challenge() -> None:
    pair = oidc.generate_pkce_pair()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(pair.code_verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert pair.code_challenge == expected
    assert _MIN_VERIFIER_LEN <= len(pair.code_verifier) <= _MAX_VERIFIER_LEN


def test_authorization_url_carries_pkce_state_and_nonce() -> None:
    url = oidc.authorization_url(
        _provider(), _discovery(), state="s1", nonce="n1", code_challenge="c1"
    )
    parsed = httpx.URL(url)
    assert str(parsed.copy_with(query=None)) == f"{_ISSUER}/authorize"
    params = parsed.params
    assert params["code_challenge"] == "c1"
    assert params["code_challenge_method"] == "S256"
    assert params["state"] == "s1"
    assert params["nonce"] == "n1"
    assert params["redirect_uri"] == _REDIRECT_URI
    assert params["client_id"] == _CLIENT_ID


def test_fetch_discovery_document_confines_to_issuer_origin() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{_ISSUER}/.well-known/openid-configuration"
        return httpx.Response(
            200,
            json={
                "issuer": _ISSUER,
                "authorization_endpoint": f"{_ISSUER}/authorize",
                "token_endpoint": f"{_ISSUER}/token",
                "jwks_uri": f"{_ISSUER}/jwks",
            },
        )

    with _client_for(handler) as client:
        document = oidc.fetch_discovery_document(_ISSUER, client=client)
    assert isinstance(document, oidc.DiscoveryDocument)
    assert document.issuer == _ISSUER


def test_fetch_discovery_document_refuses_off_origin_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "issuer": _ISSUER,
                "authorization_endpoint": "https://evil.example.test/authorize",
                "token_endpoint": f"{_ISSUER}/token",
                "jwks_uri": f"{_ISSUER}/jwks",
            },
        )

    with _client_for(handler) as client:
        outcome = oidc.fetch_discovery_document(_ISSUER, client=client)
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unavailable"


def test_fetch_discovery_document_refuses_mismatched_issuer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "issuer": f"{_ISSUER}/tenant-a",
                "authorization_endpoint": f"{_ISSUER}/authorize",
                "token_endpoint": f"{_ISSUER}/token",
                "jwks_uri": f"{_ISSUER}/jwks",
            },
        )

    with _client_for(handler) as client:
        outcome = oidc.fetch_discovery_document(_ISSUER, client=client)
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unavailable"


def test_fetch_discovery_document_bounded_attempts_then_unavailable() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        del request
        attempts += 1
        raise httpx.ConnectError("refused")

    with _client_for(handler) as client:
        outcome = oidc.fetch_discovery_document(_ISSUER, client=client)
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unavailable"
    assert attempts == _BOUNDED_ATTEMPTS


def test_fetch_jwks_refuses_off_origin_uri() -> None:
    discovery = oidc.DiscoveryDocument(
        issuer=_ISSUER,
        authorization_endpoint=f"{_ISSUER}/authorize",
        token_endpoint=f"{_ISSUER}/token",
        jwks_uri="https://evil.example.test/jwks",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request to {request.url}")

    with _client_for(handler) as client:
        outcome = oidc.fetch_jwks(discovery, client=client)
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unavailable"


def test_fetch_jwks_returns_only_usable_rsa_signing_keys() -> None:
    key = _key_pair()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "keys": [
                    _jwk(key, "kid-1"),
                    {"kty": "EC", "use": "sig", "kid": "kid-2"},
                    {"kty": "RSA", "use": "enc", "kid": "kid-3", "n": "x", "e": "x"},
                ]
            },
        )

    with _client_for(handler) as client:
        jwks = oidc.fetch_jwks(_discovery(), client=client)
    assert isinstance(jwks, oidc.Jwks)
    assert jwks.key_for_kid("kid-1") is not None
    assert jwks.key_for_kid("kid-2") is None
    assert jwks.key_for_kid("kid-3") is None


def test_exchange_code_refuses_off_origin_token_endpoint() -> None:
    discovery = oidc.DiscoveryDocument(
        issuer=_ISSUER,
        authorization_endpoint=f"{_ISSUER}/authorize",
        token_endpoint="https://evil.example.test/token",  # noqa: S106 - not a real secret
        jwks_uri=f"{_ISSUER}/jwks",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request to {request.url}")

    with _client_for(handler) as client:
        outcome = oidc.exchange_code(
            _provider(), discovery, code="c", code_verifier="v", client=client
        )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unavailable"


def test_exchange_code_refuses_missing_id_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"access_token": "ignored"})

    with _client_for(handler) as client:
        outcome = oidc.exchange_code(
            _provider(), _discovery(), code="c", code_verifier="v", client=client
        )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-exchange-invalid"


def _valid_claims(now: int) -> dict[str, object]:
    return {
        "iss": _ISSUER,
        "sub": "user-42",
        "aud": _CLIENT_ID,
        "exp": now + 300,
        "iat": now,
        "nonce": "expected-nonce",
    }


def test_verify_id_token_accepts_a_correctly_signed_token() -> None:
    key = _key_pair()
    now = int(time.time())
    token = _sign_jwt(key, kid="kid-1", claims=_valid_claims(now))
    jwks = oidc.Jwks(keys=(oidc.JwksKey(kid="kid-1", public_key=key.public_key()),))

    claims = oidc.verify_id_token(
        token,
        jwks=jwks,
        provider=_provider(),
        discovery=_discovery(),
        nonce="expected-nonce",
        now=now,
    )
    assert isinstance(claims, oidc.IdTokenClaims)
    assert claims.issuer == _ISSUER
    assert claims.subject == "user-42"


def test_verify_id_token_refuses_wrong_signing_key() -> None:
    signing_key = _key_pair()
    other_key = _key_pair()
    now = int(time.time())
    token = _sign_jwt(signing_key, kid="kid-1", claims=_valid_claims(now))
    jwks = oidc.Jwks(keys=(oidc.JwksKey(kid="kid-1", public_key=other_key.public_key()),))

    outcome = oidc.verify_id_token(
        token,
        jwks=jwks,
        provider=_provider(),
        discovery=_discovery(),
        nonce="expected-nonce",
        now=now,
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unverifiable"


def test_verify_id_token_refuses_non_rs256_alg() -> None:
    key = _key_pair()
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "none", "kid": "kid-1"}).encode())
    payload = _b64url(json.dumps(_valid_claims(now)).encode())
    token = f"{header}.{payload}."
    jwks = oidc.Jwks(keys=(oidc.JwksKey(kid="kid-1", public_key=key.public_key()),))

    outcome = oidc.verify_id_token(
        token,
        jwks=jwks,
        provider=_provider(),
        discovery=_discovery(),
        nonce="expected-nonce",
        now=now,
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unverifiable"


def test_verify_id_token_refuses_unknown_kid() -> None:
    key = _key_pair()
    now = int(time.time())
    token = _sign_jwt(key, kid="kid-unknown", claims=_valid_claims(now))
    jwks = oidc.Jwks(keys=(oidc.JwksKey(kid="kid-1", public_key=key.public_key()),))

    outcome = oidc.verify_id_token(
        token,
        jwks=jwks,
        provider=_provider(),
        discovery=_discovery(),
        nonce="expected-nonce",
        now=now,
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unverifiable"


def test_verify_id_token_refuses_expired_token() -> None:
    key = _key_pair()
    now = int(time.time())
    claims = _valid_claims(now)
    claims["exp"] = now - 10
    token = _sign_jwt(key, kid="kid-1", claims=claims)
    jwks = oidc.Jwks(keys=(oidc.JwksKey(kid="kid-1", public_key=key.public_key()),))

    outcome = oidc.verify_id_token(
        token,
        jwks=jwks,
        provider=_provider(),
        discovery=_discovery(),
        nonce="expected-nonce",
        now=now,
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unverifiable"


def test_verify_id_token_refuses_wrong_audience() -> None:
    key = _key_pair()
    now = int(time.time())
    claims = _valid_claims(now)
    claims["aud"] = "some-other-client"
    token = _sign_jwt(key, kid="kid-1", claims=claims)
    jwks = oidc.Jwks(keys=(oidc.JwksKey(kid="kid-1", public_key=key.public_key()),))

    outcome = oidc.verify_id_token(
        token,
        jwks=jwks,
        provider=_provider(),
        discovery=_discovery(),
        nonce="expected-nonce",
        now=now,
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unverifiable"


def test_verify_id_token_refuses_wrong_nonce() -> None:
    key = _key_pair()
    now = int(time.time())
    token = _sign_jwt(key, kid="kid-1", claims=_valid_claims(now))
    jwks = oidc.Jwks(keys=(oidc.JwksKey(kid="kid-1", public_key=key.public_key()),))

    outcome = oidc.verify_id_token(
        token,
        jwks=jwks,
        provider=_provider(),
        discovery=_discovery(),
        nonce="replayed-nonce",
        now=now,
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unverifiable"


def test_verify_id_token_refuses_wrong_issuer() -> None:
    key = _key_pair()
    now = int(time.time())
    claims = _valid_claims(now)
    claims["iss"] = "https://impersonator.example.test"
    token = _sign_jwt(key, kid="kid-1", claims=claims)
    jwks = oidc.Jwks(keys=(oidc.JwksKey(kid="kid-1", public_key=key.public_key()),))

    outcome = oidc.verify_id_token(
        token,
        jwks=jwks,
        provider=_provider(),
        discovery=_discovery(),
        nonce="expected-nonce",
        now=now,
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "auth-provider-unverifiable"
