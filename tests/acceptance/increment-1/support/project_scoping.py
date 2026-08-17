"""Shared fixtures and HTTP helpers for project-scoping acceptance tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
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
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture, provision_seat

from ctower_api.interface import create_app
from ctower_kernel.catalog import CatalogProblem, CompanyBundle, PostgresCatalog
from ctower_kernel.projections import BoardQuery, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.human_identity import HumanRoleBindingIssue
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()
HTTP_ACCEPTED = 202
HTTP_NOT_FOUND = 404
HTTP_FORBIDDEN = 403
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
_CTOWER_CHECKPOINTS = (
    "I1.0",
    "I1.1",
    "I1.2",
    "I1.3",
    "I1.4",
    "I1.5",
    "I1.6",
    "I1.7",
    "I2.1",
    "I2.2",
    "I2.3",
    "I2.4",
    "I2.5",
    "I2.6",
)


def _assert_pair_disjoint(tenant: TenantFixture, left: str, right: str) -> None:
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
    assert not isinstance(left_board, RecordProblem), left_board
    assert not isinstance(right_board, RecordProblem), right_board

    assert {card.ticket_id for card in left_board.cards} == {left_ticket}
    assert {card.ticket_id for card in right_board.cards} == {right_ticket}
    assert not (
        {card.ticket_id for card in left_board.cards}
        & {card.ticket_id for card in right_board.cards}
    )
    with _client(tenant) as client:
        assert _get_ticket(
            client, tenant, left_ticket, right
        ).status_code == _expected_project_read_status(right)
        assert _get_ticket(
            client, tenant, right_ticket, left
        ).status_code == _expected_project_read_status(left)
        for suffix in ("timeline", "assignments", "audit"):
            assert _get_ticket_child(
                client, tenant, left_ticket, right, suffix
            ).status_code == _expected_project_read_status(right)
        second_left = _created_ticket_id(_submit_intake(client, tenant, left, f"{left}-R104"))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    left_after = projections.board(actor, BoardQuery(project_key=left))
    right_after = projections.board(actor, BoardQuery(project_key=right))
    assert not isinstance(left_after, RecordProblem), left_after
    assert not isinstance(right_after, RecordProblem), right_after
    assert {card.ticket_id for card in left_after.cards} == {left_ticket, second_left}
    assert {card.ticket_id for card in right_after.cards} == {right_ticket}
    assert left_after.source_watermark > left_board.source_watermark
    assert right_after.source_watermark == right_board.source_watermark
    assert right_after.projection_watermark == right_board.projection_watermark


def _scoped_projection_fixture(
    tenant: TenantFixture,
) -> tuple[Projections, Actor, Actor, UUID]:
    _apply_portfolio_bundle(tenant)
    with _client(tenant) as client:
        _created_ticket_id(_submit_intake(client, tenant, "ctower", "ctower-R3048"))
        manibo_ticket = _created_ticket_id(_submit_intake(client, tenant, "manibo", "manibo-R3048"))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    projections.catch_up(tenant.tenant_id)
    projections.reconcile_project_delivery(tenant.tenant_id, now=datetime.now(UTC))
    principal_id, _credential = provision_seat(tenant, "r3048-manibo-reader", project_key="manibo")
    scoped_actor = Actor(
        principal_id,
        tenant.tenant_id,
        PrincipalKind.COMMANDER,
        project_grants=frozenset({"manibo"}),
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    return projections, scoped_actor, operator, manibo_ticket


def _expected_project_read_status(project_key: str) -> int:
    """The fixture Commander has only the bootstrap ``ctower`` Project grant."""

    return HTTP_NOT_FOUND if project_key == "ctower" else HTTP_FORBIDDEN


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


def _bind_viewer(tenant: TenantFixture, *, project_keys: tuple[str, ...]) -> Actor:
    record = PostgresRecord(tenant.database.runtime_dsn)
    subject = f"r3048-viewer-{uuid4().hex}"
    receipt = record.human_identity.bind_role(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        HumanRoleBindingIssue(
            client_command_id=uuid4(),
            display_name="R3048 viewer",
            oidc_issuer="https://r3048.example.test",
            oidc_subject=subject,
            project_keys=project_keys,
            role="viewer",
        ),
        request_digest=hashlib.sha256(subject.encode()).digest(),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )
    assert not isinstance(receipt, RecordProblem), receipt
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    resolved = record.human_identity.resolve_role_binding("https://r3048.example.test", subject)
    assert resolved is not None
    return resolved[1]


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
