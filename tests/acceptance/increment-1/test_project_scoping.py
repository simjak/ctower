"""Three-project Board, ticket, intake, and checkpoint isolation evidence for #185."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from support.acceptance import accept_pending_commands
from support.catalog import (
    FileSchemas,
    MemoryObjectStore,
    actor_for,
    apply_initial_bundle,
    minimal_bundle,
)
from support.project_hierarchy import declare_ctower_project
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.catalog import CatalogProblem, CompanyBundle, PostgresCatalog
from ctower_kernel.projections import BoardQuery, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Block, Work, WorkReceipt
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()
HTTP_ACCEPTED = 202
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422

_MANIBO_CHECKPOINTS = (
    "manibo.verify",
    "manibo.staging-infra",
    "manibo.images-published",
    "manibo.staging-deployed",
    "manibo.staging-nfq-e2e",
    "manibo.production-released",
    "manibo.production-nfq-e2e",
)
_BHLOOP_CHECKPOINTS = (
    "bhloop.contract-admission",
    "bhloop.d11-technical",
    "bhloop.production-foundation",
    "bhloop.layer-1-foundation",
    "bhloop.layer-2-staff-assistant",
    "bhloop.d11-org",
    "bhloop.biomarker-rail",
)


def test_manibo_and_ctower_boards_are_disjoint(tenant: TenantFixture) -> None:
    _assert_pair_disjoint(tenant, "manibo", "ctower")


def test_bhloop_and_ctower_boards_are_disjoint(tenant: TenantFixture) -> None:
    _assert_pair_disjoint(tenant, "bh-loop", "ctower")


def test_manibo_and_bhloop_boards_are_disjoint(tenant: TenantFixture) -> None:
    _assert_pair_disjoint(tenant, "manibo", "bh-loop")


def test_starter_bundles_apply_and_render_ordered_project_delivery_rows(
    tenant: TenantFixture,
) -> None:
    _apply_portfolio_bundle(tenant)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    projections.catch_up(tenant.tenant_id)
    affected = projections.reconcile_project_delivery(tenant.tenant_id, now=datetime.now(UTC))
    actor = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    manibo = projections.project_delivery(actor, "manibo")
    bhloop = projections.project_delivery(actor, "bh-loop")

    assert affected == len(_MANIBO_CHECKPOINTS) + len(_BHLOOP_CHECKPOINTS)
    assert _definition_order(tenant, "manibo") == _MANIBO_CHECKPOINTS
    assert _definition_order(tenant, "bh-loop") == _BHLOOP_CHECKPOINTS
    assert manibo is not None and bhloop is not None
    assert tuple(row.checkpoint_key for row in manibo.rows) == _MANIBO_CHECKPOINTS
    assert tuple(row.checkpoint_key for row in bhloop.rows) == _BHLOOP_CHECKPOINTS
    assert not (
        {row.checkpoint_key for row in manibo.rows} & {row.checkpoint_key for row in bhloop.rows}
    )


def test_project_delivery_excludes_foreign_project_ticket_facts(
    tenant: TenantFixture,
) -> None:
    _apply_portfolio_bundle(tenant)
    with _client(tenant) as client:
        foreign_ticket = _created_ticket_id(
            _submit_intake(client, tenant, "bh-loop", "bh-loop-R103")
        )
    blocker_id = uuid4()
    actor = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    blocked = Work(
        PostgresRecord(tenant.database.runtime_dsn),
        writer=PostgresWork(tenant.database.runtime_dsn),
    ).execute(
        actor,
        Block(
            client_command_id=uuid4(),
            ticket_id=foreign_ticket,
            expected_version=1,
            reason="Foreign project dependency",
            blocker_id=blocker_id,
            blocker_kind="dependency",
            reason_class="external_dependency",
            owner_principal_id=tenant.commander_id,
            source_ref="test:foreign-project-blocker",
            affected_stage=None,
            resolution_condition="Foreign dependency clears",
            next_check_at=datetime.now(UTC) + timedelta(hours=1),
            dependency_ref=None,
            board_impact=True,
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(blocked, WorkReceipt), blocked
    _link_foreign_ticket(tenant, foreign_ticket)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    projections.catch_up(tenant.tenant_id)
    projections.reconcile_project_delivery(tenant.tenant_id, now=datetime.now(UTC))
    view = projections.project_delivery(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR), "manibo"
    )

    assert view is not None
    row = next(item for item in view.rows if item.checkpoint_key == "manibo.verify")
    assert row.headline_state.value == "blocked"
    assert row.underlying_maturity.value == "planned"
    assert row.health == "STATE_UNKNOWN"
    assert f"ticket:{foreign_ticket}" not in row.source_ids
    assert f"blocker:{blocker_id}" not in row.derivation_reasons
    assert "slot_unknown:foreign-project-proof" in row.derivation_reasons
    with _client(tenant) as client:
        _created_ticket_id(_submit_intake(client, tenant, "bh-loop", "bh-loop-R105"))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    projections.reconcile_project_delivery(
        tenant.tenant_id, now=datetime.now(UTC) + timedelta(seconds=1)
    )
    after = projections.project_delivery(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR), "manibo"
    )
    assert after is not None
    assert after.source_record_position == view.source_record_position
    assert after.projection_record_position == view.projection_record_position
    assert after.projection_semantic_digest == view.projection_semantic_digest


def test_intake_accepts_scoped_ref_and_refuses_mismatched_project_ref(
    tenant: TenantFixture,
) -> None:
    _apply_portfolio_bundle(tenant)
    with _client(tenant) as client:
        accepted = _submit_intake(client, tenant, "manibo", "manibo-R001")
        refused = _submit_intake(client, tenant, "manibo", "bh-loop-R002")

    assert accepted.status_code == HTTP_ACCEPTED
    assert accepted.json()["project_key"] == "manibo"
    assert refused.status_code == HTTP_UNPROCESSABLE
    assert refused.json()["code"] == "intake-source-project-mismatch"


def test_link_intake_uses_ticket_scope_without_import_provenance_binding(
    tenant: TenantFixture,
) -> None:
    declare_ctower_project(tenant)
    _apply_portfolio_bundle(tenant)
    with _client(tenant) as client:
        created = _submit_direct_ticket(client, tenant, "ctower")
        ticket_id = UUID(str(created.json()["ticket"]["ticket_id"]))
        with psycopg.connect(tenant.database.admin_dsn) as connection:
            binding = connection.execute(
                """
                SELECT 1 FROM ticket_project_bindings
                WHERE tenant_id = %s AND ticket_id = %s
                """,
                (tenant.tenant_id, ticket_id),
            ).fetchone()
        linked = _submit_link_intake(client, tenant, "ctower", ticket_id)

    assert created.status_code == HTTP_ACCEPTED
    assert binding is None
    assert linked.status_code == HTTP_ACCEPTED, linked.json()
    assert UUID(str(linked.json()["ticket_id"])) == ticket_id


def _assert_pair_disjoint(tenant: TenantFixture, left: str, right: str) -> None:
    declare_ctower_project(tenant)
    _apply_portfolio_bundle(tenant)
    with _client(tenant) as client:
        left_ticket = _created_ticket_id(_submit_intake(client, tenant, left, f"{left}-R101"))
        right_ticket = _created_ticket_id(_submit_intake(client, tenant, right, f"{right}-R102"))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    projections.catch_up(tenant.tenant_id)
    actor = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    left_board = projections.board(actor, BoardQuery(project_key=left))
    right_board = projections.board(actor, BoardQuery(project_key=right))

    assert {card.ticket_id for card in left_board.cards} == {left_ticket}
    assert {card.ticket_id for card in right_board.cards} == {right_ticket}
    assert not (
        {card.ticket_id for card in left_board.cards}
        & {card.ticket_id for card in right_board.cards}
    )
    with _client(tenant) as client:
        assert _get_ticket(client, tenant, left_ticket, right).status_code == HTTP_NOT_FOUND
        assert _get_ticket(client, tenant, right_ticket, left).status_code == HTTP_NOT_FOUND
        for suffix in ("timeline", "assignments", "audit"):
            assert (
                _get_ticket_child(client, tenant, left_ticket, right, suffix).status_code
                == HTTP_NOT_FOUND
            )
        second_left = _created_ticket_id(_submit_intake(client, tenant, left, f"{left}-R104"))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    left_after = projections.board(actor, BoardQuery(project_key=left))
    right_after = projections.board(actor, BoardQuery(project_key=right))
    assert {card.ticket_id for card in left_after.cards} == {left_ticket, second_left}
    assert {card.ticket_id for card in right_after.cards} == {right_ticket}
    assert left_after.source_watermark > left_board.source_watermark
    assert right_after.source_watermark == right_board.source_watermark
    assert right_after.projection_watermark == right_board.projection_watermark


def _apply_portfolio_bundle(tenant: TenantFixture) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 8, 1, tzinfo=UTC),
    )
    bundle = _tenant_bundle()
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem), plan
    apply_initial_bundle(catalog, actor, bundle)


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


def _definition_order(tenant: TenantFixture, project_key: str) -> tuple[str, ...]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT checkpoint_key FROM project_delivery_checkpoint_definitions
            WHERE tenant_id = %s AND project_key = %s
            ORDER BY ordered_position, checkpoint_key
            """,
            (tenant.tenant_id, project_key),
        ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _link_foreign_ticket(tenant: TenantFixture, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        definition = connection.execute(
            """
            SELECT checkpoint_definition_id
            FROM project_delivery_checkpoint_definitions
            WHERE tenant_id = %s AND project_key = 'manibo'
              AND checkpoint_key = 'manibo.verify'
            """,
            (tenant.tenant_id,),
        ).fetchone()
        assert definition is not None
        connection.execute(
            """
            INSERT INTO project_delivery_exit_criteria (
                checkpoint_definition_id, tenant_id, criterion_key, ordinal,
                description, proof_ticket_id, proof_criterion_key, source_ids
            ) VALUES (%s, %s, 'foreign-project-proof', 2,
                'Foreign project facts must fail closed', %s, 'foreign-proof', ARRAY[]::text[])
            """,
            (definition[0], tenant.tenant_id, ticket_id),
        )


def _client(tenant: TenantFixture) -> TestClient:
    record = PostgresRecord(tenant.database.runtime_dsn)
    return TestClient(
        create_app(
            record,
            work=Work(record, writer=PostgresWork(tenant.database.runtime_dsn)),
        ),
        client=("127.0.0.1", 51000),
    )


def _submit_intake(
    client: TestClient,
    tenant: TenantFixture,
    project_key: str,
    source_ref: str,
) -> Response:
    command_id = uuid4()
    return cast(
        Response,
        client.post(
            "/v1/intake",
            json={
                "content": f"Create {project_key} scoped work",
                "initial_custodian_id": str(tenant.commander_id),
                "intent": "create_ticket",
                "priority": "P2",
                "project_key": project_key,
                "source": {"kind": "mission-control-request", "ref": source_ref},
                "title": f"{project_key} scoped ticket",
            },
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        ),
    )


def _submit_direct_ticket(
    client: TestClient,
    tenant: TenantFixture,
    project_key: str,
) -> Response:
    command_id = uuid4()
    return cast(
        Response,
        client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(tenant.commander_id),
                "priority": "P2",
                "project_key": project_key,
                "source": {"kind": "github-issue", "ref": f"{project_key}-direct-1"},
                "title": f"{project_key} direct ticket",
            },
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        ),
    )


def _submit_link_intake(
    client: TestClient,
    tenant: TenantFixture,
    project_key: str,
    ticket_id: UUID,
) -> Response:
    command_id = uuid4()
    return cast(
        Response,
        client.post(
            "/v1/intake",
            json={
                "content": f"Link scoped intake to {ticket_id}",
                "expected_ticket_version": 1,
                "intent": "link_ticket",
                "project_key": project_key,
                "source": {
                    "kind": "mission-control-request",
                    "ref": f"{project_key}-R003",
                },
                "target_ticket_id": str(ticket_id),
            },
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        ),
    )


def _get_ticket(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    project_key: str,
) -> Response:
    return cast(
        Response,
        client.get(
            f"/v1/tickets/{ticket_id}",
            params={"project_key": project_key},
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(),
            },
        ),
    )


def _get_ticket_child(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    project_key: str,
    suffix: str,
) -> Response:
    return cast(
        Response,
        client.get(
            f"/v1/tickets/{ticket_id}/{suffix}",
            params={"project_key": project_key},
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(),
            },
        ),
    )


def _telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test-tenant",
        actor_id="test-actor",
        command_id=command_id,
    )


def _created_ticket_id(response: Response) -> UUID:
    assert response.status_code == HTTP_ACCEPTED, response.text
    return UUID(str(response.json()["ticket_id"]))
