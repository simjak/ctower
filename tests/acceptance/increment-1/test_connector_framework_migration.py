"""Nonempty 0054-to-0055 connector custody and receipt preservation proof."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from support.postgres import DatabaseFixture

from ctower_kernel.record.postgres import provision_database_roles

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "packages/ctower-kernel/migrations"
_TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")
_PRINCIPAL_ID = UUID("22222222-2222-4222-8222-222222222222")
_COMPONENT_ID = UUID("33333333-3333-4333-8333-333333333333")
_REVISION_ID = UUID("44444444-4444-4444-8444-444444444444")
_TICKET_ID = UUID("55555555-5555-4555-8555-555555555555")
_THREAD_ID = UUID("66666666-6666-4666-8666-666666666666")
_EVENT_ID = UUID("77777777-7777-4777-8777-777777777777")
_CLAIM_OWNER = UUID("88888888-8888-4888-8888-888888888888")
_DIGEST = bytes.fromhex("ab" * 32)
_PAYLOAD_DIGEST = bytes.fromhex("cd" * 32)
_ZERO_HASH = bytes(32)
_EVENT_HASH = bytes.fromhex("ef" * 32)
_NOW = datetime(2026, 8, 8, 8, tzinfo=UTC)


def test_connector_framework_migration_preserves_nonempty_gitlab_facts(
    database: DatabaseFixture,
) -> None:
    """0055 maps every 0054 authority row before removing provider-shaped tables."""

    provision_database_roles(database.admin_dsn)
    with psycopg.connect(database.migrator_dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_admin")
        _apply_database_migrations_through_0054(connection)
        _seed_0054_graph(connection)
        connection.execute((MIGRATIONS / "0055_connector_framework.sql").read_text())
        _assert_preserved_connector_graph(connection)


def _apply_database_migrations_through_0054(
    connection: psycopg.Connection[dict[str, object]],
) -> None:
    manifest = json.loads((MIGRATIONS / "manifest.json").read_text())
    for entry in cast(list[dict[str, object]], manifest["migrations"]):
        path = str(entry["path"])
        if (
            entry.get("scope", "database") == "database"
            and path <= "0054_gitlab_issue_integration.sql"
        ):
            connection.execute((MIGRATIONS / path).read_text())


def _seed_0054_graph(connection: psycopg.Connection[dict[str, object]]) -> None:
    connection.execute(
        """
        INSERT INTO tenants (tenant_id, slug, name, created_at)
        VALUES (%s, 'legacy', 'Legacy', %s)
        """,
        (_TENANT_ID, _NOW),
    )
    connection.execute(
        """
        INSERT INTO principals (
            principal_id, tenant_id, kind, display_name, disabled, created_at
        ) VALUES (%s, %s, 'commander', 'Legacy Commander', false, %s)
        """,
        (_PRINCIPAL_ID, _TENANT_ID, _NOW),
    )
    connection.execute(
        """
        INSERT INTO catalog_components (
            component_id, tenant_id, kind, component_key, created_at
        ) VALUES (%s, %s, 'integration', 'gitlab.feedback', %s)
        """,
        (_COMPONENT_ID, _TENANT_ID, _NOW),
    )
    connection.execute(
        """
        INSERT INTO catalog_component_revisions (
            component_revision_id, component_id, tenant_id, revision_number,
            content_digest, schema_ref, scope_project, compatibility_ctower,
            payload_ref, created_by, created_at
        ) VALUES (
            %s, %s, %s, 1, %s, 'ctower.integration/v2', NULL, '0.0.0',
            %s, %s, %s
        )
        """,
        (
            _REVISION_ID,
            _COMPONENT_ID,
            _TENANT_ID,
            _DIGEST,
            "object:sha256:" + _DIGEST.hex(),
            _PRINCIPAL_ID,
            _NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO tickets (
            ticket_id, tenant_id, title, source_kind, source_ref, priority,
            custodian_principal_id, version, durability_state, created_by, created_at,
            project_key
        ) VALUES (
            %s, %s, 'Legacy issue', 'gitlab-issue', 'gitlab:42:7', 'P2',
            %s, 1, 'durability_pending', %s, %s, 'ctower'
        )
        """,
        (_TICKET_ID, _TENANT_ID, _PRINCIPAL_ID, _PRINCIPAL_ID, _NOW),
    )
    connection.execute(
        """
        INSERT INTO inbound_threads (
            thread_id, tenant_id, project_key, version, created_by, created_at
        ) VALUES (%s, %s, 'ctower', 1, %s, %s)
        """,
        (_THREAD_ID, _TENANT_ID, _PRINCIPAL_ID, _NOW),
    )
    connection.execute(
        """
        INSERT INTO events (
            event_id, tenant_id, stream_id, aggregate_id, sequence, kind,
            schema_version, actor_principal_id, client_command_id,
            request_sha256, correlation_id, causation_id, origin, server_time,
            payload, prev_hash, event_hash, record_position
        ) VALUES (
            %s, %s, 'ticket:legacy', %s, 1, 'workflow.changed', 1, %s, %s,
            %s, %s, NULL, 'api', %s, %s, %s, %s, 1
        )
        """,
        (
            _EVENT_ID,
            _TENANT_ID,
            _TICKET_ID,
            _PRINCIPAL_ID,
            _EVENT_ID,
            _ZERO_HASH,
            _EVENT_ID,
            _NOW,
            Jsonb({"operation": "resolve_close"}),
            _ZERO_HASH,
            _EVENT_HASH,
        ),
    )
    connection.execute(
        """
        INSERT INTO integration_gitlab_sync_progress (
            tenant_id, integration_key, component_revision_id, revision_digest,
            gitlab_project_id, updated_after, page, project_event_cursor,
            next_poll_at, consecutive_failures, claim_owner, claim_fence,
            claim_expires_at, claimed_at, completed_at
        ) VALUES (%s, 'gitlab.feedback', %s, %s, 42, %s, 3, 19, %s, 2, %s, 7, %s, %s, NULL)
        """,
        (
            _TENANT_ID,
            _REVISION_ID,
            _DIGEST,
            _NOW,
            _NOW + timedelta(minutes=1),
            _CLAIM_OWNER,
            _NOW + timedelta(minutes=2),
            _NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO integration_gitlab_issue_links (
            tenant_id, integration_key, source_component_revision_id,
            source_revision_digest, gitlab_project_id, issue_iid, ticket_id,
            thread_id, web_url, linked_at
        ) VALUES (
            %s, 'gitlab.feedback', %s, %s, 42, 7, %s, %s,
            'https://gitlab.example.test/group/project/-/issues/7', %s
        )
        """,
        (_TENANT_ID, _REVISION_ID, _DIGEST, _TICKET_ID, _THREAD_ID, _NOW),
    )
    connection.execute(
        """
        INSERT INTO integration_gitlab_issue_observations (
            tenant_id, integration_key, component_revision_id,
            gitlab_project_id, issue_iid, payload_digest, title, body, labels,
            reporter_username, reporter_name, issue_state, web_url,
            source_updated_at, observed_at
        ) VALUES (
            %s, 'gitlab.feedback', %s, 42, 7, %s, 'Legacy issue',
            'Legacy body', ARRAY['bug'], %s, 'Legacy Reporter', 'opened',
            'https://gitlab.example.test/group/project/-/issues/7', %s, %s
        )
        """,
        (_TENANT_ID, _REVISION_ID, _PAYLOAD_DIGEST, "r" * 255, _NOW, _NOW),
    )
    connection.execute(
        """
        INSERT INTO integration_gitlab_close_deliveries (
            tenant_id, integration_key, component_revision_id,
            gitlab_project_id, issue_iid, ticket_id, event_id,
            comment_created, issue_closed, delivered_at
        ) VALUES (
            %s, 'gitlab.feedback', %s, 42, 7, %s, %s, true, true, %s
        )
        """,
        (_TENANT_ID, _REVISION_ID, _TICKET_ID, _EVENT_ID, _NOW),
    )


def _assert_preserved_connector_graph(
    connection: psycopg.Connection[dict[str, object]],
) -> None:
    counts = {
        table: _table_count(connection, table)
        for table in (
            "connector_sync_progress",
            "connector_issue_links",
            "connector_issue_observations",
            "connector_close_deliveries",
        )
    }
    assert counts == dict.fromkeys(counts, 1)
    progress = connection.execute("SELECT * FROM connector_sync_progress").fetchone()
    link = connection.execute("SELECT * FROM connector_issue_links").fetchone()
    observation = connection.execute("SELECT * FROM connector_issue_observations").fetchone()
    delivery = connection.execute("SELECT * FROM connector_close_deliveries").fetchone()
    assert (
        progress is not None
        and link is not None
        and observation is not None
        and delivery is not None
    )
    cursor = json.loads(str(progress["cursor_token"]))
    assert cursor == {
        "page": 3,
        "schema": "ctower.gitlab-cursor/v1",
        "updated_after": "2026-08-08T08:00:00+00:00",
    }
    assert (progress["claim_owner"], progress["claim_fence"]) == (_CLAIM_OWNER, 7)
    assert (link["connector_kind"], link["external_ref"], link["ticket_id"]) == (
        "gitlab-issue",
        "gitlab:42:7",
        _TICKET_ID,
    )
    assert observation["payload_digest"] == _PAYLOAD_DIGEST
    assert observation["reporter_reference"] == "@" + "r" * 255
    assert (delivery["command_id"], delivery["marker_present"], delivery["issue_closed"]) == (
        _EVENT_ID,
        True,
        True,
    )
    old_tables = connection.execute(
        """
        SELECT to_regclass('integration_gitlab_sync_progress') AS progress,
            to_regclass('integration_gitlab_issue_links') AS links,
            to_regclass('integration_gitlab_issue_observations') AS observations,
            to_regclass('integration_gitlab_close_deliveries') AS deliveries
        """
    ).fetchone()
    assert old_tables == {
        "progress": None,
        "links": None,
        "observations": None,
        "deliveries": None,
    }


def _table_count(connection: psycopg.Connection[dict[str, object]], table: str) -> int:
    row = connection.execute(
        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
    ).fetchone()
    assert row is not None
    return int(cast(int, row["count"]))
