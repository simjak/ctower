"""Two-registration real-PostgreSQL connector isolation acceptance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from support.acceptance import accept_pending_commands
from support.gitlab_connector import (
    Clock,
    ProviderFixture,
    activate_two_connector_configurations,
    connector_service,
    proof_gate_close,
)
from support.tenant_fixture import TenantFixture

from ctower_api.connectors.gitlab import GitLabRuntimeRegistration
from ctower_kernel.integrations import ConnectorSyncBatch, IssueConnectorService
from ctower_kernel.integrations.postgres import PostgresConnectorStore
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()


def test_phase1_two_active_registrations_are_isolated(tenant: TenantFixture) -> None:
    """CX-01: two real registrations share core without sharing any durable fact."""

    runtime_a, runtime_b = activate_two_connector_configurations(tenant)
    provider_a = ProviderFixture(project_id=42, issue_iid=7)
    provider_b = ProviderFixture(project_id=84, issue_iid=9)
    provider_b.issue["updated_at"] = "2026-08-08T08:01:30Z"
    clock = Clock()
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    record = PostgresRecord(tenant.database.runtime_dsn)
    store = PostgresConnectorStore(tenant.database.runtime_dsn)
    service_a = connector_service(tenant, runtime_a, provider_a, record, store, clock)
    service_b = connector_service(tenant, runtime_b, provider_b, record, store, clock)

    first_a = service_a.tick(actor, runtime_a.registration)
    first_b = service_b.tick(actor, runtime_b.registration)
    ticket_a = _linked_connector_ticket(tenant, "gitlab.feedback-a", "gitlab:42:7")
    ticket_b = _linked_connector_ticket(tenant, "gitlab.feedback-b", "gitlab:84:9")
    initial_a = _connector_state(tenant, "gitlab.feedback-a")
    initial_b = _connector_state(tenant, "gitlab.feedback-b")

    _assert_initial_isolation(
        first_a, first_b, ticket_a, ticket_b, initial_a, initial_b, runtime_a, runtime_b
    )
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    provider_a.issue["description"] = "Registration A independently advanced"
    provider_a.issue["updated_at"] = "2026-08-08T08:03:00Z"
    clock.now += timedelta(seconds=60)
    service_a.tick(actor, runtime_a.registration)
    advanced_a = _connector_state(tenant, "gitlab.feedback-a")
    unchanged_b = _connector_state(tenant, "gitlab.feedback-b")
    assert advanced_a.claim_fence > initial_a.claim_fence
    assert advanced_a.cursor_token != initial_a.cursor_token
    assert unchanged_b == initial_b

    close_a = proof_gate_close(tenant, ticket_a)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    clock.now += timedelta(seconds=60)
    service_a.tick(actor, runtime_a.registration)
    after_close_a = _connector_state(tenant, "gitlab.feedback-a")
    assert provider_a.note_posts == provider_a.close_puts == 1
    assert provider_b.note_posts == provider_b.close_puts == 0
    assert f"ctower-sync:{close_a}" in provider_a.notes[0]
    assert after_close_a.delivery_event_ids == (close_a,)
    assert _connector_state(tenant, "gitlab.feedback-b") == initial_b

    _close_registration_b_and_assert_isolation(
        tenant,
        service_b,
        actor,
        runtime_b,
        provider_a,
        provider_b,
        ticket_b,
        initial_b,
        after_close_a,
        clock,
    )


def _close_registration_b_and_assert_isolation(
    tenant: TenantFixture,
    service_b: IssueConnectorService,
    actor: Actor,
    runtime_b: GitLabRuntimeRegistration,
    provider_a: ProviderFixture,
    provider_b: ProviderFixture,
    ticket_b: UUID,
    initial_b: _ConnectorState,
    after_close_a: _ConnectorState,
    clock: Clock,
) -> None:
    provider_b.issue["description"] = "Registration B independently advanced"
    provider_b.issue["updated_at"] = "2026-08-08T08:06:00Z"
    clock.now += timedelta(seconds=60)
    service_b.tick(actor, runtime_b.registration)
    advanced_b = _connector_state(tenant, "gitlab.feedback-b")
    assert advanced_b.claim_fence > initial_b.claim_fence
    assert advanced_b.cursor_token != initial_b.cursor_token
    assert _connector_state(tenant, "gitlab.feedback-a") == after_close_a

    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    close_b = proof_gate_close(tenant, ticket_b)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    clock.now += timedelta(seconds=60)
    service_b.tick(actor, runtime_b.registration)
    final_a = _connector_state(tenant, "gitlab.feedback-a")
    final_b = _connector_state(tenant, "gitlab.feedback-b")
    assert provider_a.note_posts == provider_a.close_puts == 1
    assert provider_b.note_posts == provider_b.close_puts == 1
    assert f"ctower-sync:{close_b}" in provider_b.notes[0]
    assert final_a == after_close_a
    assert final_b.claim_fence > advanced_b.claim_fence
    assert final_b.cursor_token == advanced_b.cursor_token
    assert final_b.delivery_event_ids == (close_b,)
    assert final_a.external_refs == ("gitlab:42:7",)
    assert final_b.external_refs == ("gitlab:84:9",)


def _assert_initial_isolation(
    first_a: ConnectorSyncBatch,
    first_b: ConnectorSyncBatch,
    ticket_a: UUID,
    ticket_b: UUID,
    initial_a: _ConnectorState,
    initial_b: _ConnectorState,
    runtime_a: GitLabRuntimeRegistration,
    runtime_b: GitLabRuntimeRegistration,
) -> None:
    assert first_a.tickets_created == first_b.tickets_created == 1
    assert ticket_a != ticket_b
    assert initial_a.revision_digest != initial_b.revision_digest
    assert initial_a.registration_revision_id == runtime_a.registration.revision_id
    assert initial_b.registration_revision_id == runtime_b.registration.revision_id
    assert initial_a.registration_revision_id != initial_b.registration_revision_id
    assert initial_a.cursor_token != initial_b.cursor_token
    assert initial_a.claim_fence == initial_b.claim_fence == 1


def _linked_connector_ticket(
    tenant: TenantFixture, registration_key: str, external_ref: str
) -> UUID:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT ticket_id FROM connector_issue_links
            WHERE tenant_id = %s AND connector_registration_key = %s
              AND external_ref = %s
            """,
            (tenant.tenant_id, registration_key, external_ref),
        ).fetchone()
    assert row is not None
    return cast(UUID, row["ticket_id"])


@dataclass(frozen=True, slots=True)
class _ConnectorState:
    registration_revision_id: UUID
    revision_digest: bytes
    cursor_token: dict[str, object]
    claim_fence: int
    external_refs: tuple[str, ...]
    delivery_event_ids: tuple[UUID, ...]


def _connector_state(tenant: TenantFixture, registration_key: str) -> _ConnectorState:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        progress = connection.execute(
            """
            SELECT registration_revision_id, revision_digest, cursor_token, claim_fence
            FROM connector_sync_progress
            WHERE tenant_id = %s AND connector_registration_key = %s
            """,
            (tenant.tenant_id, registration_key),
        ).fetchone()
        links = connection.execute(
            """
            SELECT external_ref FROM connector_issue_links
            WHERE tenant_id = %s AND connector_registration_key = %s
            ORDER BY external_ref
            """,
            (tenant.tenant_id, registration_key),
        ).fetchall()
        deliveries = connection.execute(
            """
            SELECT command_id FROM connector_close_deliveries
            WHERE tenant_id = %s AND connector_registration_key = %s
            ORDER BY command_id
            """,
            (tenant.tenant_id, registration_key),
        ).fetchall()
    assert progress is not None
    return _ConnectorState(
        registration_revision_id=cast(UUID, progress["registration_revision_id"]),
        revision_digest=bytes(cast(bytes, progress["revision_digest"])),
        cursor_token=cast(dict[str, object], json.loads(str(progress["cursor_token"]))),
        claim_fence=int(cast(int, progress["claim_fence"])),
        external_refs=tuple(str(row["external_ref"]) for row in links),
        delivery_event_ids=tuple(cast(UUID, row["command_id"]) for row in deliveries),
    )
