"""Executed least-privilege evidence for Proof and Workflow persistence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from support.postgres import DatabaseFixture
from support.server import running_api, start_and_admit
from support.tenant_fixture import TenantFixture, create_second_tenant

from ctower_client import (
    CtowerClient,
    EvidenceRequest,
    FreezeCriteriaRequest,
    Priority,
    ProofCriterion,
    ResolveCloseRequest,
    SourceReference,
    TicketCreateRequest,
    VerdictDecision,
    VerdictRequest,
    WorkflowTransitionRequest,
)
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record.postgres import provision_database_roles

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "packages/ctower-kernel/migrations"

HEAD_UPDATE_COLUMNS = {
    "proof_bundles": {
        "proof_id": False,
        "ticket_id": False,
        "tenant_id": False,
        "version": True,
        "candidate_digest": True,
        "candidate_author_id": False,
        "frozen_at": False,
    },
    "workflow_runs": {
        "workflow_run_id": False,
        "ticket_id": False,
        "tenant_id": False,
        "workflow_key": False,
        "workflow_revision": False,
        "initial_stage": False,
        "current_stage": True,
        "activity_class": True,
        "version": True,
        "created_at": False,
        "episode_number": False,
        "workflow_digest": False,
        "execution_policy_ref": False,
        "execution_policy_digest": False,
        "gate_policy_ref": False,
        "gate_policy_digest": False,
        "evidence_policy_ref": False,
        "evidence_policy_digest": False,
        "started_by": False,
    },
}

CP2_HEAD_UPDATE_COLUMNS = {
    "tickets": {
        "ticket_id": False,
        "tenant_id": False,
        "title": False,
        "source_kind": False,
        "source_ref": False,
        "priority": True,
        "custodian_principal_id": True,
        "version": True,
        "durability_state": False,
        "created_by": False,
        "created_at": False,
        "current_episode": True,
    },
    "lifecycle_episodes": {
        "ticket_id": False,
        "tenant_id": False,
        "episode_number": False,
        "state": True,
        "opened_at": False,
        "closed_at": True,
    },
    "assignment_intervals": {
        "ticket_id": False,
        "tenant_id": False,
        "interval_sequence": False,
        "assignment_kind": False,
        "principal_id": False,
        "assigned_at": False,
        "released_at": True,
        "changed_by": False,
        "reason": False,
        "client_command_id": False,
        "scope_ref": False,
        "episode_number": False,
    },
    "blocker_heads": {
        "blocker_id": False,
        "ticket_id": False,
        "tenant_id": False,
        "blocker_kind": False,
        "reason_class": False,
        "reason": False,
        "owner_principal_id": False,
        "source_ref": False,
        "affected_stage": False,
        "resolution_condition": False,
        "next_check_at": False,
        "dependency_ref": False,
        "board_impact": False,
        "opened_at": False,
        "resolved_at": True,
        "resolution_evidence_ref": True,
    },
}

APPEND_ONLY_TABLES = (
    "proof_criteria",
    "proof_objects",
    "proof_evidence",
    "proof_verdicts",
    "proof_invalidations",
    "workflow_transition_facts",
    "lifecycle_facts",
    "priority_facts",
    "admission_facts",
    "blocker_facts",
    "ticket_relations",
)


def test_fresh_database_narrows_head_update_privileges(tenant: TenantFixture) -> None:
    ticket_id = _exercise_public_proof_workflow_commands(tenant)

    _assert_immutable_workflow_pin_update_is_denied(tenant, ticket_id)
    _assert_runtime_role_privileges(tenant.database.admin_dsn)


def test_projection_login_assumes_only_projection_and_reset_cannot_escape(
    tenant: TenantFixture,
) -> None:
    projection_dsn = tenant.database.projection_dsn
    stale_login = psycopg.connect(projection_dsn, autocommit=True)
    try:
        provision_database_roles(tenant.database.admin_dsn)
        with pytest.raises(psycopg.OperationalError):
            stale_login.execute("SELECT 1")
    finally:
        stale_login.close()

    view = Projections(PostgresProjections(projection_dsn)).catch_up(tenant.tenant_id)
    assert view.projection_watermark == view.source_watermark

    with psycopg.connect(projection_dsn, autocommit=True, row_factory=dict_row) as connection:
        assert _current_user(connection) == "ctower_projection_runtime"
        _assert_projection_login_cannot_escape(connection)
        connection.execute("SET ROLE ctower_projection")
        assert _current_user(connection) == "ctower_projection"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("UPDATE tickets SET version = version WHERE false")
        connection.execute("RESET ROLE")
        _assert_projection_login_cannot_escape(connection)


def _assert_projection_login_cannot_escape(
    connection: psycopg.Connection[dict[str, object]],
) -> None:
    for statement in (
        "UPDATE tickets SET version = version WHERE false",
        "CREATE TABLE projection_privilege_escape (value integer)",
        "SET ROLE ctower_svc",
        "SET ROLE ctower_admin",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(statement)


def _current_user(connection: psycopg.Connection[dict[str, object]]) -> str:
    row = connection.execute("SELECT current_user AS value").fetchone()
    assert row is not None
    return str(row["value"])


def test_upgrade_database_corrects_existing_head_privileges(
    database: DatabaseFixture,
) -> None:
    provision_database_roles(database.admin_dsn)
    with psycopg.connect(database.migrator_dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        for name in (
            "0002_ticket_slice.sql",
            "0003_privileges.sql",
            "0004_proof_workflow.sql",
            "0005_proof_verdict_sequence.sql",
        ):
            connection.execute((MIGRATIONS / name).read_text(encoding="utf-8"))

    _assert_legacy_heads_have_table_wide_update(database.admin_dsn)
    with psycopg.connect(database.migrator_dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        for name in (
            "0006_narrow_head_update_privileges.sql",
            "0007_task_management_facts.sql",
            "0008_board_projection.sql",
            "0009_transactional_record_positions.sql",
            "0010_custody_episode_intervals.sql",
            "0011_persisted_command_refusals.sql",
        ):
            connection.execute((MIGRATIONS / name).read_text(encoding="utf-8"))

    tenant = create_second_tenant(database)
    ticket_id = _exercise_public_proof_workflow_commands(tenant)
    _assert_immutable_workflow_pin_update_is_denied(tenant, ticket_id)
    _assert_runtime_role_privileges(database.admin_dsn)


def _exercise_public_proof_workflow_commands(tenant: TenantFixture) -> UUID:
    candidate_digest = "sha256:" + "d" * 64
    content = "least-privilege acceptance evidence"
    artifact_digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    with running_api(tenant.database.runtime_dsn) as base_url:
        with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
            ticket_id = _prepare_public_trace(
                commander, tenant, candidate_digest, artifact_digest, content
            )
        with CtowerClient(base_url, credential=tenant.operator_credential) as operator:
            verdict = operator.record_proof_verdict(
                ticket_id,
                VerdictRequest(
                    expected_version=2,
                    verdict_id=uuid4(),
                    criterion_key="artifact-current",
                    candidate_digest=candidate_digest,
                    decision=VerdictDecision.PASS,
                ),
                command_id=uuid4(),
            )
        with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
            _complete_public_trace(commander, ticket_id)

    assert verdict.satisfied is True
    return ticket_id


def _prepare_public_trace(
    commander: CtowerClient,
    tenant: TenantFixture,
    candidate_digest: str,
    artifact_digest: str,
    content: str,
) -> UUID:
    ticket_id = commander.create_ticket(
        TicketCreateRequest(
            initial_custodian_id=tenant.commander_id,
            priority=Priority.P1,
            source=SourceReference(kind="test", ref=f"test:role-privileges:{uuid4()}"),
            title="Proof and Workflow least privilege",
        ),
        command_id=uuid4(),
    ).ticket.ticket_id
    start_and_admit(commander, ticket_id)
    frame = commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=1,
            workflow_ref="ctower.trust-spine-four-stage@1",
            source_stage="capture",
            destination_stage="frame",
        ),
        command_id=uuid4(),
    )
    _freeze_and_record_public_evidence(
        commander, ticket_id, candidate_digest, artifact_digest, content
    )
    verification = commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=2,
            workflow_ref="ctower.trust-spine-four-stage@1",
            source_stage="frame",
            destination_stage="verify",
        ),
        command_id=uuid4(),
    )
    assert (frame.stage, verification.stage) == ("frame", "verify")
    return ticket_id


def _freeze_and_record_public_evidence(
    commander: CtowerClient,
    ticket_id: UUID,
    candidate_digest: str,
    artifact_digest: str,
    content: str,
) -> None:
    frozen = commander.freeze_proof_criteria(
        ticket_id,
        FreezeCriteriaRequest(
            expected_version=0,
            candidate_digest=candidate_digest,
            criteria=(
                ProofCriterion(
                    key="artifact-current",
                    description="The candidate artifact is current.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
        command_id=uuid4(),
    )
    evidence = commander.record_proof_evidence(
        ticket_id,
        EvidenceRequest(
            expected_version=1,
            evidence_id=uuid4(),
            criterion_key="artifact-current",
            candidate_digest=candidate_digest,
            artifact_digest=artifact_digest,
            content=content,
        ),
        command_id=uuid4(),
    )
    assert (frozen.version, evidence.version) == (1, 2)


def _complete_public_trace(commander: CtowerClient, ticket_id: UUID) -> None:
    workflow_ref = "ctower.trust-spine-four-stage@1"
    terminal = commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=3,
            workflow_ref=workflow_ref,
            source_stage="verify",
            destination_stage="close",
        ),
        command_id=uuid4(),
    )
    closed = commander.resolve_close_workflow(
        ticket_id,
        ResolveCloseRequest(expected_version=4, workflow_ref=workflow_ref),
        command_id=uuid4(),
    )
    assert terminal.stage == "close"
    assert closed.lifecycle_facts == ("resolved", "closed")


def _assert_immutable_workflow_pin_update_is_denied(tenant: TenantFixture, ticket_id: UUID) -> None:
    original_revision = _workflow_revision(tenant.database.admin_dsn, ticket_id)
    with psycopg.connect(tenant.database.admin_dsn, autocommit=True) as connection:
        connection.execute("SET ROLE ctower_svc")
        try:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(
                    "UPDATE workflow_runs SET workflow_revision = workflow_revision + 1 "
                    "WHERE ticket_id = %s",
                    (ticket_id,),
                )
        finally:
            connection.execute("RESET ROLE")
    assert _workflow_revision(tenant.database.admin_dsn, ticket_id) == original_revision


def _workflow_revision(dsn: str, ticket_id: UUID) -> int:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT workflow_revision FROM workflow_runs WHERE ticket_id = %s",
            (ticket_id,),
        ).fetchone()
    assert row is not None
    return int(row["workflow_revision"])


def _assert_runtime_role_privileges(dsn: str) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        for table, expected_columns in {**HEAD_UPDATE_COLUMNS, **CP2_HEAD_UPDATE_COLUMNS}.items():
            columns = connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            ).fetchall()
            assert {str(row["column_name"]) for row in columns} == set(expected_columns)
            actual = {
                column: _column_update_privilege(connection, table, column)
                for column in expected_columns
            }
            assert actual == expected_columns
            assert _table_privilege(connection, table, "SELECT") is True
            assert _table_privilege(connection, table, "INSERT") is True
            assert _table_privilege(connection, table, "UPDATE") is False
            assert _table_privilege(connection, table, "DELETE") is False

        for table in APPEND_ONLY_TABLES:
            assert _table_privilege(connection, table, "SELECT") is True
            assert _table_privilege(connection, table, "INSERT") is True
            assert _table_privilege(connection, table, "UPDATE") is False
            assert _table_privilege(connection, table, "DELETE") is False


def _assert_legacy_heads_have_table_wide_update(dsn: str) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        for table, expected_columns in HEAD_UPDATE_COLUMNS.items():
            assert _table_privilege(connection, table, "UPDATE") is True
            legacy_columns = {
                str(row["column_name"])
                for row in connection.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    """,
                    (table,),
                ).fetchall()
            }
            for column in expected_columns.keys() & legacy_columns:
                assert _column_update_privilege(connection, table, column) is True


def _column_update_privilege(
    connection: psycopg.Connection[dict[str, object]], table: str, column: str
) -> bool:
    row = connection.execute(
        "SELECT has_column_privilege('ctower_svc', %s, %s, 'UPDATE')",
        (f"public.{table}", column),
    ).fetchone()
    assert row is not None
    return bool(row["has_column_privilege"])


def _table_privilege(
    connection: psycopg.Connection[dict[str, object]], table: str, privilege: str
) -> bool:
    row = connection.execute(
        "SELECT has_table_privilege('ctower_svc', %s, %s)",
        (f"public.{table}", privilege),
    ).fetchone()
    assert row is not None
    return bool(row["has_table_privilege"])
