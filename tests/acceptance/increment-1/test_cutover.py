"""I1.7A storage, read, and explicit refusal acceptance evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.projections import (
    CheckpointDefinition,
    DeliveryFacts,
    DeliveryState,
    Projections,
    derive_project_delivery_row,
)
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_CONFLICT = 409
HTTP_NOT_FOUND = 404
HTTP_UNAUTHORIZED = 401
HTTP_UNPROCESSABLE_ENTITY = 422
_DIGEST = "sha256:" + ("a" * 64)
_CRITERIA = (
    "authority_decision",
    "contracts",
    "append_only_storage",
    "read_only_projection",
    "development_dogfood",
    "cp3_d",
)


def test_i17a_storage_is_append_only_and_projection_only(
    tenant: TenantFixture,
) -> None:
    cutover_id, definition_id = _seed_authority_rows(tenant)
    health = Projections(PostgresProjections(tenant.database.projection_dsn)).cutover_health(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    )

    assert health.cutover_id == cutover_id
    assert health.authority_mode == "legacy_writable"
    assert health.phase == "prepared"
    assert health.writes_enabled is False
    assert health.projection_completeness == "current"
    assert health.source_watermark == health.projection_watermark == 0

    for table in (
        "ctower_project_cutover_facts",
        "project_delivery_checkpoint_definitions",
        "project_delivery_exit_criteria",
    ):
        assert _has_privilege(tenant, "ctower_svc", table, "INSERT")
        assert _has_privilege(tenant, "ctower_svc", table, "SELECT")
        assert not _has_privilege(tenant, "ctower_svc", table, "UPDATE")
        assert not _has_privilege(tenant, "ctower_svc", table, "DELETE")

    projection = "project_delivery_projection_rows"
    assert _has_privilege(tenant, "ctower_svc", projection, "SELECT")
    assert not _has_privilege(tenant, "ctower_svc", projection, "INSERT")
    assert not _has_privilege(tenant, "ctower_svc", projection, "UPDATE")
    assert not _has_privilege(tenant, "ctower_svc", projection, "DELETE")
    for privilege in ("INSERT", "UPDATE", "DELETE", "SELECT"):
        assert _has_privilege(tenant, "ctower_projection", projection, privilege)

    with psycopg.connect(tenant.database.admin_dsn, autocommit=True) as connection:
        with pytest.raises(psycopg.DatabaseError, match="immutable"):
            connection.execute(
                """
                UPDATE ctower_project_cutover_facts
                SET source_watermark = source_watermark + 1
                WHERE tenant_id = %s AND cutover_id = %s
                """,
                (tenant.tenant_id, cutover_id),
            )
        with pytest.raises(psycopg.DatabaseError, match="immutable"):
            connection.execute(
                """
                DELETE FROM project_delivery_exit_criteria
                WHERE tenant_id = %s AND checkpoint_definition_id = %s
                """,
                (tenant.tenant_id, definition_id),
            )
        with pytest.raises(psycopg.DatabaseError, match="immutable"):
            connection.execute(
                """
                UPDATE project_delivery_checkpoint_definitions
                SET checkpoint_label = 'rewritten'
                WHERE tenant_id = %s AND checkpoint_definition_id = %s
                """,
                (tenant.tenant_id, definition_id),
            )


def test_i17a_api_reads_blocked_cp3_d_and_stubs_mutate_nothing(
    tenant: TenantFixture,
) -> None:
    _seed_project_delivery_row(tenant)
    before = _cutover_fact_count(tenant)
    command_id = uuid4()

    with TestClient(_app(tenant)) as client:
        health = client.get(
            "/v1/migrations/ctower-project/cutover-health",
            headers=_headers(tenant),
        )
        delivery = client.get(
            "/v1/projects/ctower/delivery",
            headers=_headers(tenant),
        )
        _assert_i17a_refusals(client, tenant, command_id)

    assert health.status_code == HTTP_OK
    assert health.json()["authority_mode"] == "legacy_writable"
    assert health.json()["writes_enabled"] is False
    assert health.json()["durability_claim"] == "CP3_D_NOT_PROVEN"
    assert delivery.status_code == HTTP_OK
    row = delivery.json()["rows"][0]
    assert row["checkpoint_key"] == "I1.7"
    assert row["headline_state"] == "blocked"
    assert row["underlying_maturity"] == "verified"
    assert row["criteria"] == {"declared": 6, "proven": 5}
    assert row["confidence"] == "development_degraded"
    assert row["health"] == "CP3_D_NOT_PROVEN"
    assert _cutover_fact_count(tenant) == before == 0


def _assert_i17a_refusals(
    client: TestClient,
    tenant: TenantFixture,
    command_id: UUID,
) -> None:
    refused = [
        client.post(
            f"/v1/migrations/ctower-project/{phase}",
            json={"cutover_id": str(uuid4()), "input_digest": _DIGEST},
            headers=_headers(tenant, command_id=command_id),
        )
        for phase in (
            "inventory",
            "export",
            "plan",
            "import",
            "reconcile",
            "prepare",
            "commit-development-epoch",
        )
    ]
    invalid_stub = client.post(
        "/v1/migrations/ctower-project/inventory",
        json={"cutover_id": str(uuid4())},
        headers=_headers(tenant, command_id=command_id),
    )
    unauthenticated = client.post(
        "/v1/migrations/ctower-project/import",
        content=b"not-json",
        headers={
            "Idempotency-Key": str(uuid4()),
            **telemetry_headers(),
        },
    )
    invalid_project = client.get("/v1/projects/x!/delivery", headers=_headers(tenant))
    missing_project = client.get("/v1/projects/other/delivery", headers=_headers(tenant))
    unauthenticated_health = client.get(
        "/v1/migrations/ctower-project/cutover-health",
        headers=telemetry_headers(),
    )
    unauthenticated_delivery = client.get(
        "/v1/projects/ctower/delivery",
        headers=telemetry_headers(),
    )

    assert {(response.status_code, response.json()["code"]) for response in refused} == {
        (HTTP_CONFLICT, "i1-7b-required")
    }
    assert invalid_stub.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert unauthenticated.status_code == HTTP_UNAUTHORIZED
    assert invalid_project.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert missing_project.status_code == HTTP_NOT_FOUND
    assert unauthenticated_health.status_code == HTTP_UNAUTHORIZED
    assert unauthenticated_delivery.status_code == HTTP_UNAUTHORIZED


def _seed_authority_rows(tenant: TenantFixture) -> tuple[UUID, UUID]:
    cutover_id = uuid4()
    definition_id = uuid4()
    event_id, recorded_at = _bootstrap_event(tenant)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO ctower_project_cutover_facts (
                cutover_fact_id, tenant_id, cutover_id, fact_sequence, phase,
                authority_mode, writes_enabled, durability_claim, recovery_claim,
                data_class, legacy_writer_fence, split_brain, source_watermark,
                event_id, actor_principal_id, client_command_id, recorded_at
            ) VALUES (
                %s, %s, %s, 1, 'prepared', 'legacy_writable', false,
                'CP3_D_NOT_PROVEN', 'EXTERNAL_FAILURE_DOMAIN_UNPROVEN',
                'RECONSTRUCTIBLE_ONLY', 'not_armed', 'clear', 0,
                %s, %s, %s, %s
            )
            """,
            (
                uuid4(),
                tenant.tenant_id,
                cutover_id,
                event_id,
                tenant.operator_id,
                uuid4(),
                recorded_at,
            ),
        )
        _insert_definition(
            connection,
            tenant,
            definition_id,
            event_id,
            recorded_at,
        )
        connection.execute(
            """
            INSERT INTO project_delivery_exit_criteria (
                checkpoint_definition_id, tenant_id, criterion_key, ordinal,
                description, proof_ticket_id, proof_criterion_key, source_ids
            ) VALUES (%s, %s, 'cp3_d', 1, %s, NULL, NULL, %s)
            """,
            (
                definition_id,
                tenant.tenant_id,
                "External failure-domain durability is independently proven.",
                ["ctower:CP3-D"],
            ),
        )
    return cutover_id, definition_id


def _seed_project_delivery_row(tenant: TenantFixture) -> None:
    definition_id = uuid4()
    event_id, recorded_at = _bootstrap_event(tenant)
    definition = _definition()
    row = derive_project_delivery_row(
        definition,
        DeliveryFacts(
            maturity=DeliveryState.VERIFIED,
            proven_criteria=frozenset(_CRITERIA[:-1]),
            effective_blockers=("cp3_d",),
            source_ids=("ctower:CT-I1-007", "mission-control:i1.7"),
            source_watermark=27,
            projection_watermark=27,
            last_reconciled_at=datetime(2026, 7, 25, 10, tzinfo=UTC),
            observed_at=datetime(2026, 7, 25, 10, 30, tzinfo=UTC),
            source_complete=True,
            cp3_d_proven=False,
        ),
    )
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        _insert_definition(
            connection,
            tenant,
            definition_id,
            event_id,
            recorded_at,
        )
        connection.execute(
            """
            INSERT INTO project_delivery_projection_rows (
                tenant_id, project_key, checkpoint_key, row_payload,
                source_watermark, projection_watermark, reconciled_at
            ) VALUES (%s, 'ctower', 'I1.7', %s, 27, 27, %s)
            """,
            (tenant.tenant_id, Jsonb(row.response_payload()), recorded_at),
        )


def _insert_definition(
    connection: psycopg.Connection[tuple[object, ...]],
    tenant: TenantFixture,
    definition_id: UUID,
    event_id: UUID,
    recorded_at: datetime,
) -> None:
    definition = _definition()
    connection.execute(
        """
        INSERT INTO project_delivery_checkpoint_definitions (
            checkpoint_definition_id, tenant_id, company_key, project_key,
            checkpoint_key, definition_revision, ordered_position,
            checkpoint_label, outcome, accountable_owner, applicable_states,
            catalog_revision, catalog_digest, event_id, actor_principal_id,
            recorded_at
        ) VALUES (
            %s, %s, 'ctower', 'ctower', 'I1.7', 1, 7,
            %s, %s, %s, %s, 'ctower.project-delivery@1',
            %s, %s, %s, %s
        )
        """,
        (
            definition_id,
            tenant.tenant_id,
            definition.label,
            definition.outcome,
            definition.accountable_owner,
            sorted(state.value for state in definition.applicable_states),
            bytes.fromhex("a" * 64),
            event_id,
            tenant.operator_id,
            recorded_at,
        ),
    )


def _definition() -> CheckpointDefinition:
    return CheckpointDefinition(
        key="I1.7",
        label="Development dogfood cutover",
        outcome="ctower owns reviewed reconstructible engineering work",
        accountable_owner="operator",
        criteria=_CRITERIA,
        applicable_states=frozenset(DeliveryState),
    )


def _bootstrap_event(tenant: TenantFixture) -> tuple[UUID, datetime]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT event_id, server_time
            FROM events
            WHERE tenant_id = %s AND kind = 'bootstrap.first_tenant_created'
            ORDER BY sequence
            LIMIT 1
            """,
            (tenant.tenant_id,),
        ).fetchone()
    assert row is not None
    return cast(UUID, row["event_id"]), cast(datetime, row["server_time"])


def _has_privilege(
    tenant: TenantFixture,
    role: str,
    table: str,
    privilege: str,
) -> bool:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT has_table_privilege(%s, %s, %s) AS value",
            (role, table, privilege),
        ).fetchone()
    assert row is not None
    return bool(row["value"])


def _cutover_fact_count(tenant: TenantFixture) -> int:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT count(*) AS value
            FROM ctower_project_cutover_facts
            WHERE tenant_id = %s
            """,
            (tenant.tenant_id,),
        ).fetchone()
    assert row is not None
    return int(cast(int, row["value"]))


def _headers(
    tenant: TenantFixture,
    *,
    command_id: UUID | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {tenant.operator_credential}",
        **telemetry_headers(command_id),
    }
    if command_id is not None:
        headers["Idempotency-Key"] = str(command_id)
    return headers


def _app(tenant: TenantFixture) -> FastAPI:
    return create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        projections=Projections(PostgresProjections(tenant.database.projection_dsn)),
    )
