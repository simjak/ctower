"""Focused acceptance fixtures for Request-maintenance proposal review."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from ctower_kernel.record import RecordProblem
from ctower_kernel.work.requests import PostgresRequests

from .acceptance import accept_pending_commands
from .server import application
from .telemetry import telemetry_headers
from .tenant_fixture import TenantFixture

__all__ = ["assert_done_and_unread_targets_are_not_actionable", "evidence_payload", "policy_fields"]
HTTP_OK = 200
HTTP_PENDING = 202


def assert_done_and_unread_targets_are_not_actionable(
    tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise both known-DONE and unread Request state through the real API store."""

    with TestClient(application(tenant.database.runtime_dsn)) as client:
        request_id = _append_open_proposal_and_finish_request(client, tenant)
        review = client.get(
            "/v1/request-maintenance/review",
            headers=_query_headers(tenant.operator_credential),
        )
        assert review.status_code == HTTP_OK, review.json()
        assert all(row["request_id"] != str(request_id) for row in review.json()["rows"])
        monkeypatch.setattr(PostgresRequests, "list", _unavailable_request_read)
        unread = client.get(
            "/v1/request-maintenance/review",
            headers=_query_headers(tenant.operator_credential),
        )

    assert unread.status_code == HTTP_OK, unread.json()
    assert unread.json()["rows"] == []
    assert unread.json()["partial"] is True
    assert "requests:request-source-injected-unavailable" in unread.json()["unanswered_sources"]
    assert f"request-state-unreadable:{request_id}" in unread.json()["unanswered_sources"]


def evidence_payload(*items: dict[str, object]) -> list[dict[str, object]]:
    return [
        {key: value for key, value in item.items() if not key.startswith("_")} for item in items
    ]


def policy_fields(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for directory, name in (
        ("execution", "execution"),
        ("gates", "gate"),
        ("evidence", "evidence"),
    ):
        path = root / f"packs/policies/{directory}/trust-spine-four-stage-v1.yaml"
        result[f"{name}_policy_ref"] = f"ctower.trust-spine-four-stage.{directory}@1"
        result[f"{name}_policy_digest"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _append_open_proposal_and_finish_request(client: TestClient, tenant: TenantFixture) -> UUID:
    capture_command = uuid4()
    captured = client.post(
        "/v1/requests",
        headers=_mutation_headers(tenant.commander_credential, capture_command),
        json={
            "project_key": "ctower",
            "text": "An open maintenance proposal whose Request later becomes done.",
        },
    )
    assert captured.status_code == HTTP_PENDING, captured.json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    request_id = UUID(captured.json()["request_id"])
    target = _request_row(client, tenant, request_id)
    appended = client.post(
        "/v1/request-maintenance/proposals",
        headers=_mutation_headers(tenant.commander_credential),
        json={
            "ambiguity_reason": None,
            "basis": "recorded-evidence",
            "evidence": [_event_evidence(tenant, capture_command)],
            "kind": "keep",
            "project_key": "ctower",
            "source_record_position": _record_watermark(tenant),
            "target_expected_version": 1,
            "target_request_id": str(request_id),
            "target_text": target["content"],
        },
    )
    assert appended.status_code == HTTP_PENDING, appended.json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    _finish_request(client, tenant, request_id)
    assert _request_row(client, tenant, request_id)["state"] == "DONE"
    return request_id


def _finish_request(client: TestClient, tenant: TenantFixture, request_id: UUID) -> None:
    triaged = client.post(
        f"/v1/requests/{request_id}/triage",
        headers=_mutation_headers(tenant.operator_credential),
        json={
            "canonical_request_id": None,
            "disposition": "REJECTED",
            "expected_version": 1,
            "reason": "The operator rejected the Request.",
        },
    )
    assert triaged.status_code == HTTP_PENDING, triaged.json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    evaluated = client.post(
        f"/v1/requests/{request_id}/closure-evaluations",
        headers=_mutation_headers(tenant.operator_credential),
        json={"expected_version": 2, "reason": "Evaluate the recorded rejection."},
    )
    assert evaluated.status_code == HTTP_PENDING, evaluated.json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)


def _request_row(client: TestClient, tenant: TenantFixture, request_id: UUID) -> dict[str, object]:
    response = client.get(
        "/v1/requests",
        headers=_query_headers(tenant.commander_credential),
        params={"project_key": "ctower"},
    )
    assert response.status_code == HTTP_OK, response.json()
    return next(
        cast(dict[str, object], row)
        for row in response.json()["rows"]
        if row["request_id"] == str(request_id)
    )


def _event_evidence(tenant: TenantFixture, command_id: UUID) -> dict[str, object]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """SELECT event_id, kind, event_hash FROM events
               WHERE tenant_id = %s AND client_command_id = %s AND kind = 'request.changed'""",
            (tenant.tenant_id, command_id),
        ).fetchone()
    assert row is not None
    return {
        "event_digest": f"sha256:{bytes(row['event_hash']).hex()}",
        "event_id": str(row["event_id"]),
        "event_kind": str(row["kind"]),
        "kind": "record-event",
    }


def _record_watermark(tenant: TenantFixture) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT last_position FROM record_position_ledger WHERE singleton"
        ).fetchone()
    assert row is not None
    return int(row[0])


def _unavailable_request_read(*_args: object, **_kwargs: object) -> RecordProblem:
    return RecordProblem(
        code="request-source-injected-unavailable",
        detail="Injected unavailable Request projection",
        status=503,
        title="Request projection unavailable",
    )


def _mutation_headers(credential: str, command_id: UUID | None = None) -> dict[str, str]:
    identity = command_id or uuid4()
    return {
        "Authorization": f"Bearer {credential}",
        "Idempotency-Key": str(identity),
        **telemetry_headers(identity),
    }


def _query_headers(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}", **telemetry_headers()}
