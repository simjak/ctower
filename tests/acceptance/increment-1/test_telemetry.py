"""Strict propagation, golden signals, and exporter-failure acceptance."""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_api.telemetry import TelemetryRecorder
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext as InternalTelemetryContext

__all__: tuple[str, ...] = ()

HTTP_CREATED = 201
HTTP_UNAUTHORIZED = 401
TELEMETRY_SIGNAL_COUNT = 3


def test_auth_denial_telemetry_is_complete_server_owned_and_redacted(
    tenant: TenantFixture,
) -> None:
    captures: list[dict[str, object]] = []
    recorder = TelemetryRecorder(captures.append)
    claimed = telemetry_headers()
    claimed_payload = json.loads(claimed["X-Ctower-Telemetry-Context"])
    claimed_payload.update({"tenant_id": "claimed-tenant", "actor_id": "claimed-actor"})
    claimed["X-Ctower-Telemetry-Context"] = json.dumps(claimed_payload)
    rejected_credential = "rejected-credential-material"

    with TestClient(
        create_app(PostgresRecord(tenant.database.runtime_dsn), telemetry=recorder)
    ) as client:
        response = client.post(
            "/v1/tickets",
            content=b"{",
            headers={**claimed, "Authorization": f"Bearer {rejected_credential}"},
        )

    assert response.status_code == HTTP_UNAUTHORIZED
    assert len(captures) == TELEMETRY_SIGNAL_COUNT
    assert {record["signal"] for record in captures} == {"span", "log", "metric"}
    labels = [cast(dict[str, str], record["metric_labels"]) for record in captures]
    assert {label["outcome"] for label in labels} == {"error"}
    assert {label["reason"] for label in labels} == {"unauthorized"}
    encoded = json.dumps(captures, separators=(",", ":"), sort_keys=True)
    assert rejected_credential not in encoded
    assert "claimed-tenant" not in encoded
    assert "claimed-actor" not in encoded


def test_internal_telemetry_value_is_not_a_second_external_json_validator() -> None:
    assert not hasattr(InternalTelemetryContext, "from_json")


def test_context_reaches_outbox_and_golden_signals_are_redacted(
    tenant: TenantFixture,
) -> None:
    command_id = uuid4()
    captures: list[dict[str, object]] = []
    recorder = TelemetryRecorder(captures.append)
    record = PostgresRecord(tenant.database.runtime_dsn, telemetry=recorder)
    context_header = telemetry_headers(command_id)

    with TestClient(create_app(record, telemetry=recorder), client=("127.0.0.1", 51000)) as client:
        response = _create_ticket(
            client,
            tenant,
            command_id=command_id,
            telemetry=context_header,
            title="golden-secret-title",
        )

    assert response.status_code == HTTP_CREATED
    assert response.headers["X-Ctower-Telemetry-Health"] == "healthy"
    payload = response.json()
    event_id = UUID(payload["event_ids"][0])
    ticket_id = UUID(payload["ticket"]["ticket_id"])
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT telemetry FROM outbox WHERE event_id = %s", (event_id,)
        ).fetchone()

    assert row is not None
    outbox_context = cast(dict[str, object], row["telemetry"])
    input_context = json.loads(context_header["X-Ctower-Telemetry-Context"])
    assert outbox_context == {
        **input_context,
        "actor_id": str(tenant.operator_id),
        "command_id": str(command_id),
        "tenant_id": str(tenant.tenant_id),
        "ticket_id": str(ticket_id),
    }
    assert {str(record["name"]) for record in captures} == {
        "access.authenticate",
        "record.create_ticket",
        "work.create_ticket",
    }
    assert {str(record["signal"]) for record in captures} == {"span", "log", "metric"}
    assert {str(record["trace_id"]) for record in captures} == {input_context["trace_id"]}
    assert {str(record["correlation_id"]) for record in captures} == {
        input_context["correlation_id"]
    }
    for record_payload in captures:
        assert record_payload["metric_labels"] == {"outcome": "ok", "reason": "committed"} or (
            record_payload["metric_labels"]
            == {
                "outcome": "ok",
                "reason": "authorized",
            }
        )
    encoded = json.dumps(captures, separators=(",", ":"), sort_keys=True)
    assert tenant.operator_credential not in encoded
    assert "golden-secret-title" not in encoded
    assert "mission-control:telemetry" not in encoded


def test_exporter_failure_preserves_commit_and_reports_degraded_health(
    tenant: TenantFixture,
) -> None:
    command_id = uuid4()

    def unavailable_exporter(record: dict[str, object]) -> None:
        del record
        raise OSError("collector unavailable")

    recorder = TelemetryRecorder(unavailable_exporter)
    record = PostgresRecord(tenant.database.runtime_dsn, telemetry=recorder)
    with TestClient(create_app(record, telemetry=recorder), client=("127.0.0.1", 51000)) as client:
        response = _create_ticket(
            client,
            tenant,
            command_id=command_id,
            telemetry=telemetry_headers(command_id),
            title="Exporter failure cannot roll back",
        )

    assert response.status_code == HTTP_CREATED
    assert response.headers["X-Ctower-Telemetry-Health"] == "degraded"
    ticket_id = UUID(response.json()["ticket"]["ticket_id"])
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        committed = connection.execute(
            """
            SELECT
                EXISTS (SELECT 1 FROM tickets WHERE ticket_id = %s),
                EXISTS (
                    SELECT 1 FROM outbox
                    WHERE event_id = (SELECT event_ids[1] FROM command_results
                        WHERE principal_id = %s AND client_command_id = %s)
                )
            """,
            (ticket_id, tenant.operator_id, command_id),
        ).fetchone()
    assert committed == (True, True)
    assert recorder.health == "degraded"


def _create_ticket(
    client: TestClient,
    tenant: TenantFixture,
    *,
    command_id: UUID,
    telemetry: dict[str, str],
    title: str,
) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(tenant.commander_id),
                "priority": "P1",
                "source": {
                    "kind": "mission-control",
                    "ref": "mission-control:telemetry",
                },
                "title": title,
            },
            headers={
                **telemetry,
                "Authorization": f"Bearer {tenant.operator_credential}",
                "Idempotency-Key": str(command_id),
            },
        ),
    )
