"""GH-C01..C06 and frozen-boundary security controls for the GitHub connector."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from ctower_api.connector_loop import ConnectorLoop, build_connector_loop
from ctower_api.connectors.github import (
    GitHubAppAuth,
    GitHubAuthError,
    GitHubConnectorConfig,
    GitHubCursor,
    GitHubIssueConnector,
    GitHubRuntimeRegistration,
)
from ctower_api.control_worker import build_worker
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import (
    ConnectorAttempt,
    ConnectorCursorToken,
    FetchIssuePage,
    FetchIssuePageResult,
)
from ctower_kernel.projections import Projections
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.runtime import Routine
from modules.integrations.github_test_support import (
    Clock,
    MintingTransport,
    SecretPath,
    SecretPathTransport,
    assert_jwt_signed_by,
    connector_config,
    decode_jwt_part,
    live_tainted_private_key,
    private_key_pem,
)

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
_REVISION = "sha256:" + "b" * 64
_SECOND_MINT = 2


def test_github_private_key_and_tokens_are_reference_only() -> None:
    payload = _catalog_payload()
    runtime = GitHubRuntimeRegistration.from_catalog(
        payload,
        revision_id=_uuid("22222222-2222-4222-8222-222222222222"),
        revision_digest=_REVISION,
    )
    serialized = json.dumps(
        {
            "payload": payload,
            "config": runtime.config.model_dump(mode="json"),
            "registration": runtime.registration.to_mapping(),
        },
        sort_keys=True,
    ).lower()

    assert runtime.private_key_binding == "GITHUB_FEEDBACK_APP_PRIVATE_KEY"
    assert "private_key_binding" in serialized
    assert not any(
        forbidden in serialized
        for forbidden in ("private_key_value", "private_key_pem", "installation_token", "jwt")
    )


def test_github_installation_token_is_minted_server_side() -> None:
    clock, transport, resolved, auth = _auth()

    token = auth.installation_token()
    request = transport.mint_requests[0]
    jwt_value = request.headers["authorization"].removeprefix("Bearer ")
    header, claims, _signature = jwt_value.split(".")

    assert token.get_secret_value() == "opaque-token-value"
    assert resolved == [("GITHUB_FEEDBACK_APP_PRIVATE_KEY", "sha256:" + "a" * 64)]
    assert decode_jwt_part(header) == {"alg": "RS256", "typ": "JWT"}
    assert decode_jwt_part(claims) == {
        "exp": int(clock.now.timestamp()) + 540,
        "iat": int(clock.now.timestamp()) - 60,
        "iss": "Iv1.0123456789abcdef",
    }


def test_github_installation_token_refreshes_before_expiry() -> None:
    clock, transport, _resolved, auth = _auth()
    first = auth.installation_token().get_secret_value()
    clock.advance(timedelta(minutes=54, seconds=59))
    cached = auth.installation_token().get_secret_value()
    clock.advance(timedelta(seconds=2))
    transport.opaque_value = "replacement-value"
    refreshed = auth.installation_token().get_secret_value()

    assert (first, cached, refreshed) == (
        "opaque-token-value",
        "opaque-token-value",
        "replacement-value",
    )
    assert len(transport.mint_requests) == _SECOND_MINT


def test_github_token_format_is_opaque() -> None:
    opaque = "not-a-ghs-prefix:any-length-or-shape-is-opaque"
    _clock, transport, _resolved, auth = _auth(opaque_value=opaque)

    assert auth.installation_token().get_secret_value() == opaque
    assert transport.mint_requests


def test_github_token_mint_is_repository_selected_and_least_privilege() -> None:
    _clock, transport, _resolved, auth = _auth()
    auth.installation_token()
    request = transport.mint_requests[0]

    assert json.loads(request.read()) == {
        "permissions": {"issues": "write", "metadata": "read"},
        "repository_ids": [98_765],
    }
    assert request.url == httpx.URL("https://api.github.com/app/installations/12345/access_tokens")

    bad_transport = MintingTransport(Clock())

    def broader(request: httpx.Request) -> httpx.Response:
        response = bad_transport.handle(request)
        if request.url.path.endswith("/access_tokens"):
            payload = cast(dict[str, object], response.json())
            payload["permissions"] = {"issues": "write", "metadata": "read", "contents": "read"}
            return httpx.Response(201, request=request, json=payload)
        return response

    denied = _auth(handler=broader)[3]
    with pytest.raises(GitHubAuthError, match="grant violated"):
        denied.installation_token()


def test_github_registration_refuses_unapproved_auth_and_ingress() -> None:
    for field, value in (
        ("private_key", "forbidden"),
        ("installation_token", "forbidden"),
        ("personal_access_token", "forbidden"),
        ("oauth_client_secret", "forbidden"),
        ("webhook_secret", "forbidden"),
        ("api_origin", "https://github.example.test"),
    ):
        payload = _catalog_payload()
        payload[field] = value
        with pytest.raises(ValidationError, match=field):
            GitHubRuntimeRegistration.from_catalog(
                payload,
                revision_id=_uuid("22222222-2222-4222-8222-222222222222"),
                revision_digest=_REVISION,
            )


def test_github_egress_is_pinned_to_api_github_com_443() -> None:
    clock, transport, resolved, auth = _auth()
    connector = GitHubIssueConnector(
        connector_config(),
        auth=auth,
        client=httpx.Client(transport=httpx.MockTransport(transport.handle)),
    )
    result = connector.fetch_page(_fetch_request(), _attempt())

    assert result.kind == "page"
    assert all(
        request.url.scheme == "https"
        and request.url.host == "api.github.com"
        and request.url.port in {None, 443}
        for request in (*transport.mint_requests, *transport.issue_requests)
    )
    assert resolved
    with pytest.raises(ValidationError):
        GitHubConnectorConfig.model_validate(
            {**connector_config().model_dump(), "repository_owner": "evil.example/x"}
        )
    assert clock.now.tzinfo is not None


def test_github_egress_rejects_redirects_and_destination_drift() -> None:
    clock = Clock()
    key = private_key_pem()
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(
                307,
                request=request,
                headers={"location": "https://attacker.example/token"},
            )
        raise AssertionError("redirect target received a credential")

    auth = GitHubAppAuth(
        connector_config(),
        resolve_private_key=lambda _binding, _revision: key,
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
        clock=clock,
    )
    with pytest.raises(GitHubAuthError, match="redirect"):
        auth.installation_token()
    assert len(observed) == 1 and observed[0].url.host == "api.github.com"


def test_github_key_rotation_rebinds_without_old_key_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    clock.now = datetime.now(tz=UTC)
    transport = SecretPathTransport(clock, path="rotation", canary="ROTATION-CREDENTIAL-CANARY")
    client = httpx.Client(transport=httpx.MockTransport(transport.handle))
    monkeypatch.setattr(httpx, "Client", lambda *_args, **_kwargs: client)
    runtime = GitHubRuntimeRegistration.from_catalog(
        _catalog_payload(),
        revision_id=_uuid("22222222-2222-4222-8222-222222222222"),
        revision_digest=_REVISION,
    )
    old_key = private_key_pem()
    replacement_key = private_key_pem()
    old_reference = _revision_secret_reference(
        "GITHUB_FEEDBACK_APP_PRIVATE_KEY", "sha256:" + "a" * 64
    )
    replacement_reference = _revision_secret_reference(
        "GITHUB_FEEDBACK_APP_PRIVATE_KEY_V2", "sha256:" + "c" * 64
    )
    keys = {old_reference: old_key, replacement_reference: old_key}
    resolved: list[str] = []

    def resolver(reference: str) -> str:
        resolved.append(reference)
        return keys[reference]

    connector = runtime.build(resolver)
    initial = connector.fetch_page(_fetch_request(), _attempt())
    with pytest.raises(GitHubAuthError, match="reuse the old private key"):
        connector.rotate_private_key(
            binding="GITHUB_FEEDBACK_APP_PRIVATE_KEY_V2",
            binding_revision="sha256:" + "c" * 64,
        )
    refused = connector.fetch_page(_fetch_request(), _attempt())

    keys[replacement_reference] = replacement_key
    connector.rotate_private_key(
        binding="GITHUB_FEEDBACK_APP_PRIVATE_KEY_V2",
        binding_revision="sha256:" + "c" * 64,
    )
    result = connector.fetch_page(_fetch_request(), _attempt())
    assert_jwt_signed_by(transport.jwt_taints[-1], replacement_key)

    revoked = _revoke_through_control_worker(runtime, connector)

    assert refused.kind == "fetch_failure" and refused.reason == "authentication"
    assert initial.kind == "page"
    assert result.kind == "page"
    assert revoked.kind == "fetch_failure" and revoked.reason == "authentication"
    assert resolved == [
        old_reference,
        old_reference,
        replacement_reference,
        old_reference,
        replacement_reference,
        replacement_reference,
    ]
    assert transport.mint_count == _SECOND_MINT
    assert transport.issue_count == _SECOND_MINT
    assert transport.revoke_count == 1


def test_github_revocation_drill_invalidates_cached_tokens_and_fails_closed() -> None:
    _clock, transport, _resolved, auth = _auth()
    auth.installation_token()
    auth.revoke()

    assert len(transport.revoke_requests) == 1
    with pytest.raises(GitHubAuthError, match="revoked"):
        auth.installation_token()
    assert len(transport.mint_requests) == 1

    transport.opaque_value = "replacement-value"
    auth.rotate_private_key(
        binding="GITHUB_FEEDBACK_APP_PRIVATE_KEY_V2",
        binding_revision="sha256:" + "c" * 64,
    )
    assert auth.installation_token().get_secret_value() == "replacement-value"
    assert len(transport.mint_requests) == _SECOND_MINT


def test_github_authentication_refusals_fail_closed() -> None:
    _clock, _transport, _resolved, auth = _auth()
    with pytest.raises(GitHubAuthError, match="new binding revision"):
        auth.rotate_private_key(
            binding="GITHUB_FEEDBACK_APP_PRIVATE_KEY_V2",
            binding_revision="sha256:" + "a" * 64,
        )

    auth.revoke()
    with pytest.raises(GitHubAuthError, match="revoked"):
        auth.installation_token()

    clock = Clock()
    mint = MintingTransport(clock)

    def failed_revoke(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(503, request=request)
        return mint.handle(request)

    failed = _auth(handler=failed_revoke)[3]
    failed.installation_token()
    with pytest.raises(GitHubAuthError, match="revocation failed closed"):
        failed.revoke()

    def unsupported_revoke(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(200, request=request)
        return mint.handle(request)

    unsupported = _auth(handler=unsupported_revoke)[3]
    unsupported.installation_token()
    with pytest.raises(GitHubAuthError, match="revocation failed closed"):
        unsupported.revoke()


@pytest.mark.parametrize("failure", ["status", "http", "json", "naive-expiry", "short-grant"])
def test_github_token_mint_refuses_invalid_provider_grants(failure: str) -> None:
    clock = Clock()
    mint = MintingTransport(clock)

    def handler(request: httpx.Request) -> httpx.Response:
        response = mint.handle(request)
        if failure == "status":
            return httpx.Response(200, request=request, json=response.json())
        if failure == "http":
            return httpx.Response(503, request=request)
        if failure == "json":
            return httpx.Response(201, request=request, content=b"{")
        payload = cast(dict[str, object], response.json())
        if failure == "naive-expiry":
            payload["expires_at"] = clock.now.replace(tzinfo=None).isoformat()
        else:
            payload["expires_at"] = (clock.now + timedelta(minutes=4)).isoformat()
        return httpx.Response(201, request=request, json=payload)

    auth = _auth(handler=handler)[3]
    with pytest.raises(GitHubAuthError):
        auth.installation_token()


def test_github_signing_and_clock_failures_are_redacted() -> None:
    clock = Clock()
    mint = MintingTransport(clock)
    bad_key = GitHubAppAuth(
        connector_config(),
        resolve_private_key=lambda _binding, _revision: "not-a-private-key",
        client=httpx.Client(transport=httpx.MockTransport(mint.handle)),
        clock=clock,
    )
    with pytest.raises(GitHubAuthError, match="resolution or signing failed") as key_error:
        bad_key.installation_token()
    assert "not-a-private-key" not in str(key_error.value)

    naive_clock = GitHubAppAuth(
        connector_config(),
        resolve_private_key=lambda _binding, _revision: private_key_pem(),
        client=httpx.Client(transport=httpx.MockTransport(mint.handle)),
        clock=lambda: clock.now.replace(tzinfo=None),
    )
    with pytest.raises(GitHubAuthError, match="timezone-aware"):
        naive_clock.installation_token()


@pytest.mark.parametrize(
    "path",
    ("success", "http-failure", "malformed-response", "refresh", "rotation", "revocation"),
)
def test_github_secret_taint_never_reaches_observable_outputs(
    path: str,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_taints = ["PRIVATE-KEY-TAINT-OLD"]
    if path == "rotation":
        private_taints.append("PRIVATE-KEY-TAINT-REPLACEMENT")
    installation_canary = "INSTALLATION-CREDENTIAL-CANARY"
    clock = Clock()
    transport = SecretPathTransport(clock, path=cast(SecretPath, path), canary=installation_canary)
    keys = {
        "sha256:" + "a" * 64: live_tainted_private_key(private_taints[0]),
        "sha256:" + "c" * 64: live_tainted_private_key(private_taints[-1]),
    }
    resolved: list[tuple[str, str]] = []

    def resolver(binding: str, revision: str) -> str:
        resolved.append((binding, revision))
        return keys[revision]

    client = httpx.Client(transport=httpx.MockTransport(transport.handle))
    caplog.set_level(logging.DEBUG)
    auth = GitHubAppAuth(
        connector_config(),
        resolve_private_key=resolver,
        client=client,
        clock=clock,
    )
    connector = GitHubIssueConnector(
        connector_config(),
        auth=auth,
        client=client,
    )
    results: list[object] = [connector.fetch_page(_fetch_request(), _attempt())]
    if path == "refresh":
        clock.advance(timedelta(minutes=56))
        results.append(connector.fetch_page(_fetch_request(), _attempt()))
    elif path == "rotation":
        connector.rotate_private_key(
            binding="GITHUB_FEEDBACK_APP_PRIVATE_KEY_V2",
            binding_revision="sha256:" + "c" * 64,
        )
        results.append(connector.fetch_page(_fetch_request(), _attempt()))
    elif path == "revocation":
        connector.revoke_credentials()
        results.append(connector.fetch_page(_fetch_request(), _attempt()))

    captured = capsys.readouterr()
    observable = _observable_surface_dump(
        auth,
        connector,
        results,
        transport,
        caplog,
        (captured.out, captured.err),
    )
    secret_taints = [*private_taints, *transport.jwt_taints, *transport.token_taints]
    _assert_secret_path_reached(path, transport, resolved)
    assert all(taint and taint not in observable for taint in secret_taints)
    assert "Bearer " not in observable


def test_github_phase2_preserves_phase1_freeze_set() -> None:
    frozen = (
        "packages/ctower-kernel/src/ctower_kernel/integrations/interface.py",
        "packages/ctower-kernel/src/ctower_kernel/integrations/service.py",
        "packages/ctower-kernel/src/ctower_kernel/integrations/postgres.py",
        "packages/ctower-kernel/src/ctower_kernel/integrations/_postgres_sql.py",
        "packages/ctower-kernel/migrations/0055_connector_framework.sql",
        "apps/ctower-api/src/ctower_api/control_worker.py",
        "tests/modules/integrations/connector_conformance.py",
    )
    assert all((ROOT / path).is_file() for path in frozen)


def _auth(
    *,
    opaque_value: str = "opaque-token-value",
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> tuple[Clock, MintingTransport, list[tuple[str, str]], GitHubAppAuth]:
    clock = Clock()
    transport = MintingTransport(clock, opaque_value=opaque_value)
    keys = {
        "sha256:" + "a" * 64: private_key_pem(),
        "sha256:" + "c" * 64: private_key_pem(),
    }
    resolved: list[tuple[str, str]] = []

    def resolver(binding: str, revision: str) -> str:
        resolved.append((binding, revision))
        return keys[revision]

    selected_handler = handler if handler is not None else transport.handle
    auth = GitHubAppAuth(
        connector_config(),
        resolve_private_key=resolver,
        client=httpx.Client(transport=httpx.MockTransport(selected_handler)),
        clock=clock,
    )
    return clock, transport, resolved, auth


def _revoke_through_control_worker(
    runtime: GitHubRuntimeRegistration, connector: GitHubIssueConnector
) -> FetchIssuePageResult:
    loop = build_connector_loop(
        runtime,
        connector=connector,
        actor=Actor(
            _uuid("11111111-1111-4111-8111-111111111111"),
            _uuid("22222222-2222-4222-8222-222222222222"),
            PrincipalKind.COMMANDER,
        ),
        runtime_dsn="postgresql://runtime-reference",
    )
    worker = build_worker(
        cast(Routine, object()),
        cast(Projections, object()),
        pack_root=ROOT / "packs",
        standing_integrations=(loop,),
    )
    composed = cast(ConnectorLoop, worker.standing_integrations[0])
    assert composed.connector is connector
    assert isinstance(composed.connector, GitHubIssueConnector)
    composed.connector.revoke_credentials()
    return composed.connector.fetch_page(_fetch_request(), _attempt())


def _observable_surface_dump(
    auth: GitHubAppAuth,
    connector: GitHubIssueConnector,
    results: list[object],
    transport: SecretPathTransport,
    caplog: pytest.LogCaptureFixture,
    captured_output: tuple[str, str],
) -> str:
    serialized = [
        result.model_dump(mode="json") if hasattr(result, "model_dump") else repr(result)
        for result in results
    ]
    surfaces = {
        "exceptions": [],
        "structured_failures": serialized,
        "logs": [record.getMessage() for record in caplog.records],
        "telemetry": [],
        "record_messages": serialized,
        "inbox_messages": [],
        "status": connector.diagnostic,
        "receipts": serialized,
        "snapshots": [repr(auth), repr(connector), repr(results)],
        "fixtures": transport.safe_requests,
        "cli_output": list(captured_output),
        "urls": [request["url"] for request in transport.safe_requests],
        "captured_headers": [request["headers"] for request in transport.safe_requests],
        "gate_artifacts": serialized,
    }
    return json.dumps(surfaces, sort_keys=True, default=repr)


def _assert_secret_path_reached(
    path: str,
    transport: SecretPathTransport,
    resolved: list[tuple[str, str]],
) -> None:
    expected_counts = {
        "success": (1, 1, 0),
        "http-failure": (1, 1, 0),
        "malformed-response": (1, 0, 0),
        "refresh": (2, 2, 0),
        "rotation": (2, 2, 0),
        "revocation": (1, 1, 1),
    }
    assert (transport.mint_count, transport.issue_count, transport.revoke_count) == expected_counts[
        path
    ]
    assert resolved
    assert transport.jwt_taints and transport.token_taints


def _fetch_request() -> FetchIssuePage:
    cursor = GitHubCursor(
        updated_at=Clock().now - timedelta(days=1),
        issue_id=0,
        page=1,
    )
    return FetchIssuePage(cursor=ConnectorCursorToken(value=cursor.encode()), page_size=50)


def _attempt() -> ConnectorAttempt:
    return ConnectorAttempt(
        attempt_number=1,
        max_attempts=4,
        deadline_remaining_milliseconds=10_000,
    )


def _catalog_payload() -> dict[str, JsonValue]:
    return {
        "schema": "ctower.integration/v3",
        "key": "github.feedback",
        "adapter": "github-issues",
        "authority": "co_source",
        "execution": "standing_sync",
        "github": {
            "app_client_id": "Iv1.0123456789abcdef",
            "installation_id": 12_345,
            "repository_id": 98_765,
            "repository_owner": "ctower",
            "repository_name": "feedback",
            "private_key_binding_revision": "sha256:" + "a" * 64,
            "repository_selection": "selected",
            "permissions": {"issues": "write", "metadata": "read"},
            "import_updated_after": "2026-08-10T00:00:00Z",
            "page_size": 50,
            "poll_interval_seconds": 60,
        },
        "ctower": {
            "project_key": "ctower",
            "initial_custodian_id": "11111111-1111-4111-8111-111111111111",
        },
        "label_map": [{"github": "bug", "ctower": "type.bug"}],
        "private_key_binding": "GITHUB_FEEDBACK_APP_PRIVATE_KEY",
    }


def _uuid(value: str) -> UUID:
    return UUID(value)


def _revision_secret_reference(binding: str, revision: str) -> str:
    return f"{binding}__SHA256_{revision.removeprefix('sha256:').upper()}"
