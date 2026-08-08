"""GitLab issue ingestion and proof-gated close against real ctower persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row
from support.acceptance import accept_pending_commands
from support.gitlab_connector import (
    Clock as _Clock,
)
from support.gitlab_connector import (
    ProviderFixture as _ProviderFixture,
)
from support.gitlab_connector import (
    activate_catalog_configuration as _activate_catalog_configuration,
)
from support.gitlab_connector import (
    integration_payload as _integration_payload,
)
from support.gitlab_connector import (
    proof_gate_close as _proof_gate_close,
)
from support.tenant_fixture import TenantFixture

from ctower_api.connectors.gitlab import GitLabIssueConnector, GitLabRuntimeRegistration
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.postgres import PostgresBoardContextFacts
from ctower_kernel.integrations import (
    ConnectorSyncError,
    IssueConnectorService,
)
from ctower_kernel.integrations.postgres import PostgresConnectorStore
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Intake

__all__: tuple[str, ...] = ()

_INTEGRATION_KEY = "gitlab.feedback"
_PROJECT_ID = 42
_ISSUE_IID = 7


def test_gitlab_issue_roundtrip_preserves_one_custody_chain_and_proof_gated_close(
    tenant: TenantFixture,
) -> None:
    """AC-GL-01/02/03: real DB + real HTTP Adapter over an honest GitLab fixture."""

    revision_id, revision_digest = _activate_catalog_configuration(tenant)
    runtime_revision = GitLabRuntimeRegistration.from_catalog(
        _integration_payload(tenant.commander_id),
        revision_id=revision_id,
        revision_digest=revision_digest,
    )
    registration = runtime_revision.registration
    provider = _ProviderFixture()
    client = httpx.Client(transport=httpx.MockTransport(provider.handle))
    adapter = GitLabIssueConnector(runtime_revision.config, token=str(uuid4()), client=client)
    clock = _Clock()
    record = PostgresRecord(tenant.database.runtime_dsn)
    sync = IssueConnectorService(
        adapter,
        PostgresConnectorStore(tenant.database.runtime_dsn),
        Intake(record),
        record,
        record.event_audit,
        BoardContextFacts(PostgresBoardContextFacts(tenant.database.runtime_dsn)),
        clock=clock,
    )
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)

    inactive = sync.tick(commander, registration.model_copy(update={"revision_id": uuid4()}))
    assert not inactive.claimed and provider.issue_list_calls == 0
    first = sync.tick(commander, registration)
    immediate = sync.tick(commander, registration)
    ticket_id = _linked_ticket(tenant)

    assert first.tickets_created == 1 and first.issues_seen == 1
    assert not immediate.claimed and provider.issue_list_calls == 1
    _assert_ingested_mapping(tenant, ticket_id)

    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    clock.now += timedelta(seconds=60)
    second = sync.tick(commander, registration)
    assert second.tickets_created == 0
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    provider.issue["description"] = "Feedback body after reporter edit"
    provider.issue["updated_at"] = "2026-08-08T08:04:00Z"
    clock.now += timedelta(seconds=60)
    update = sync.tick(commander, registration)
    assert update.ticket_updates == 1
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    _assert_update_comment(tenant, ticket_id)

    close_event_id = _proof_gate_close(tenant, ticket_id)
    clock.now += timedelta(seconds=60)
    closed = sync.tick(commander, registration)
    no_storm = sync.tick(commander, registration)

    assert closed.closures_delivered == 1
    assert provider.issue["state"] == "closed"
    assert len(provider.notes) == 1
    assert "current-proof gate" in provider.notes[0]
    assert f"ctower-sync:{close_event_id}" in provider.notes[0]
    assert not no_storm.claimed
    assert provider.note_posts == 1 and provider.close_puts == 1
    clock.now += timedelta(seconds=60)
    reflected_close = sync.tick(commander, registration)
    assert reflected_close.ticket_updates == 0 and reflected_close.closures_delivered == 0
    assert provider.note_posts == 1 and provider.close_puts == 1
    _assert_single_custody_and_delivery(tenant, ticket_id, close_event_id)


def test_gitlab_claim_lease_blocks_then_expires_and_fences_the_stale_worker(
    tenant: TenantFixture,
) -> None:
    revision_id, revision_digest = _activate_catalog_configuration(tenant)
    registration = GitLabRuntimeRegistration.from_catalog(
        _integration_payload(tenant.commander_id),
        revision_id=revision_id,
        revision_digest=revision_digest,
    ).registration
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    first_store = PostgresConnectorStore(tenant.database.runtime_dsn)
    second_store = PostgresConnectorStore(tenant.database.runtime_dsn)
    started_at = datetime(2026, 8, 8, 8, 2, tzinfo=UTC)

    first_claim = first_store.claim(actor, registration, owner_id=uuid4(), now=started_at)
    concurrent = second_store.claim(
        actor,
        registration,
        owner_id=uuid4(),
        now=started_at + registration.poll_interval,
    )

    assert first_claim is not None
    assert concurrent is None
    replacement = second_store.claim(
        actor,
        registration,
        owner_id=uuid4(),
        now=first_claim.expires_at,
    )
    assert replacement is not None
    assert replacement.fence > first_claim.fence
    with pytest.raises(ConnectorSyncError, match="stale or unavailable"):
        first_store.complete(
            actor,
            registration,
            first_claim,
            first_claim.cursor,
            first_claim.project_event_cursor,
            now=first_claim.expires_at,
        )
    with pytest.raises(ConnectorSyncError, match="stale, expired, or unavailable"):
        first_store.fail(actor, registration, first_claim, now=first_claim.expires_at)


def test_gitlab_failures_persist_an_increasing_retry_delay(tenant: TenantFixture) -> None:
    revision_id, revision_digest = _activate_catalog_configuration(tenant)
    registration = GitLabRuntimeRegistration.from_catalog(
        _integration_payload(tenant.commander_id),
        revision_id=revision_id,
        revision_digest=revision_digest,
    ).registration
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    store = PostgresConnectorStore(tenant.database.runtime_dsn)
    started_at = datetime(2026, 8, 8, 8, 2, tzinfo=UTC)

    first_claim = store.claim(actor, registration, owner_id=uuid4(), now=started_at)
    assert first_claim is not None
    store.fail(actor, registration, first_claim, now=started_at)
    first_due, first_failures = _retry_state(tenant)
    first_delay = first_due - started_at
    second_claim = store.claim(actor, registration, owner_id=uuid4(), now=first_due)
    assert second_claim is not None
    store.fail(actor, registration, second_claim, now=first_due)
    second_due, second_failures = _retry_state(tenant)
    second_delay = second_due - first_due

    assert (first_failures, second_failures) == (1, 2)
    assert second_delay > first_delay


def _linked_ticket(tenant: TenantFixture) -> UUID:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT ticket_id FROM connector_issue_links
            WHERE tenant_id = %s AND connector_registration_key = %s
              AND external_ref = %s
            """,
            (tenant.tenant_id, _INTEGRATION_KEY, "gitlab:42:7"),
        ).fetchall()
    assert len(rows) == 1
    return cast(UUID, rows[0]["ticket_id"])


def _assert_ingested_mapping(tenant: TenantFixture, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        ticket = connection.execute(
            """
            SELECT title, source_kind, source_ref FROM tickets
            WHERE tenant_id = %s AND ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
        inbound = connection.execute(
            """
            SELECT content FROM inbound_events
            WHERE tenant_id = %s AND source_kind = 'gitlab-issue'
              AND source_ref = 'gitlab:42:7'
            """,
            (tenant.tenant_id,),
        ).fetchone()
        observation = connection.execute(
            """
            SELECT source_labels, reporter_reference, reporter_display_name FROM
                connector_issue_observations
            WHERE tenant_id = %s AND connector_registration_key = %s
            """,
            (tenant.tenant_id, _INTEGRATION_KEY),
        ).fetchone()
    assert ticket == {
        "title": "Feedback title",
        "source_kind": "gitlab-issue",
        "source_ref": "gitlab:42:7",
    }
    assert inbound is not None and "Feedback body" in str(inbound["content"])
    assert inbound is not None and "Report Person (@reporter)" in str(inbound["content"])
    assert observation is not None
    assert observation["source_labels"] == ["bug", "feedback"]
    assert observation["reporter_reference"] == "@reporter"
    assert observation["reporter_display_name"] == "Report Person"


def _assert_update_comment(tenant: TenantFixture, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT payload->>'body' AS body FROM events
            WHERE tenant_id = %s AND aggregate_id = %s
              AND kind = 'ticket.comment_added'
            ORDER BY sequence
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchall()
    assert len(rows) == 1
    assert "Feedback body after reporter edit" in str(rows[0]["body"])


def _assert_single_custody_and_delivery(
    tenant: TenantFixture, ticket_id: UUID, event_id: UUID
) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM tickets WHERE tenant_id = %s
                    AND source_kind = 'gitlab-issue' AND source_ref = 'gitlab:42:7') AS tickets,
                (SELECT count(*) FROM connector_issue_links WHERE tenant_id = %s
                    AND ticket_id = %s) AS links,
                (SELECT count(*) FROM connector_close_deliveries WHERE tenant_id = %s
                    AND command_id = %s) AS deliveries
            """,
            (
                tenant.tenant_id,
                tenant.tenant_id,
                ticket_id,
                tenant.tenant_id,
                event_id,
            ),
        ).fetchone()
    assert counts == {"tickets": 1, "links": 1, "deliveries": 1}


def _retry_state(tenant: TenantFixture) -> tuple[datetime, int]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT next_poll_at, consecutive_failures
            FROM connector_sync_progress
            WHERE tenant_id = %s AND connector_registration_key = %s
            """,
            (tenant.tenant_id, _INTEGRATION_KEY),
        ).fetchone()
    assert row is not None
    return cast(datetime, row["next_poll_at"]), int(cast(int, row["consecutive_failures"]))
