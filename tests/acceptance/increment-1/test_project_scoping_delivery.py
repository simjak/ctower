"""Project Delivery and scoped intake acceptance evidence for #185."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
from support.acceptance import accept_pending_commands
from support.project_scoping import (
    _BHLOOP_CHECKPOINTS,
    _CTOWER_CHECKPOINTS,
    _MANIBO_CHECKPOINTS,
    HTTP_ACCEPTED,
    HTTP_UNPROCESSABLE,
    _apply_portfolio_bundle,
    _bind_viewer,
    _client,
    _created_ticket_id,
    _definition_order,
    _link_foreign_ticket,
    _submit_direct_ticket,
    _submit_intake,
    _submit_link_intake,
    _telemetry,
)
from support.tenant_fixture import TenantFixture

from ctower_kernel.projections import BoardQuery, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Block, Work, WorkReceipt
from ctower_kernel.work.postgres import PostgresWork


def test_foreign_project_projection_reads_are_refused_before_materialization(
    tenant: TenantFixture,
) -> None:
    """A viewer bound only to manibo cannot read ctower Board or Delivery rows."""
    _apply_portfolio_bundle(tenant)
    with _client(tenant) as client:
        foreign_ticket = _created_ticket_id(
            _submit_intake(client, tenant, "ctower", "ctower-R3048")
        )
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    projections.catch_up(tenant.tenant_id)
    projections.reconcile_project_delivery(tenant.tenant_id, now=datetime.now(UTC))
    viewer = _bind_viewer(tenant, project_keys=("manibo",))

    board = projections.board(viewer, BoardQuery(project_key="ctower"))
    assert isinstance(board, RecordProblem), (
        f"HTTP 200 with foreign card {foreign_ticket}: {board.response_payload()}"
    )
    assert (board.status, board.code) == (403, "project-scope-denied")

    delivery = projections.project_delivery(viewer, "ctower")
    assert isinstance(delivery, RecordProblem), (
        f"HTTP 200 with foreign Project Delivery rows: {delivery!r}"
    )
    assert (delivery.status, delivery.code) == (403, "project-scope-denied")


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

    assert not isinstance(manibo, RecordProblem), manibo
    assert not isinstance(bhloop, RecordProblem), bhloop
    assert affected == (
        len(_CTOWER_CHECKPOINTS) + len(_MANIBO_CHECKPOINTS) + len(_BHLOOP_CHECKPOINTS)
    )
    assert _definition_order(tenant, "ctower") == _CTOWER_CHECKPOINTS
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

    assert not isinstance(view, RecordProblem), view
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
    assert not isinstance(after, RecordProblem), after
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
