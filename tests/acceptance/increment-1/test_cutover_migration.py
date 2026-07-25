"""Real restricted-import HTTP acceptance without epoch mutation."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportRunCreateRequest,
    MigrationFenceFileIdentity,
)
from ctower_kernel.migration import Migration, PostgresMigration
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
_DIGEST = "sha256:" + ("a" * 64)


def test_real_migration_routes_replay_and_refuse_cross_scope_without_epoch(
    tenant: TenantFixture,
) -> None:
    before = _cutover_fact_count(tenant)
    importer_credential = "synthetic-http-importer"
    create_request = _run_request(importer_credential)

    with TestClient(_app(tenant)) as client:
        created, replayed = _create_run(client, tenant, create_request)
        run_id = UUID(created.json()["run_id"])
        exported, planned = _bind_run(client, tenant, run_id, create_request)
        imported, cross_scope = _import_batch(
            client,
            tenant,
            run_id,
            create_request.cutover_id,
            importer_credential,
        )
        run = client.get(
            f"/v1/migrations/ctower-project/import-runs/{run_id}",
            headers=_operator_headers(tenant),
        )
        fenced = _observe_fence(client, tenant)
        health = client.get(
            "/v1/migrations/ctower-project/cutover-health",
            headers=_operator_headers(tenant),
        )

    assert created.status_code == replayed.status_code == HTTP_OK
    assert created.json() == replayed.json()
    assert all(
        response.status_code == HTTP_OK
        for response in (exported, planned, imported, run, fenced, health)
    )
    assert cross_scope.status_code == HTTP_UNAUTHORIZED
    assert health.json()["import_run_id"] == str(run_id)
    assert health.json()["migration_digests"]["source_selection"] == _DIGEST
    assert health.json()["split_brain"] == "unknown"
    assert health.json()["writes_enabled"] is False
    assert _cutover_fact_count(tenant) == before == 0


def _create_run(
    client: TestClient,
    tenant: TenantFixture,
    request: CtowerProjectImportRunCreateRequest,
) -> tuple[Response, Response]:
    command_id = uuid4()
    created = client.post(
        "/v1/migrations/ctower-project/inventory",
        content=request.model_dump_json(),
        headers=_operator_headers(tenant, command_id),
    )
    replayed = client.post(
        "/v1/migrations/ctower-project/inventory",
        content=request.model_dump_json(),
        headers=_operator_headers(tenant, command_id),
    )
    return created, replayed


def _bind_run(
    client: TestClient,
    tenant: TenantFixture,
    run_id: UUID,
    create: CtowerProjectImportRunCreateRequest,
) -> tuple[Response, Response]:
    export = CtowerProjectExportEqualityBindRequest(
        run_id=run_id,
        cutover_id=create.cutover_id,
        selection_digest=create.source_selection_digest,
        inventory_a_digest=_DIGEST,
        inventory_b_digest=_DIGEST,
        export_digest=_DIGEST,
        equality_report_digest=_DIGEST,
        reviewer_public_key_digest=create.reviewer_public_key_digest,
        result="equal",
    )
    exported = client.post(
        "/v1/migrations/ctower-project/export",
        content=export.model_dump_json(),
        headers=_operator_headers(tenant, uuid4()),
    )
    plan = CtowerProjectAliasPlanBindRequest(
        run_id=run_id,
        cutover_id=create.cutover_id,
        export_equality_digest=export.equality_report_digest,
        alias_map_digest=_DIGEST,
        reviewer_public_key_digest=create.reviewer_public_key_digest,
        attention_required=0,
    )
    planned = client.post(
        "/v1/migrations/ctower-project/plan",
        content=plan.model_dump_json(),
        headers=_operator_headers(tenant, uuid4()),
    )
    return exported, planned


def _import_batch(
    client: TestClient,
    tenant: TenantFixture,
    run_id: UUID,
    cutover_id: UUID,
    credential: str,
) -> tuple[Response, Response]:
    batch = _seed_batch(run_id, cutover_id, tenant.commander_id)
    imported = client.post(
        "/v1/migrations/ctower-project/import",
        content=batch.model_dump_json(by_alias=True),
        headers=_migration_headers(credential),
    )
    wrong_scope = batch.model_copy(update={"cutover_id": uuid4()})
    cross_scope = client.post(
        "/v1/migrations/ctower-project/import",
        content=wrong_scope.model_dump_json(by_alias=True),
        headers=_migration_headers(credential),
    )
    return imported, cross_scope


def _observe_fence(client: TestClient, tenant: TenantFixture) -> Response:
    credential = "synthetic-fence-observer"
    _add_fence_observer(tenant, credential)
    request = CtowerProjectFenceObservationRequest(
        schema_id="ctower.ctower-project-fence-observation/v1",
        observation_id=uuid4(),
        registry_id=uuid4(),
        registry_revision=1,
        registry_digest=_DIGEST,
        sequence=1,
        previous_observation_digest=None,
        observed_at=datetime.now(UTC),
        from_offset=0,
        to_offset=0,
        file_identity=MigrationFenceFileIdentity(
            device=1,
            inode=1,
            scoped_rows_digest=_DIGEST,
        ),
        status="unknown",
        reason_code="classifier_unknown",
        observation_digest=_DIGEST,
        disables_writes=True,
        may_enable_writes=False,
    )
    return cast(
        Response,
        client.post(
            "/v1/migrations/ctower-project/fence-observations",
            content=request.model_dump_json(by_alias=True),
            headers=_migration_headers(credential),
        ),
    )


def _run_request(credential: str) -> CtowerProjectImportRunCreateRequest:
    return CtowerProjectImportRunCreateRequest(
        cutover_id=uuid4(),
        tenant_key="ctower",
        project_key="ctower",
        source_selection_digest=_DIGEST,
        build_digest=_DIGEST,
        client_digest=_DIGEST,
        schema_digest=_DIGEST,
        operation_registry_digest=_DIGEST,
        reviewer_public_key_digest=_DIGEST,
        importer_credential_digest=(f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}"),
        importer_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _seed_batch(
    run_id: UUID,
    cutover_id: UUID,
    commander_id: UUID,
) -> CtowerProjectImportBatchRequest:
    return CtowerProjectImportBatchRequest.model_validate(
        {
            "schema": "ctower.ctower-project-import-batch/v1",
            "run_id": run_id,
            "cutover_id": cutover_id,
            "batch_index": 0,
            "batch_digest": _DIGEST,
            "operations": (
                {
                    "operation": "ticket_seed",
                    "identity": {
                        "namespace": "mission-control:request",
                        "immutable_source_id": "R325",
                        "source_version_or_digest": "line:1",
                        "operation_kind": "ticket_seed",
                        "planned_target_ref": "new_ticket",
                        "command_id": uuid4(),
                    },
                    "project_key": "ctower",
                    "priority": "P2",
                    "title": "Synthetic R325",
                    "source": {
                        "namespace": "mission-control:request",
                        "immutable_source_id": "R325",
                        "source_version": "line:1",
                        "source_digest": _DIGEST,
                    },
                    "initial_commander_custodian_id": commander_id,
                },
            ),
        }
    )


def _add_fence_observer(tenant: TenantFixture, credential: str) -> None:
    observer_id = uuid4()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, 'fence_observer', 'Synthetic Fence Observer', false, %s)
            """,
            (observer_id, tenant.tenant_id, datetime.now(UTC)),
        )
        connection.execute(
            """
            INSERT INTO principal_credentials (
                credential_id, principal_id, tenant_id, credential_digest, created_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                observer_id,
                tenant.tenant_id,
                hashlib.sha256(credential.encode()).digest(),
                datetime.now(UTC),
            ),
        )


def _operator_headers(
    tenant: TenantFixture,
    command_id: UUID | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {tenant.operator_credential}",
        **telemetry_headers(command_id),
    }
    if command_id is not None:
        headers["Idempotency-Key"] = str(command_id)
    return headers


def _migration_headers(credential: str) -> dict[str, str]:
    command_id = uuid4()
    return {
        "Authorization": f"Bearer {credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }


def _cutover_fact_count(tenant: TenantFixture) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT count(*) FROM ctower_project_cutover_facts WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _app(tenant: TenantFixture) -> FastAPI:
    store = PostgresMigration(tenant.database.runtime_dsn)
    return create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        projections=Projections(PostgresProjections(tenant.database.projection_dsn)),
        migration=Migration(store),
        migration_importer_resolver=store.resolve_importer,
        fence_observer_resolver=store.resolve_fence_observer,
    )
