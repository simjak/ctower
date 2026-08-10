"""GitHub Issue round trip through real PostgreSQL and HTTP MockTransport."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import cast
from uuid import UUID

import httpx
import psycopg
from modules.integrations.github_test_support import Clock, MintingTransport, private_key_pem
from psycopg.rows import dict_row
from support.acceptance import accept_pending_commands
from support.gitlab_connector import _activate_payloads, _revision_identity, proof_gate_close
from support.tenant_fixture import TenantFixture

from ctower_api.connectors.github import (
    GitHubAppAuth,
    GitHubIssueConnector,
    GitHubRuntimeRegistration,
)
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.postgres import PostgresBoardContextFacts
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import IssueConnectorService
from ctower_kernel.integrations.postgres import PostgresConnectorStore
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Intake

__all__: tuple[str, ...] = ()


def test_github_issue_roundtrip_uses_real_postgres_and_mock_transport(
    tenant: TenantFixture,
) -> None:
    payload = _payload(tenant.commander_id)
    _activate_payloads(tenant, (payload,))
    revision_id, digest = _revision_identity(tenant, payload)
    runtime = GitHubRuntimeRegistration.from_catalog(
        payload, revision_id=revision_id, revision_digest=digest
    )
    clock = Clock()
    mint = MintingTransport(clock)
    auth = GitHubAppAuth(
        runtime.config,
        resolve_private_key=lambda _binding, _revision: private_key_pem(),
        client=httpx.Client(transport=httpx.MockTransport(mint.handle)),
        clock=clock,
    )
    provider = _Provider()
    connector = GitHubIssueConnector(
        runtime.config,
        auth=auth,
        client=httpx.Client(transport=httpx.MockTransport(provider.handle)),
    )
    record = PostgresRecord(tenant.database.runtime_dsn)
    sync = IssueConnectorService(
        connector,
        PostgresConnectorStore(tenant.database.runtime_dsn),
        Intake(record),
        record,
        record.event_audit,
        BoardContextFacts(PostgresBoardContextFacts(tenant.database.runtime_dsn)),
        clock=clock,
    )
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)

    first = sync.tick(actor, runtime.registration)
    ticket_id = _linked_ticket(tenant)
    assert first.tickets_created == first.issues_seen == 1
    _assert_mapping(tenant, ticket_id)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    provider.issue["body"] = "Feedback body after reporter edit"
    provider.issue["updated_at"] = "2026-08-10T12:04:00Z"
    clock.now += timedelta(seconds=60)
    assert sync.tick(actor, runtime.registration).ticket_updates == 1
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    close_event_id = proof_gate_close(tenant, ticket_id)
    clock.now += timedelta(seconds=60)
    assert sync.tick(actor, runtime.registration).closures_delivered == 1
    assert provider.issue["state"] == "closed"
    assert len(provider.comments) == provider.comment_posts == provider.close_patches == 1
    assert f"ctower-sync:{close_event_id}" in provider.comments[0]


class _Provider:
    def __init__(self) -> None:
        self.issue: dict[str, object] = {
            "id": 4290,
            "number": 429,
            "title": "GitHub connector",
            "body": "Feedback body",
            "labels": [{"name": "bug"}],
            "user": {"id": 42, "login": "reporter"},
            "state": "open",
            "updated_at": "2026-08-10T12:01:00Z",
            "html_url": "https://github.com/ctower/feedback/issues/429",
            "repository_url": "https://api.github.com/repos/ctower/feedback",
        }
        self.comments: list[str] = []
        self.comment_posts = 0
        self.close_patches = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/issues"):
            since = request.url.params["since"]
            values = [self.issue] if str(self.issue["updated_at"]) > since else []
            return httpx.Response(200, request=request, json=values)
        if request.method == "GET" and request.url.path.endswith("/comments"):
            return httpx.Response(
                200, request=request, json=[{"body": body} for body in self.comments]
            )
        if request.method == "POST":
            self.comment_posts += 1
            body = cast(dict[str, str], json.loads(request.read()))["body"]
            self.comments.append(body)
            return httpx.Response(201, request=request, json={"body": body})
        if request.method == "PATCH":
            self.close_patches += 1
            self.issue["state"] = "closed"
            self.issue["updated_at"] = "2026-08-10T12:05:00Z"
            return httpx.Response(200, request=request, json={"state": "closed"})
        raise AssertionError(request)


def _payload(commander_id: UUID) -> dict[str, JsonValue]:
    return {
        "schema": "ctower.integration/v3",
        "key": "github.feedback",
        "adapter": "github-issues",
        "authority": "co_source",
        "execution": "standing_sync",
        "github": {
            "app_client_id": "Iv1.0123456789abcdef",
            "installation_id": 12345,
            "repository_id": 98765,
            "repository_owner": "ctower",
            "repository_name": "feedback",
            "private_key_binding_revision": "sha256:" + "a" * 64,
            "repository_selection": "selected",
            "permissions": {"issues": "write", "metadata": "read"},
            "import_updated_after": "2026-08-10T12:00:00Z",
            "page_size": 50,
            "poll_interval_seconds": 60,
        },
        "ctower": {"project_key": "ctower", "initial_custodian_id": str(commander_id)},
        "label_map": [{"github": "bug", "ctower": "security"}],
        "private_key_binding": "GITHUB_FEEDBACK_APP_PRIVATE_KEY",
    }


def _linked_ticket(tenant: TenantFixture) -> UUID:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT ticket_id FROM connector_issue_links
            WHERE tenant_id = %s
              AND connector_registration_key = 'github.feedback'
              AND external_ref = 'github:98765:429'
            """,
            (tenant.tenant_id,),
        ).fetchone()
    assert row is not None
    return cast(UUID, row["ticket_id"])


def _assert_mapping(tenant: TenantFixture, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT title, source_kind, source_ref FROM tickets
            WHERE tenant_id = %s AND ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
    assert row == {
        "title": "GitHub connector",
        "source_kind": "github-issue",
        "source_ref": "github:98765:429",
    }
