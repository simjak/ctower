"""Real-Postgres Catalog activation, migration, and ticket-comment evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import rfc8785
from psycopg.rows import dict_row
from support.catalog import (
    FileSchemas,
    MemoryObjectStore,
    actor_for,
    minimal_bundle,
    telemetry_for,
)
from support.postgres import DatabaseFixture
from support.tenant_fixture import TenantFixture

from ctower_kernel.catalog import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    PostgresCatalog,
)
from ctower_kernel.record import Actor, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.comments import TicketCommentCommand, TicketCommentResult
from ctower_kernel.record.postgres import (
    PostgresRecord,
    provision_database_roles,
)

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "packages/ctower-kernel/migrations"
CATALOG_TABLES = {
    "catalog_components",
    "catalog_component_revisions",
    "catalog_payload_receipts",
    "catalog_component_dependencies",
    "catalog_component_provenance",
    "catalog_component_lifecycle_facts",
    "catalog_component_supersessions",
    "company_bundle_revisions",
    "company_bundle_members",
    "company_bundle_assignments",
    "company_bundle_secret_refs",
    "company_bundle_checks",
    "company_bundle_active",
}
IMMUTABLE_CATALOG_TABLES = CATALOG_TABLES - {"company_bundle_active"}
_SECOND_VERSION = 2
_SUPERSESSION_EVENT_COUNT = 2
_CONFLICT_STATUS = 409


def test_fresh_and_0023_upgrade_catalog_migrations_are_additive_and_least_privilege(
    database: DatabaseFixture,
) -> None:
    provision_database_roles(database.admin_dsn)
    manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    entries = cast(list[dict[str, object]], manifest["migrations"])
    with psycopg.connect(database.migrator_dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_admin")
        for entry in entries:
            path = str(entry["path"])
            if path > "0023_cp3c_privileges.sql" or entry.get("scope", "database") != "database":
                continue
            connection.execute((MIGRATIONS / path).read_text(encoding="utf-8"))
        _insert_upgrade_probe(connection)
        before = _authority_counts(connection)
        connection.execute((MIGRATIONS / "0024_catalog_authority.sql").read_text(encoding="utf-8"))
        connection.execute(
            (MIGRATIONS / "0025_ticket_comment_event.sql").read_text(encoding="utf-8")
        )
        assert _authority_counts(connection) == before
    with psycopg.connect(database.admin_dsn, row_factory=dict_row) as connection:
        tables = {
            str(row["table_name"])
            for row in connection.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            ).fetchall()
        }
        assert tables >= CATALOG_TABLES
        assert "comments" not in tables
        assert _constraint(connection, "events_kind_check") == {
            "attention.poison_disposition_recorded",
            "bootstrap.first_tenant_created",
            "catalog.bundle_activated",
            "catalog.component_published",
            "proof.changed",
            "routine.occurrence_recorded",
            "ticket.comment_added",
            "ticket.created",
            "ticket.custody_transferred",
            "work.changed",
            "workflow.changed",
        }
        subject_kinds = {"catalog", "proof", "ticket", "work", "workflow"}
        assert _constraint(connection, "event_links_subject_kind_check") == subject_kinds
        assert (
            _constraint(connection, "durability_subject_heads_subject_kind_check") == subject_kinds
        )
        _assert_catalog_privileges(connection)


def test_company_bundle_apply_replay_export_and_zero_diff_are_atomic(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    store = MemoryObjectStore()
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        store,
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 7, 24, tzinfo=UTC),
    )
    bundle = _tenant_bundle()
    before = _catalog_counts(tenant.database.admin_dsn)
    validation = catalog.validate(actor, bundle)
    plan = catalog.plan(actor, bundle)
    assert not isinstance(validation, CatalogProblem)
    assert not isinstance(plan, CatalogProblem)
    assert _catalog_counts(tenant.database.admin_dsn) == before
    command_id = uuid4()
    command = CompanyBundleApply(
        client_command_id=command_id,
        bundle=bundle,
        expected_active_version=0,
        plan_digest=plan.plan_digest,
    )

    applied = catalog.apply(actor, command, telemetry=telemetry_for(actor, command_id))
    replay = catalog.apply(actor, command, telemetry=telemetry_for(actor, command_id))

    assert isinstance(applied, CompanyBundleCommandResult)
    assert replay == applied
    assert applied.active_version == 1
    assert len(applied.event_ids) == len(bundle.resources) + 1
    exported = catalog.export(actor)
    assert not isinstance(exported, CatalogProblem)
    replanned = catalog.plan(actor, exported.bundle)
    assert not isinstance(replanned, CatalogProblem)
    assert exported.bundle_digest == applied.bundle_digest
    assert replanned.actions == ()
    assert replanned.proposed_bundle_digest == applied.bundle_digest
    _assert_catalog_commit(tenant.database.admin_dsn, command_id, len(applied.event_ids))
    _assert_successor_round_trip(
        catalog,
        actor,
        exported.bundle,
        tenant.database.admin_dsn,
        initial_event_count=len(applied.event_ids),
    )


def _assert_successor_round_trip(
    catalog: PostgresCatalog,
    actor: Actor,
    active_bundle: CompanyBundle,
    dsn: str,
    *,
    initial_event_count: int,
) -> None:
    changed = _superseding_bundle(active_bundle, "company.trusted-delivery")
    dependency = next(
        resource for resource in changed.resources if resource.component.key == "protected.cli"
    ).component.compatibility.requires[0]
    incomplete = changed.model_copy(
        update={
            "resources": tuple(
                resource
                for resource in changed.resources
                if resource.component.reference() != dependency
            )
        }
    )
    refused = catalog.plan(actor, incomplete)
    assert isinstance(refused, CatalogProblem)
    assert refused.code == "bundle-reference-invalid"
    second_plan = catalog.plan(actor, changed)
    assert not isinstance(second_plan, CatalogProblem)
    second_id = uuid4()
    second = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=second_id,
            bundle=changed,
            expected_active_version=1,
            plan_digest=second_plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, second_id),
    )
    assert isinstance(second, CompanyBundleCommandResult)
    assert second.active_version == _SECOND_VERSION
    assert len(second.event_ids) == _SUPERSESSION_EVENT_COUNT
    second_export = catalog.export(actor)
    assert not isinstance(second_export, CatalogProblem)
    second_replan = catalog.plan(actor, second_export.bundle)
    assert not isinstance(second_replan, CatalogProblem)
    assert second_replan.actions == ()
    assert second_replan.proposed_bundle_digest == second.bundle_digest
    assert _catalog_counts(dsn) == (
        len(active_bundle.resources) + 1,
        _SECOND_VERSION,
        initial_event_count + len(second.event_ids),
    )


def test_ticket_comment_is_canonical_replay_safe_and_table_free(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    record = PostgresRecord(tenant.database.runtime_dsn)
    create_id = uuid4()
    created = record.create_ticket(
        actor,
        TicketCommand(
            client_command_id=create_id,
            title="Comment authority",
            source=SourceReference("acceptance", "company-bundle"),
            priority="P1",
            initial_custodian_id=tenant.commander_id,
        ),
        request_digest=hashlib.sha256(b"create-comment-ticket").digest(),
        now=datetime(2026, 7, 24, tzinfo=UTC),
        telemetry=telemetry_for(actor, create_id),
    )
    assert not isinstance(created, RecordProblem)
    command_id = uuid4()
    command = TicketCommentCommand(
        client_command_id=command_id,
        ticket_id=created.ticket.ticket_id,
        body="Authenticated append-only note.",
    )
    request_digest = _digest(command.request_payload())

    comment = record.add_comment(
        actor,
        command,
        request_digest=request_digest,
        now=datetime(2026, 7, 24, 0, 1, tzinfo=UTC),
        telemetry=telemetry_for(actor, command_id),
    )
    replay = record.add_comment(
        actor,
        command,
        request_digest=request_digest,
        now=datetime(2026, 7, 24, 0, 2, tzinfo=UTC),
        telemetry=telemetry_for(actor, command_id),
    )

    assert isinstance(comment, TicketCommentResult)
    assert replay == comment
    timeline = record.ticket_timeline(
        actor,
        created.ticket.ticket_id,
        telemetry=telemetry_for(actor, command_id),
    )
    assert not isinstance(timeline, RecordProblem)
    assert [event.kind.value for event in timeline.events] == [
        "ticket.created",
        "ticket.comment_added",
    ]
    _assert_comment_commit(tenant.database.admin_dsn, command_id)


def test_cancelled_ticket_comment_is_durably_refused(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    record = PostgresRecord(tenant.database.runtime_dsn)
    ticket_id = _create_comment_ticket(record, actor, tenant, "Cancelled comment")
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE lifecycle_episodes SET state = 'cancelled'
            WHERE tenant_id = %s AND ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        )
    command_id = uuid4()
    command = TicketCommentCommand(
        client_command_id=command_id,
        ticket_id=ticket_id,
        body="This must remain absent.",
    )
    request_digest = _digest(command.request_payload())

    refused = record.add_comment(
        actor,
        command,
        request_digest=request_digest,
        now=datetime(2026, 7, 24, 0, 3, tzinfo=UTC),
        telemetry=telemetry_for(actor, command_id),
    )
    replay = record.add_comment(
        actor,
        command,
        request_digest=request_digest,
        now=datetime(2026, 7, 24, 0, 4, tzinfo=UTC),
        telemetry=telemetry_for(actor, command_id),
    )

    assert isinstance(refused, RecordProblem)
    assert replay == refused
    assert refused.code == "ticket-comment-ineligible"
    _assert_comment_refusal(tenant.database.admin_dsn, command_id, ticket_id)


def _insert_upgrade_probe(
    connection: psycopg.Connection[dict[str, object]],
) -> None:
    now = datetime(2026, 7, 24, tzinfo=UTC)
    tenant_id, principal_id = uuid4(), uuid4()
    connection.execute(
        "INSERT INTO tenants (tenant_id, slug, name, created_at) VALUES (%s, %s, %s, %s)",
        (tenant_id, "upgrade-probe", "Upgrade Probe", now),
    )
    connection.execute(
        """
        INSERT INTO principals (
            principal_id, tenant_id, kind, display_name, disabled,
            credential_ref, vault_ref, created_at
        ) VALUES (%s, %s, 'operator', 'Upgrade Operator', false, %s, %s, %s)
        """,
        (principal_id, tenant_id, "credential:upgrade", "vault:upgrade", now),
    )


def _authority_counts(
    connection: psycopg.Connection[dict[str, object]],
) -> tuple[int, int]:
    row = connection.execute(
        """
        SELECT (SELECT count(*) FROM tenants) AS tenant_count,
            (SELECT count(*) FROM principals) AS principal_count
        """
    ).fetchone()
    assert row is not None
    return int(cast(int, row["tenant_count"])), int(cast(int, row["principal_count"]))


def _constraint(connection: psycopg.Connection[dict[str, object]], name: str) -> set[str]:
    row = connection.execute(
        "SELECT pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conname = %s",
        (name,),
    ).fetchone()
    assert row is not None
    return set(re.findall(r"'([^']+)'", str(row["definition"])))


def _assert_catalog_privileges(
    connection: psycopg.Connection[dict[str, object]],
) -> None:
    for table in IMMUTABLE_CATALOG_TABLES:
        assert _privilege(connection, table, "SELECT")
        assert _privilege(connection, table, "INSERT")
        assert not _privilege(connection, table, "UPDATE")
        assert not _privilege(connection, table, "DELETE")
    assert _privilege(connection, "company_bundle_active", "SELECT")
    assert _privilege(connection, "company_bundle_active", "INSERT")
    assert not _privilege(connection, "company_bundle_active", "UPDATE")
    assert not _privilege(connection, "company_bundle_active", "DELETE")
    assert _column_privilege(connection, "company_bundle_active", "active_version", "UPDATE")
    assert not _column_privilege(connection, "company_bundle_active", "tenant_id", "UPDATE")


def _privilege(
    connection: psycopg.Connection[dict[str, object]],
    table: str,
    privilege: str,
) -> bool:
    row = connection.execute(
        "SELECT has_table_privilege('ctower_svc', %s, %s) AS value",
        (f"public.{table}", privilege),
    ).fetchone()
    assert row is not None
    return bool(row["value"])


def _column_privilege(
    connection: psycopg.Connection[dict[str, object]],
    table: str,
    column: str,
    privilege: str,
) -> bool:
    row = connection.execute(
        "SELECT has_column_privilege('ctower_svc', %s, %s, %s) AS value",
        (f"public.{table}", column, privilege),
    ).fetchone()
    assert row is not None
    return bool(row["value"])


def _catalog_counts(dsn: str) -> tuple[int, int, int]:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM catalog_component_revisions),
                (SELECT count(*) FROM company_bundle_revisions),
                (SELECT count(*) FROM events WHERE kind LIKE 'catalog.%')
            """
        ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


def _tenant_bundle() -> CompanyBundle:
    bundle = minimal_bundle()
    return bundle.model_copy(
        update={
            "company": bundle.company.model_copy(
                update={"key": "ctower", "display_name": "Ctower"}
            ),
            "resources": tuple(
                resource.model_copy(
                    update={
                        "component": resource.component.model_copy(
                            update={
                                "scope": resource.component.scope.model_copy(
                                    update={"tenant": "ctower"}
                                )
                            }
                        )
                    }
                )
                for resource in bundle.resources
            ),
        }
    )


def _superseding_bundle(bundle: CompanyBundle, key: str) -> CompanyBundle:
    resource = next(item for item in bundle.resources if item.component.key == key)
    previous = resource.component.reference()
    payload = {**resource.payload, "display_name": "Trusted delivery revision two"}
    digest = "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    replacement = resource.model_copy(
        update={
            "component": resource.component.model_copy(
                update={
                    "content_digest": digest,
                    "payload_ref": "object:" + digest,
                    "revision": previous.revision + 1,
                    "supersedes": previous,
                }
            ),
            "payload": payload,
        }
    )
    resources = tuple(
        replacement if item.component.key == key else item for item in bundle.resources
    )
    return bundle.model_copy(update={"resources": resources})


def _create_comment_ticket(
    record: PostgresRecord,
    actor: Actor,
    tenant: TenantFixture,
    title: str,
) -> UUID:
    command_id = uuid4()
    created = record.create_ticket(
        actor,
        TicketCommand(
            client_command_id=command_id,
            title=title,
            source=SourceReference("acceptance", "company-bundle"),
            priority="P1",
            initial_custodian_id=tenant.commander_id,
        ),
        request_digest=hashlib.sha256(title.encode()).digest(),
        now=datetime(2026, 7, 24, tzinfo=UTC),
        telemetry=telemetry_for(actor, command_id),
    )
    assert not isinstance(created, RecordProblem)
    return created.ticket.ticket_id


def _assert_catalog_commit(dsn: str, command_id: UUID, event_count: int) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        result = connection.execute(
            """
            SELECT cardinality(event_ids) AS event_count
            FROM command_results WHERE client_command_id = %s
            """,
            (command_id,),
        ).fetchone()
        facts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM company_bundle_active) AS active_count,
                (SELECT count(*) FROM company_bundle_revisions) AS bundle_count,
                (SELECT count(*) FROM catalog_component_revisions) AS component_count,
                (SELECT count(*) FROM outbox
                    WHERE event_id = ANY(
                        SELECT unnest(event_ids) FROM command_results
                        WHERE client_command_id = %s
                    )) AS outbox_count
            """,
            (command_id,),
        ).fetchone()
    assert result == {"event_count": event_count}
    assert facts == {
        "active_count": 1,
        "bundle_count": 1,
        "component_count": len(minimal_bundle().resources),
        "outbox_count": event_count,
    }


def _assert_comment_commit(dsn: str, command_id: UUID) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT event.kind, event.payload, result.event_ids, outbox.topic
            FROM command_results AS result
            JOIN events AS event ON event.event_id = result.event_ids[1]
            JOIN outbox ON outbox.event_id = event.event_id
            WHERE result.client_command_id = %s
            """,
            (command_id,),
        ).fetchone()
        comments_table = connection.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'comments'
            """
        ).fetchone()
    assert row is not None
    assert row["kind"] == "ticket.comment_added"
    assert row["payload"]["body"] == "Authenticated append-only note."
    assert len(row["event_ids"]) == 1
    assert row["topic"] == "record.events"
    assert comments_table is None


def _assert_comment_refusal(dsn: str, command_id: UUID, ticket_id: UUID) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        result = connection.execute(
            """
            SELECT status_code, response_body, event_ids
            FROM command_results WHERE client_command_id = %s
            """,
            (command_id,),
        ).fetchone()
        comments = connection.execute(
            """
            SELECT count(*) AS count FROM events
            WHERE aggregate_id = %s AND kind = 'ticket.comment_added'
            """,
            (ticket_id,),
        ).fetchone()
    assert result is not None
    assert result["status_code"] == _CONFLICT_STATUS
    assert result["response_body"]["code"] == "ticket-comment-ineligible"
    assert result["event_ids"] == []
    assert comments == {"count": 0}


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()
