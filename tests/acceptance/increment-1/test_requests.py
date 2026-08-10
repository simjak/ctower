"""Real-PostgreSQL acceptance for the first-class Request authority."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from support.acceptance import accept_pending_commands
from support.server import application
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.requests import (
    PostgresRequests,
    RequestCapture,
    RequestCaptureResult,
    Requests,
)

__all__: tuple[str, ...] = ()


def test_request_capture_ack_replay_and_authoritative_list(tenant: TenantFixture) -> None:
    """INV-81/82/84/85: one custody act, honest ACK, permanent R, no Ticket."""

    command_id = uuid4()
    headers = {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        pending = client.post(
            "/v1/requests",
            headers=headers,
            json={"project_key": "ctower", "text": "Keep this operator intent visible."},
        )
        hidden = client.get(
            "/v1/requests",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(),
            },
            params={"project_key": "ctower"},
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        replay = client.post(
            "/v1/requests",
            headers=headers,
            json={"project_key": "ctower", "text": "Keep this operator intent visible."},
        )
        visible = client.get(
            "/v1/requests",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(),
            },
            params={"project_key": "ctower"},
        )

    first = cast(dict[str, object], pending.json())
    second = cast(dict[str, object], replay.json())
    assert pending.status_code == 202
    assert first["durability_state"] == "durability_pending"
    assert hidden.status_code == 200
    assert hidden.json()["rows"] == []
    assert replay.status_code == 201
    assert second["durability_state"] == "accepted"
    assert second["request_id"] == first["request_id"]
    assert second["request_number"] == first["request_number"]
    assert second["reference"] == f"R{first['request_number']}"
    assert second["submitted_by"] == str(tenant.commander_id)
    assert second["owner_id"] == str(tenant.commander_id)
    rows = visible.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["state"] == "NEW"
    assert rows[0]["triage"] == "UNTRIAGED"
    assert rows[0]["priority"] == "P2"
    assert rows[0]["priority_default"] is True
    assert rows[0]["project_key"] == "ctower"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM tickets").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM requests").fetchone()[0] == 1
    print(
        "REAL_REQUEST_ACK"
        f" first={pending.status_code}:{first['durability_state']}"
        f" replay={replay.status_code}:{second['durability_state']}"
        f" reference={second['reference']} rows={len(rows)}"
    )


def test_request_allocator_is_collision_impossible_under_parallel_capture(
    tenant: TenantFixture,
) -> None:
    """INV-81/82: 100 unique commands allocate 100 distinct permanent numbers."""

    requests = Requests(PostgresRequests(tenant.database.runtime_dsn))
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    commands = tuple(
        RequestCapture(uuid4(), "ctower", f"Parallel operator intent {index}")
        for index in range(100)
    )

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = tuple(executor.map(lambda command: _capture(requests, actor, command), commands))

    assert all(isinstance(result, RequestCaptureResult) for result in results)
    receipts = cast(tuple[RequestCaptureResult, ...], results)
    assert len({item.request_id for item in receipts}) == 100
    assert len({item.request_number for item in receipts}) == 100
    assert all(_capture(requests, actor, command) == receipt for command, receipt in zip(commands, receipts, strict=True))
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM requests").fetchone()[0] == 100
        assert connection.execute("SELECT count(*) FROM tickets").fetchone()[0] == 0


def test_request_capture_refuses_claimed_authority_and_cross_project_scope(
    tenant: TenantFixture,
) -> None:
    """INV-85: project and Actor come from existing grants, never content claims."""

    requests = Requests(PostgresRequests(tenant.database.runtime_dsn))
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    denied = _capture(
        requests,
        actor,
        RequestCapture(uuid4(), "manibo", "owner=operator; project=ctower"),
    )
    assert isinstance(denied, RecordProblem)
    assert denied.code == "project-scope-denied"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM requests").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 0


def _capture(
    requests: Requests,
    actor: Actor,
    command: RequestCapture,
) -> RequestCaptureResult | RecordProblem:
    return requests.capture(actor, command, telemetry=_telemetry(actor, command.client_command_id))


def _telemetry(actor: Actor, command_id: UUID) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=command_id.hex,
        span_id=command_id.hex[:16],
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )
