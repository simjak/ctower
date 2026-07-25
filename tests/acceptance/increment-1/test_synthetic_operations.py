"""PostgreSQL acceptance for fixed synthetic attempt and result receipts."""

from __future__ import annotations

from datetime import time
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from support.acceptance import accept_command
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.record import RecordProblem
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    FixedOperationCompletion,
    FixedOperations,
    RoutineRevision,
    ScheduleKind,
    SyntheticRunCommand,
    SyntheticRunState,
)
from ctower_kernel.runtime.postgres import PostgresRuntime

_HTTP_CREATED = 201
_HTTP_ACCEPTED = 202
_HTTP_UNAUTHORIZED = 401


def test_synthetic_run_api_records_only_an_accepted_fixed_job(
    tenant: TenantFixture,
) -> None:
    runtime = PostgresRuntime(tenant.database.runtime_dsn)
    command_id = uuid4()
    app = create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        synthetic_runtime=runtime,
        synthetic_revision=_revision(),
    )
    headers = {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }
    with TestClient(app) as client:
        pending = client.post(
            "/v1/control/synthetic-runs",
            headers=headers,
            json={"workflow_ref": "ctower.trust-spine-four-stage@1"},
        )
        unauthorized = client.get(
            "/v1/control/synthetic-runs/not-a-uuid",
            headers={"Authorization": "Bearer invalid"},
        )
        assert pending.status_code == _HTTP_ACCEPTED
        run_id = pending.json()["run_id"]
        assert (
            client.get(
                f"/v1/control/synthetic-runs/{run_id}",
                headers=headers,
            ).json()["state"]
            == "pending"
        )
        assert unauthorized.status_code == _HTTP_UNAUTHORIZED
        accept_command(
            tenant.database.admin_dsn,
            tenant.tenant_id,
            tenant.commander_id,
            command_id,
        )
        accepted = client.post(
            "/v1/control/synthetic-runs",
            headers=headers,
            json={"workflow_ref": "ctower.trust-spine-four-stage@1"},
        )

    assert accepted.status_code == _HTTP_CREATED
    assert accepted.json()["run_id"] == run_id


def test_fixed_synthetic_attempt_fence_and_terminal_result_are_immutable(
    tenant: TenantFixture,
) -> None:
    fixed = FixedOperations(PostgresRuntime(tenant.database.runtime_dsn))
    command_id = uuid4()
    receipt = fixed.start_synthetic(
        tenant.tenant_id,
        tenant.commander_id,
        SyntheticRunCommand(command_id, "ctower.trust-spine-four-stage@1"),
        _revision(),
    )
    assert not isinstance(receipt, RecordProblem)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        command_id,
    )

    attempt = fixed.claim_synthetic("ctower.test.synthetic")
    assert attempt is not None
    completion = FixedOperationCompletion(
        succeeded=False,
        ticket_id=None,
        lifecycle_facts=(),
        detail_code="synthetic-test-refusal",
    )
    result = fixed.complete_synthetic(attempt, completion)
    replay = fixed.complete_synthetic(attempt, completion)
    run = fixed.synthetic_run(tenant.tenant_id, receipt.run_id)

    assert replay == result
    assert run is not None
    assert run.state is SyntheticRunState.FAILED
    assert run.attempt_count == 1
    assert fixed.claim_synthetic("ctower.test.synthetic") is None
    _assert_immutable(tenant)


def _revision() -> RoutineRevision:
    return RoutineRevision(
        routine_ref="ctower.test.synthetic-receipt@1",
        revision_digest="sha256:" + "c" * 64,
        schedule_kind=ScheduleKind.DAILY,
        timezone="UTC",
        local_time=time(1),
        concurrency=ConcurrencyPolicy.COALESCE_IF_ACTIVE,
        catch_up=CatchUpPolicy.SKIP_MISSED,
        catch_up_cap=1,
        handler_kind="synthetic_four_stage",
        timeout_seconds=60,
        component_digests=("sha256:" + "d" * 64,),
    )


def _assert_immutable(tenant: TenantFixture) -> None:
    statements = (
        "DELETE FROM fixed_operation_attempts",
        "DELETE FROM fixed_operation_results",
    )
    for statement in statements:
        with (
            psycopg.connect(tenant.database.admin_dsn) as connection,
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
        ):
            connection.execute(statement)
