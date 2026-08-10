"""Real seat-CLI caller evidence for the Phase-1 Request authority."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from support.acceptance import accept_pending_commands
from support.server import application, running_api
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctowerctl import main
from ctowerctl.spool import Spool

__all__: tuple[str, ...] = ()

EXIT_SUCCESS = 0
EXIT_TEMPORARY = 75
HTTP_UNPROCESSABLE = 422
TRIAGED_VERSION = 3


class _MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


@pytest.fixture
def protected_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _MemoryBackend()
    monkeypatch.setattr("ctowerctl.spool._keyring._secure_backend", lambda: backend)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def test_seat_cli_capture_keeps_pending_in_the_spool_and_replays_one_request(
    tenant: TenantFixture,
    protected_state: None,
) -> None:
    """OR-01/04/05: the real CLI reaches one command with honest custody state."""

    del protected_state
    command_id = uuid4()
    with running_api(tenant.database.runtime_dsn) as base_url:
        arguments = [
            "--base-url",
            base_url,
            "request",
            "capture",
            "--command-id",
            str(command_id),
            "--project-key",
            "ctower",
            "Keep the operator outcome visible.",
        ]
        pending_status, pending = _run(arguments, tenant.commander_credential)
        hidden_status, hidden = _run(
            ["--base-url", base_url, "request", "list", "--project-key", "ctower"],
            tenant.commander_credential,
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        accepted_status, accepted = _run(arguments, tenant.commander_credential)
        listed_status, listed = _run(
            ["--base-url", base_url, "request", "list", "--project-key", "ctower"],
            tenant.commander_credential,
        )

    assert pending_status == EXIT_TEMPORARY
    assert pending["state"] == "queued"
    pending_result = cast(dict[str, object], pending["result"])
    accepted_result = cast(dict[str, object], accepted["result"])
    assert pending_result["durability_state"] == "durability_pending"
    assert hidden_status == listed_status == accepted_status == EXIT_SUCCESS
    assert hidden["rows"] == []
    assert accepted["state"] == "accepted"
    assert accepted_result["durability_state"] == "accepted"
    assert accepted_result["request_id"] == pending_result["request_id"]
    assert accepted_result["reference"] == pending_result["reference"]
    assert len(cast(list[object], listed["rows"])) == 1
    spool = Spool.for_origin(base_url).status()
    assert spool.pending_count == 0
    assert spool.accepted_count == 1
    print(
        "REAL_REQUEST_CLI"
        f" pending={pending_status}:{pending_result['durability_state']}"
        f" accepted={accepted_status}:{accepted_result['durability_state']}"
        f" reference={accepted_result['reference']}"
    )


def test_capture_schema_rejects_identity_and_authority_claims_before_mutation(
    tenant: TenantFixture,
) -> None:
    """OR-05: Actor, owner, number, state, and source are server facts only."""

    command_id = uuid4()
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        response = client.post(
            "/v1/requests",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
            json={
                "project_key": "ctower",
                "text": "Caller claims are forbidden.",
                "owner_id": str(tenant.commander_id),
                "request_number": 1,
                "source": {"kind": "external", "ref": "claimed"},
                "state": "DONE",
            },
        )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json()["code"] == "validation-error"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert (
            cast(tuple[int], connection.execute("SELECT count(*) FROM requests").fetchone())[0] == 0
        )


def test_seat_cli_priority_and_triage_use_generated_request_paths(
    tenant: TenantFixture,
    protected_state: None,
) -> None:
    """The authored CLI handlers invoke the generated transition operations end to end."""

    del protected_state
    with running_api(tenant.database.runtime_dsn) as base_url:
        captured = _accepted_cli_mutation(
            tenant,
            base_url,
            tenant.commander_credential,
            [
                "request",
                "capture",
                "--command-id",
                str(uuid4()),
                "--project-key",
                "ctower",
                "CLI transition intent",
            ],
        )
        capture_result = cast(dict[str, object], captured["result"])
        request_id = str(capture_result["request_id"])
        prioritized = _accepted_cli_mutation(
            tenant,
            base_url,
            tenant.commander_credential,
            [
                "request",
                "prioritize",
                request_id,
                "--command-id",
                str(uuid4()),
                "--expected-version",
                "1",
                "--priority",
                "P1",
                "--reason",
                "operator impact",
            ],
        )
        triaged = _accepted_cli_mutation(
            tenant,
            base_url,
            tenant.commander_credential,
            [
                "request",
                "triage",
                request_id,
                "--command-id",
                str(uuid4()),
                "--expected-version",
                "2",
                "--disposition",
                "ACCEPTED",
            ],
        )

    assert cast(dict[str, object], prioritized["result"])["operation"] == "priority"
    assert cast(dict[str, object], triaged["result"])["operation"] == "triage"
    assert cast(dict[str, object], triaged["result"])["version"] == TRIAGED_VERSION


def _accepted_cli_mutation(
    tenant: TenantFixture,
    base_url: str,
    credential: str,
    arguments: list[str],
) -> dict[str, object]:
    complete = ["--base-url", base_url, *arguments]
    pending_status, _pending = _run(complete, credential)
    assert pending_status == EXIT_TEMPORARY
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    accepted_status, accepted = _run(complete, credential)
    assert accepted_status == EXIT_SUCCESS
    assert accepted["state"] == "accepted"
    return accepted


def _run(arguments: list[str], credential: str) -> tuple[int, dict[str, object]]:
    stdout, stderr = io.StringIO(), io.StringIO()
    status = main(
        arguments,
        stdin=io.StringIO(f"{credential}\n"),
        stdout=stdout,
        stderr=stderr,
    )
    assert stderr.getvalue() == ""
    return status, cast(dict[str, object], json.loads(stdout.getvalue()))
