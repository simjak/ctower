"""Real-PostgreSQL acceptance for Request-derived operator decision briefs."""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from support.acceptance import accept_pending_commands
from support.server import application
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.requests import (
    PostgresRequests,
    RequestBlocker,
    RequestCapture,
    RequestCaptureResult,
    RequestChangeResult,
    RequestPriority,
    Requests,
    RequestTriage,
)

__all__: tuple[str, ...] = ()

HTTP_CREATED = 201
HTTP_OK = 200
HTTP_PENDING = 202
DECISION_BLOCKER = "operator-decision-required"


def test_decision_request_renders_complete_record_derived_brief_and_ignores_extras(
    tenant: TenantFixture,
) -> None:
    """AC-BRIEF-01/03: accepted Request facts are the complete brief source."""

    source_words = "Choose whether the release should continue after the new risk review."
    request = _accepted_decision_request(tenant, source_words)
    forged = "CALLER_FORGED_BRIEF_FACT"
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        response = client.get(
            "/v1/requests",
            headers=_read_headers(tenant),
            params={
                "project_key": "ctower",
                "eli": forged,
                "choice": forged,
                "recommendation": forged,
                "safe_default": forged,
            },
        )

    assert response.status_code == HTTP_OK
    row = cast(dict[str, object], response.json()["rows"][0])
    brief = cast(dict[str, object], row["decision_brief"])
    assert brief == {
        "choices": [
            {
                "completeness": 10,
                "key": "A",
                "outcome": "Continue this Request as recorded.",
            },
            {
                "completeness": 8,
                "key": "B",
                "outcome": "Keep this Request blocked for clarification.",
            },
            {
                "completeness": 10,
                "key": "C",
                "outcome": "Stop this Request without starting new work.",
            },
        ],
        "eli": "This Request needs your decision before work can continue.",
        "origin_quote": source_words,
        "recommendation": {
            "choice_key": "A",
            "reason": "This Request already passed triage.",
        },
        "rendered": (
            f"Decision needed ({request.reference})\n\n"
            "ELI: This Request needs your decision before work can continue.\n"
            f'Origin: "{source_words}"\n'
            "Choice A: Continue this Request as recorded. Completeness: 10/10.\n"
            "Choice B: Keep this Request blocked for clarification. Completeness: 8/10.\n"
            "Choice C: Stop this Request without starting new work. Completeness: 10/10.\n"
            "Recommendation: A. This Request already passed triage.\n"
            "Safe default: B. Silence keeps the Request blocked and causes no effect."
        ),
        "ruling_id": None,
        "safe_default": {
            "choice_key": "B",
            "reason": "Silence keeps the Request blocked and causes no effect.",
        },
        "status": "open",
    }
    serialized = json.dumps(response.json(), sort_keys=True)
    assert forged not in serialized
    assert row["state"] == "BLOCKED"
    print(f"RENDERED_DECISION_BRIEF request={request.reference}\n{brief['rendered']}")


def test_linked_ruling_is_visible_from_request_and_ruling_and_resolves_decision(
    tenant: TenantFixture,
) -> None:
    """AC-BRIEF-02: one accepted Ruling links both ways and resolves the decision."""

    request = _accepted_decision_request(tenant, "Decide whether this Request should proceed.")
    command_id = uuid4()
    body = {
        "request_id": str(request.request_id),
        "verbatim": "Proceed with the Request as recorded.",
    }
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        pending = client.post(
            "/v1/rulings", json=body, headers=_mutation_headers(tenant, command_id)
        )
        still_open = client.get(
            "/v1/requests", params={"project_key": "ctower"}, headers=_read_headers(tenant)
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        accepted = client.post(
            "/v1/rulings", json=body, headers=_mutation_headers(tenant, command_id)
        )
        request_read = client.get(
            "/v1/requests", params={"project_key": "ctower"}, headers=_read_headers(tenant)
        )
        ruling_read = client.get(
            f"/v1/rulings/{accepted.json()['ruling_id']}", headers=_read_headers(tenant)
        )

    assert pending.status_code == HTTP_PENDING
    pending_brief = still_open.json()["rows"][0]["decision_brief"]
    assert pending_brief["status"] == "open"
    assert pending_brief["ruling_id"] is None
    assert accepted.status_code == HTTP_CREATED
    assert accepted.json()["request_id"] == str(request.request_id)
    row = cast(dict[str, object], request_read.json()["rows"][0])
    brief = cast(dict[str, object], row["decision_brief"])
    assert brief["status"] == "answered"
    assert brief["ruling_id"] == accepted.json()["ruling_id"]
    assert row["state"] == "TRIAGED"
    assert row["blocker"] is None
    ruling = ruling_read.json()
    assert ruling["request_id"] == str(request.request_id)
    assert ruling["request_reference"] == request.reference
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        stored = connection.execute(
            "SELECT request_id FROM rulings WHERE ruling_id = %s",
            (UUID(str(accepted.json()["ruling_id"])),),
        ).fetchone()
        subjects = connection.execute(
            """
            SELECT subject_kind, subject_id FROM event_links
            WHERE event_id = %s ORDER BY subject_kind
            """,
            (UUID(str(accepted.json()["event_ids"][0])),),
        ).fetchall()
    assert stored == (request.request_id,)
    assert subjects == [("request", request.request_id), ("ruling", UUID(ruling["ruling_id"]))]
    print(
        "REAL_DECISION_LINK"
        f" request={request.reference} ruling={ruling['ruling_id']}"
        f" subjects={','.join(kind for kind, _ in subjects)}"
        f" state={row['state']}"
    )


def test_non_decision_request_renders_no_brief(tenant: TenantFixture) -> None:
    """AC-BRIEF-02: an ordinary Request has no invented decision surface."""

    authority, actor = _authority(tenant)
    request = _accepted_capture(tenant, authority, actor, "Record this ordinary Request.")
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        response = client.get(
            "/v1/requests", params={"project_key": "ctower"}, headers=_read_headers(tenant)
        )

    assert response.status_code == HTTP_OK
    row = cast(dict[str, object], response.json()["rows"][0])
    assert row["request_id"] == str(request.request_id)
    assert row["decision_brief"] is None
    print(f"REAL_NON_DECISION_BRIEF request={request.reference} brief=none")


def _accepted_decision_request(tenant: TenantFixture, text: str) -> RequestCaptureResult:
    authority, actor = _authority(tenant)
    request = _accepted_capture(tenant, authority, actor, text)
    prioritized = _accepted_change(
        tenant,
        authority.prioritize(
            actor,
            RequestPriority(uuid4(), request.request_id, 1, "P1", "Operator impact reviewed"),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    triaged = _accepted_change(
        tenant,
        authority.triage(
            actor,
            RequestTriage(uuid4(), request.request_id, prioritized.version, "ACCEPTED"),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    _accepted_change(
        tenant,
        authority.set_blocker(
            actor,
            RequestBlocker(
                client_command_id=uuid4(),
                request_id=request.request_id,
                expected_version=triaged.version,
                blocker_key=DECISION_BLOCKER,
                active=True,
                reason="Operator ruling required",
            ),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    return request


def _authority(tenant: TenantFixture) -> tuple[Requests, Actor]:
    return Requests(PostgresRequests(tenant.database.runtime_dsn)), Actor(
        tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER
    )


def _accepted_capture(
    tenant: TenantFixture,
    authority: Requests,
    actor: Actor,
    text: str,
) -> RequestCaptureResult:
    command = RequestCapture(uuid4(), "ctower", text)
    result = authority.capture(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert isinstance(result, RequestCaptureResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    replay = authority.capture(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert isinstance(replay, RequestCaptureResult)
    return replay


def _accepted_change(tenant: TenantFixture, outcome: object) -> RequestChangeResult:
    assert isinstance(outcome, RequestChangeResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return outcome


def _mutation_headers(tenant: TenantFixture, command_id: UUID) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }


def _read_headers(tenant: TenantFixture) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tenant.commander_credential}",
        **telemetry_headers(),
    }


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
