"""Real-PostgreSQL acceptance for Request-derived operator decision briefs."""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
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
HTTP_CONFLICT = 409
HTTP_NOT_FOUND = 404
HTTP_OK = 200
HTTP_PENDING = 202
HTTP_UNPROCESSABLE = 422
DECISION_BLOCKER = "operator-decision-required"
RENDERED_MAX = 400000


def test_decision_request_renders_complete_record_derived_brief_and_ignores_extras(
    tenant: TenantFixture,
) -> None:
    """AC-BRIEF-01/03: accepted Request facts are the complete brief source."""

    source_words = "Choose whether the release should continue after the new risk review."
    request, _ = _accepted_decision_request(tenant, source_words)
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

    request, _ = _accepted_decision_request(tenant, "Decide whether this Request should proceed.")
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
        successor = _accepted_ruling(
            client,
            tenant,
            verbatim="The corrected answer still proceeds with the Request.",
            supersedes_ruling_id=UUID(str(accepted.json()["ruling_id"])),
        )
        successor_request_read = client.get(
            "/v1/requests", params={"project_key": "ctower"}, headers=_read_headers(tenant)
        )
        successor_read = client.get(
            f"/v1/rulings/{successor['ruling_id']}", headers=_read_headers(tenant)
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
    successor_brief = successor_request_read.json()["rows"][0]["decision_brief"]
    assert successor_brief["ruling_id"] == successor["ruling_id"]
    assert successor_read.json()["request_id"] == str(request.request_id)
    assert successor_read.json()["request_reference"] == request.reference
    stored, subjects = _stored_link_evidence(tenant, accepted.json())
    assert stored == (request.request_id,)
    assert subjects == [("request", request.request_id), ("ruling", UUID(ruling["ruling_id"]))]
    print(
        "REAL_DECISION_LINK"
        f" request={request.reference} ruling={ruling['ruling_id']}"
        f" successor={successor['ruling_id']}"
        f" subjects={','.join(kind for kind, _ in subjects)}"
        f" state={row['state']}"
    )


def test_decision_occurrences_reopen_and_only_the_answered_occurrence_is_resolved(
    tenant: TenantFixture,
) -> None:
    """AC-BRIEF-01/02: each latest active marker is one answerable occurrence."""

    request, version = _accepted_decision_request(
        tenant, "Decide whether repeated release review may continue."
    )
    authority, actor = _authority(tenant)
    unrelated = _accepted_blocker(
        tenant,
        authority,
        actor,
        request.request_id,
        version,
        "deployment-window",
        active=True,
        reason="The deployment window remains closed",
    )
    first, first_row, duplicate = _first_occurrence_answer(tenant, request)
    _assert_first_occurrence(first, first_row, duplicate)

    reopened = _accepted_blocker(
        tenant,
        authority,
        actor,
        request.request_id,
        unrelated.version,
        DECISION_BLOCKER,
        active=True,
        reason="A later review requires a new operator answer",
    )
    guard_sqlstate = _assert_successor_occurrence_guard(
        tenant,
        request.request_id,
        UUID(str(first["ruling_id"])),
    )
    open_row, second, answered_row = _second_occurrence_answer(tenant, request)
    _assert_second_occurrence(open_row, second, answered_row)

    _accepted_blocker(
        tenant,
        authority,
        actor,
        request.request_id,
        reopened.version,
        DECISION_BLOCKER,
        active=False,
        reason="The later decision need was withdrawn",
    )
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        inactive_read = client.get(
            "/v1/requests", params={"project_key": "ctower"}, headers=_read_headers(tenant)
        )
    assert inactive_read.json()["rows"][0]["decision_brief"] is None
    print(
        "REAL_DECISION_OCCURRENCES"
        f" request={request.reference} first={first['ruling_id']} second={second['ruling_id']}"
        f" reopened=open unrelated=deployment-window inactive=none guard={guard_sqlstate}"
    )


def test_ruling_request_link_refusals_are_exact(tenant: TenantFixture) -> None:
    """AC-BRIEF-02: invalid Request relations refuse by exact stable code."""

    authority, actor = _authority(tenant)
    ordinary = _accepted_capture(tenant, authority, actor, "An ordinary Request.")
    decision, _ = _accepted_decision_request(tenant, "A decision Request for relation tests.")
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        missing = client.post(
            "/v1/rulings",
            json={"request_id": str(uuid4()), "verbatim": "Cannot link an absent Request."},
            headers=_mutation_headers(tenant, uuid4()),
        )
        ordinary_refusal = client.post(
            "/v1/rulings",
            json={
                "request_id": str(ordinary.request_id),
                "verbatim": "Cannot answer an ordinary Request.",
            },
            headers=_mutation_headers(tenant, uuid4()),
        )
        root = _accepted_ruling(
            client,
            tenant,
            request_id=decision.request_id,
            verbatim="The valid answer used as predecessor.",
        )
        ambiguous = client.post(
            "/v1/rulings",
            json={
                "request_id": str(decision.request_id),
                "supersedes_ruling_id": root["ruling_id"],
                "verbatim": "A relation cannot name both directions.",
            },
            headers=_mutation_headers(tenant, uuid4()),
        )

    assert missing.status_code == HTTP_NOT_FOUND
    assert missing.json()["code"] == "ruling-request-not-found"
    assert ordinary_refusal.status_code == HTTP_CONFLICT
    assert ordinary_refusal.json()["code"] == "ruling-request-not-decision"
    assert ambiguous.status_code == HTTP_UNPROCESSABLE
    assert ambiguous.json()["code"] == "invalid-ruling"


def test_maximum_legal_request_content_stays_inside_rendered_contract(
    tenant: TenantFixture,
) -> None:
    """AC-BRIEF-01: worst-case JSON escaping still validates the HTTP response."""

    request, _ = _accepted_decision_request(tenant, "\x01" * 65536)
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        response = client.get(
            "/v1/requests", params={"project_key": "ctower"}, headers=_read_headers(tenant)
        )

    assert response.status_code == HTTP_OK
    rendered = response.json()["rows"][0]["decision_brief"]["rendered"]
    assert len(rendered) <= RENDERED_MAX
    assert response.json()["rows"][0]["reference"] == request.reference


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


def _accepted_decision_request(
    tenant: TenantFixture, text: str
) -> tuple[RequestCaptureResult, int]:
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
    blocked = _accepted_change(
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
    return request, blocked.version


def _accepted_ruling(
    client: TestClient,
    tenant: TenantFixture,
    *,
    verbatim: str,
    request_id: UUID | None = None,
    supersedes_ruling_id: UUID | None = None,
) -> dict[str, object]:
    command_id = uuid4()
    body: dict[str, object] = {"verbatim": verbatim}
    if request_id is not None:
        body["request_id"] = str(request_id)
    if supersedes_ruling_id is not None:
        body["supersedes_ruling_id"] = str(supersedes_ruling_id)
    pending = client.post("/v1/rulings", json=body, headers=_mutation_headers(tenant, command_id))
    assert pending.status_code == HTTP_PENDING
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    accepted = client.post("/v1/rulings", json=body, headers=_mutation_headers(tenant, command_id))
    assert accepted.status_code == HTTP_CREATED
    return cast(dict[str, object], accepted.json())


def _accepted_blocker(
    tenant: TenantFixture,
    authority: Requests,
    actor: Actor,
    request_id: UUID,
    version: int,
    blocker_key: str,
    *,
    active: bool,
    reason: str,
) -> RequestChangeResult:
    command_id = uuid4()
    return _accepted_change(
        tenant,
        authority.set_blocker(
            actor,
            RequestBlocker(
                command_id,
                request_id,
                version,
                blocker_key,
                active=active,
                reason=reason,
            ),
            telemetry=_telemetry(actor, command_id),
        ),
    )


def _first_occurrence_answer(
    tenant: TenantFixture,
    request: RequestCaptureResult,
) -> tuple[dict[str, object], dict[str, object], Response]:
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        first = _accepted_ruling(
            client,
            tenant,
            request_id=request.request_id,
            verbatim="Proceed after the first review.",
        )
        first_read = client.get(
            "/v1/requests", params={"project_key": "ctower"}, headers=_read_headers(tenant)
        )
        duplicate = client.post(
            "/v1/rulings",
            json={
                "request_id": str(request.request_id),
                "verbatim": "A second root cannot answer the same decision occurrence.",
            },
            headers=_mutation_headers(tenant, uuid4()),
        )
    return first, cast(dict[str, object], first_read.json()["rows"][0]), duplicate


def _assert_first_occurrence(
    first: dict[str, object],
    row: dict[str, object],
    duplicate: Response,
) -> None:
    brief = cast(dict[str, object], row["decision_brief"])
    assert brief["ruling_id"] == first["ruling_id"]
    assert row["blocker"] == "deployment-window"
    assert row["state"] == "BLOCKED"
    assert duplicate.status_code == HTTP_CONFLICT
    assert duplicate.json()["code"] == "ruling-request-already-answered"


def _second_occurrence_answer(
    tenant: TenantFixture,
    request: RequestCaptureResult,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        open_read = client.get(
            "/v1/requests", params={"project_key": "ctower"}, headers=_read_headers(tenant)
        )
        second = _accepted_ruling(
            client,
            tenant,
            request_id=request.request_id,
            verbatim="Proceed after the later review too.",
        )
        answered_read = client.get(
            "/v1/requests", params={"project_key": "ctower"}, headers=_read_headers(tenant)
        )
    return (
        cast(dict[str, object], open_read.json()["rows"][0]),
        second,
        cast(dict[str, object], answered_read.json()["rows"][0]),
    )


def _assert_second_occurrence(
    open_row: dict[str, object],
    second: dict[str, object],
    answered_row: dict[str, object],
) -> None:
    open_brief = cast(dict[str, object], open_row["decision_brief"])
    answered_brief = cast(dict[str, object], answered_row["decision_brief"])
    assert open_brief["status"] == "open"
    assert open_brief["ruling_id"] is None
    assert open_row["blocker"] == "deployment-window"
    assert open_row["state"] == "BLOCKED"
    assert answered_brief["ruling_id"] == second["ruling_id"]
    assert answered_row["blocker"] == "deployment-window"
    assert answered_row["state"] == "BLOCKED"


def _stored_link_evidence(
    tenant: TenantFixture,
    result: dict[str, object],
) -> tuple[tuple[UUID] | None, list[tuple[str, UUID]]]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        stored = connection.execute(
            "SELECT request_id FROM rulings WHERE ruling_id = %s",
            (UUID(str(result["ruling_id"])),),
        ).fetchone()
        subjects = connection.execute(
            """
            SELECT subject_kind, subject_id FROM event_links
            WHERE event_id = %s ORDER BY subject_kind
            """,
            (UUID(str(cast(list[str], result["event_ids"])[0])),),
        ).fetchall()
    return cast(tuple[UUID] | None, stored), cast(list[tuple[str, UUID]], subjects)


def _assert_successor_occurrence_guard(
    tenant: TenantFixture,
    request_id: UUID,
    predecessor_id: UUID,
) -> str:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        decision_fact_id = cast(
            tuple[UUID],
            connection.execute(
                """
                SELECT blocker_fact_id FROM request_blocker_facts
                WHERE tenant_id = %s AND request_id = %s
                  AND blocker_key = 'operator-decision-required'
                ORDER BY request_version DESC LIMIT 1
                """,
                (tenant.tenant_id, request_id),
            ).fetchone(),
        )[0]
        with pytest.raises(psycopg.errors.CheckViolation) as failure:
            connection.execute(
                """
                INSERT INTO rulings (
                    ruling_id, tenant_id, project_key, verbatim_bytes, verbatim_sha256,
                    recorded_by, seat_key, recorded_at, command_id, event_id,
                    supersedes_ruling_id, request_id, decision_blocker_fact_id
                )
                SELECT %s, tenant_id, project_key, verbatim_bytes, verbatim_sha256,
                       recorded_by, seat_key, recorded_at, %s, event_id,
                       ruling_id, request_id, %s
                FROM rulings WHERE ruling_id = %s
                """,
                (uuid4(), uuid4(), decision_fact_id, predecessor_id),
            )
        connection.rollback()
    return failure.value.sqlstate or "unknown"


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
