"""Generated-client/PostgreSQL proof for the dormant migration boundary."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from modules.migration._reviewed import ReviewedSource, reviewed_source
from modules.migration.source_tool.fixtures import CUTOVER_ID, REVIEW
from support.project_delivery import materialize_checkpoint_truth, refresh_project_delivery
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_client import CtowerClient, CtowerProblemError
from ctower_client.models import (
    CtowerProjectEpochRefusalRequest,
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRunCreateRequest,
)
from ctower_client.models import (
    TelemetryContext as HttpTelemetryContext,
)
from ctower_kernel.migration import Migration, PostgresMigration
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    canonical_digest,
)
from tools.migration.ctower_project.ctower_project_source.executor import (
    ImportPassReceipt,
    batch_command_id,
    execute_import,
    prove_pass_two,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import ImportPlan
from tools.migration.ctower_project.ctower_project_source.reconcile import reconcile

_HTTP_ACCEPTED = 202
_HTTP_NOT_FOUND = 404
_HTTP_UNAUTHORIZED = 401
_HTTP_UNPROCESSABLE = 422
__all__: tuple[str, ...] = ()


def test_generated_client_completes_real_two_pass_with_pending_http_parity(
    tenant: TenantFixture,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    source = reviewed_source(tmp_path, CUTOVER_ID)
    materialize_checkpoint_truth(tenant, now=now)
    store = PostgresMigration(
        tenant.database.runtime_dsn,
        trusted_reviewer_keys=source.trusted_keys,
    )
    app = _app(tenant, store)
    create = source.create_request(now)
    create_command = uuid4()

    with TestClient(app) as transport:
        _assert_raw_pending_create(transport, tenant, create, create_command)
        operator = _client(transport, tenant.operator_credential)
        created = operator.create_ctower_project_import_run(
            create,
            command_id=create_command,
        )
        assert created.durability_state == "durability_pending"

        exported = operator.bind_ctower_project_export_equality(
            source.export_request(created.run_id),
            command_id=uuid4(),
        )
        assert exported.state == "export_equality_bound"
        target = _create_target(tenant)
        alias_map = source.fixture.alias_map(
            source.equality,
            existing_ticket_id=target,
        )
        plan_request, plan = source.plan_request(
            created.run_id,
            target,
            tenant.commander_id,
            now,
        )
        operator.bind_ctower_project_alias_plan(
            plan_request,
            command_id=uuid4(),
        )

        _assert_http_refusal_boundaries(
            transport,
            tenant,
            source.importer_credential,
            source.observer_credential,
        )
        _assert_fence_and_epoch_http(
            transport,
            tenant,
            source.observer_credential,
            created.run_id,
            plan_request.fence_registry_artifact,
        )

        _execute_and_finalize(
            operator,
            _client(transport, source.importer_credential),
            source,
            alias_map,
            plan,
            tenant,
        )


def _execute_and_finalize(
    operator: CtowerClient,
    importer: CtowerClient,
    source: ReviewedSource,
    alias_map: dict[str, object],
    plan: ImportPlan,
    tenant: TenantFixture,
) -> None:
    first = execute_import(plan, client=importer, apply=True)
    refresh_project_delivery(tenant, now=datetime.now(UTC))
    second = execute_import(plan, client=importer, apply=True)
    assert isinstance(first, ImportPassReceipt)
    assert isinstance(second, ImportPassReceipt)
    prove_pass_two(first, second)
    ready = operator.get_ctower_project_import_run(plan.run_id)
    assert ready.state == "pass_two_noop"
    assert ready.counts.replayed_operations == plan.operation_count
    assert ready.conservation is not None
    refresh_project_delivery(tenant, now=datetime.now(UTC))
    reconciliation = reconcile(
        source.first,
        source.equality,
        alias_map,
        plan,
        first,
        second,
        client=operator,
        review=REVIEW,
        signer=source.fixture.signer,
    )
    result = operator.finalize_ctower_project_import_run(
        CtowerProjectImportFinalizeRequest(
            run_id=ready.run_id,
            cutover_id=ready.cutover_id,
            expected_run_semantic_digest=ready.semantic_digest,
            reconciliation_artifact=canonical_bytes(reconciliation).decode(),
        ),
        command_id=uuid4(),
    )
    assert result.expected_graph == ready.reconciliation_graph
    assert result.actual_graph == ready.reconciliation_graph
    assert result.pass_two_measurement == ready.pass_two_measurement


def _assert_raw_pending_create(
    transport: TestClient,
    tenant: TenantFixture,
    create: CtowerProjectImportRunCreateRequest,
    command_id: UUID,
) -> None:
    raw = transport.post(
        "/v1/migrations/ctower-project/inventory",
        content=create.model_dump_json(),
        headers=_headers(tenant, command_id),
    )
    assert raw.status_code == _HTTP_ACCEPTED
    assert raw.headers["Retry-After"] == "1"


def _assert_http_refusal_boundaries(
    transport: TestClient,
    tenant: TenantFixture,
    importer_credential: str,
    observer_credential: str,
) -> None:
    headers = {"Authorization": "Bearer invalid"}
    for path in (
        "/v1/migrations/ctower-project/import",
        "/v1/migrations/ctower-project/fence-observations",
    ):
        unauthorized = transport.post(path, content=b"{", headers=headers)
        oversized = transport.post(path, content=b"x" * 300_000, headers=headers)
        assert unauthorized.status_code == oversized.status_code == _HTTP_UNAUTHORIZED
        assert unauthorized.json() == oversized.json()
    for credential, path in (
        (importer_credential, "/v1/migrations/ctower-project/import"),
        (observer_credential, "/v1/migrations/ctower-project/fence-observations"),
    ):
        malformed = transport.post(
            path,
            content=b"{",
            headers={"Authorization": f"Bearer {credential}", "Idempotency-Key": str(uuid4())},
        )
        assert malformed.status_code == _HTTP_UNPROCESSABLE
    operator_headers = _headers(tenant, uuid4())
    for path in (
        "/v1/migrations/ctower-project/inventory",
        "/v1/migrations/ctower-project/export",
        "/v1/migrations/ctower-project/plan",
        "/v1/migrations/ctower-project/reconcile",
        "/v1/migrations/ctower-project/corrections",
    ):
        assert (
            transport.post(path, content=b"{}", headers=operator_headers).status_code
            == _HTTP_UNPROCESSABLE
        )
    for path in (
        "/v1/migrations/ctower-project/prepare",
        "/v1/migrations/ctower-project/commit-development-epoch",
    ):
        assert (
            transport.post(path, content=b"{}", headers=operator_headers).status_code
            == _HTTP_UNPROCESSABLE
        )
    assert (
        transport.get(
            "/v1/migrations/ctower-project/import-runs/not-a-uuid",
            headers=operator_headers,
        ).status_code
        == _HTTP_UNPROCESSABLE
    )
    assert (
        transport.get(
            f"/v1/migrations/ctower-project/import-runs/{uuid4()}",
            headers=operator_headers,
        ).status_code
        == _HTTP_NOT_FOUND
    )
    assert (
        transport.post(
            "/v1/migrations/ctower-project/inventory",
            content=b"x" * 8_388_609,
            headers=operator_headers,
        ).status_code
        == _HTTP_UNPROCESSABLE
    )


def _assert_fence_and_epoch_http(
    transport: TestClient,
    tenant: TenantFixture,
    observer_credential: str,
    run_id: UUID,
    registry_artifact: str,
) -> None:
    registry = json.loads(registry_artifact)
    observer = _client(transport, observer_credential)
    receipt = observer.report_ctower_project_fence_observation(
        _observation(run_id, registry),
        command_id=uuid4(),
    )
    assert receipt.durability_state == "durability_pending"
    refusal = CtowerProjectEpochRefusalRequest(
        run_id=run_id,
        cutover_id=UUID(registry["cutover_id"]),
        reconciliation_digest=f"sha256:{'0' * 64}",
        fence_registry_digest=registry["registry_digest"],
    )
    operator = _client(transport, tenant.operator_credential)
    for invoke in (
        operator.prepare_ctower_project_cutover,
        operator.commit_ctower_project_development_epoch,
    ):
        with pytest.raises(CtowerProblemError) as caught:
            invoke(refusal, command_id=uuid4())
        assert caught.value.problem.code == "i1-7c-required"


def _observation(
    run_id: UUID,
    registry: dict[str, object],
) -> CtowerProjectFenceObservationRequest:
    body: dict[str, object] = {
        "schema": "ctower.ctower-project-fence-observation/v2",
        "observation_id": str(uuid4()),
        "run_id": str(run_id),
        "cutover_id": registry["cutover_id"],
        "tenant_key": "ctower",
        "project_key": "ctower",
        "registry_id": registry["registry_id"],
        "registry_revision": registry["revision"],
        "registry_digest": registry["registry_digest"],
        "source_pointer_digest": registry["source_pointer_digest"],
        "sequence": 1,
        "previous_observation_digest": None,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "from_offset": 0,
        "to_offset": 0,
        "file_identity": {
            "device": 1,
            "inode": 1,
            "scoped_rows_digest": registry["operation_registry_digest"],
        },
        "status": "unknown",
        "reason_code": "classifier_unknown",
        "disables_writes": True,
        "may_enable_writes": False,
    }
    body["observation_digest"] = canonical_digest(body)
    return CtowerProjectFenceObservationRequest.model_validate_json(canonical_bytes(body))


def test_generated_client_refuses_partial_finalize(
    tenant: TenantFixture,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    source = reviewed_source(tmp_path, CUTOVER_ID)
    store = PostgresMigration(
        tenant.database.runtime_dsn,
        trusted_reviewer_keys=source.trusted_keys,
    )
    with TestClient(_app(tenant, store)) as transport:
        operator = _client(transport, tenant.operator_credential)
        created = operator.create_ctower_project_import_run(
            source.create_request(now),
            command_id=uuid4(),
        )
        operator.bind_ctower_project_export_equality(
            source.export_request(created.run_id),
            command_id=uuid4(),
        )
        plan_request, plan = source.plan_request(
            created.run_id,
            _create_target(tenant),
            tenant.commander_id,
            now,
        )
        operator.bind_ctower_project_alias_plan(plan_request, command_id=uuid4())
        importer = _client(transport, source.importer_credential)
        importer.apply_ctower_project_import_batch(
            plan.batches[0],
            command_id=_batch_command_id(plan.batches[0]),
        )
        partial = operator.get_ctower_project_import_run(created.run_id)
        with pytest.raises(CtowerProblemError) as caught:
            operator.finalize_ctower_project_import_run(
                CtowerProjectImportFinalizeRequest(
                    run_id=partial.run_id,
                    cutover_id=partial.cutover_id,
                    expected_run_semantic_digest=partial.semantic_digest,
                    reconciliation_artifact="{}",
                ),
                command_id=uuid4(),
            )
        assert caught.value.problem.code == "migration-import-finalization-refused"


def _app(tenant: TenantFixture, store: PostgresMigration) -> FastAPI:
    return create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        projections=Projections(PostgresProjections(tenant.database.projection_dsn)),
        migration=Migration(store),
        migration_importer_resolver=store.resolve_importer,
        migration_importer_credential_resolver=store.resolve_importer_credential,
        fence_observer_resolver=store.resolve_fence_observer,
    )


def _client(transport: TestClient, credential: str) -> CtowerClient:
    client = CtowerClient("http://testserver", credential=credential)
    client.close()
    object.__setattr__(client, "_http", transport)
    return client


def _create_target(tenant: TenantFixture) -> UUID:
    actor = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    result = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P2",
            source=SourceReference("synthetic", "synthetic:http-alias-target"),
            title="Generated-client alias target",
        ),
        telemetry=_telemetry(actor),
    )
    assert not isinstance(result, RecordProblem)
    return result.ticket.ticket_id


def _headers(tenant: TenantFixture, command_id: UUID) -> dict[str, str]:
    telemetry = HttpTelemetryContext(
        schema_id="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(tenant.tenant_id),
        actor_id=str(tenant.operator_id),
        command_id=str(command_id),
    )
    return {
        "Authorization": f"Bearer {tenant.operator_credential}",
        "Content-Type": "application/json",
        "Idempotency-Key": str(command_id),
        "X-Ctower-Telemetry-Context": telemetry.model_dump_json(by_alias=True),
    }


def _batch_command_id(batch: CtowerProjectImportBatchRequest) -> UUID:
    return batch_command_id(batch)


def _telemetry(actor: Actor) -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=command_id,
    )
