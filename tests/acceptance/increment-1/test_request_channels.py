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
from support.project_hierarchy import declare_ctower_project
from support.server import application, running_api
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctowerctl import main
from ctowerctl.spool import Spool

__all__: tuple[str, ...] = ()

EXIT_SUCCESS = 0
EXIT_TEMPORARY = 75
HTTP_PENDING = 202
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
HTTP_UNAUTHORIZED = 401
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


def test_create_request_intake_refuses_external_submit_and_promotion_provenance(
    tenant: TenantFixture,
) -> None:
    """OR-01/05: ordinary intake cannot mint external Request provenance."""

    declare_ctower_project(tenant)
    external_command = uuid4()
    discussion_command = uuid4()
    promotion_command = uuid4()
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        external = client.post(
            "/v1/intake",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(external_command),
                **telemetry_headers(external_command),
            },
            json={
                "content": "Caller-declared external Request",
                "intent": "create_request",
                "project_key": "ctower",
                "source": {"kind": "slack", "ref": "channel:message"},
                "taint": "external_untrusted",
            },
        )
        discussion = client.post(
            "/v1/intake",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(discussion_command),
                **telemetry_headers(discussion_command),
            },
            json={
                "content": "External discussion remains discussion provenance",
                "project_key": "ctower",
                "source": {"kind": "slack", "ref": "channel:other-message"},
                "taint": "authenticated",
            },
        )
        assert discussion.status_code == HTTP_PENDING, discussion.text
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        promotion = client.post(
            f"/v1/intake/events/{discussion.json()['inbound_event_id']}/promotion",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(promotion_command),
                **telemetry_headers(promotion_command),
            },
            json={"expected_thread_version": 1, "intent": "create_request"},
        )

    assert external.status_code == promotion.status_code == HTTP_UNPROCESSABLE
    assert external.json()["code"] == promotion.json()["code"] == "request-source-forbidden"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        requests, inbound = cast(
            tuple[int, int],
            connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM requests WHERE tenant_id = %s),
                  (SELECT count(*) FROM inbound_events WHERE tenant_id = %s)
                """,
                (tenant.tenant_id, tenant.tenant_id),
            ).fetchone(),
        )
    assert requests == 0
    assert inbound == 1


def test_existing_tenant_capture_is_fenced_before_authority_epoch(
    tenant: TenantFixture,
) -> None:
    """OR-06: migration-time fencing exists before either native capture seam is exposed."""

    declare_ctower_project(tenant)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO request_native_capture_fences (tenant_id, reason, fenced_at)
            VALUES (%s, 'legacy-request-ledger-cutover', now())
            """,
            (tenant.tenant_id,),
        )
    request_command = uuid4()
    intake_command = uuid4()
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        request_capture = client.post(
            "/v1/requests",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(request_command),
                **telemetry_headers(request_command),
            },
            json={"project_key": "ctower", "text": "Must wait for cutover"},
        )
        intake_capture = client.post(
            "/v1/intake",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(intake_command),
                **telemetry_headers(intake_command),
            },
            json={
                "content": "Must also wait for cutover",
                "intent": "create_request",
                "project_key": "ctower",
                "source": {"kind": "native", "ref": "native:intake"},
            },
        )

    assert request_capture.status_code == intake_capture.status_code == HTTP_CONFLICT
    assert request_capture.json()["code"] == "migration-import-finalization-refused"
    assert intake_capture.json()["code"] == "migration-import-finalization-refused"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert (
            cast(tuple[int], connection.execute("SELECT count(*) FROM requests").fetchone())[0] == 0
        )


def test_request_validation_is_typed_and_path_identity_is_auth_first(
    tenant: TenantFixture,
) -> None:
    """OR-05: semantic whitespace and malformed paths never escape as FastAPI/500 bodies."""

    command_id = uuid4()
    headers = {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        whitespace = client.post(
            f"/v1/requests/{uuid4()}/priority",
            headers=headers,
            json={"expected_version": 1, "priority": "P1", "reason": " "},
        )
        unauthenticated_path = client.post(
            "/v1/requests/not-a-uuid/priority",
            json={"expected_version": 1, "priority": "P1", "reason": "valid"},
        )
        invalid_path = client.post(
            "/v1/requests/not-a-uuid/priority",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"expected_version": 1, "priority": "P1", "reason": "valid"},
        )

    assert whitespace.status_code == HTTP_UNPROCESSABLE
    assert whitespace.headers["content-type"].startswith("application/problem+json")
    assert whitespace.json()["code"] == "invalid-request"
    assert unauthenticated_path.status_code == HTTP_UNAUTHORIZED
    assert unauthenticated_path.headers["content-type"].startswith("application/problem+json")
    assert invalid_path.status_code == HTTP_UNPROCESSABLE
    assert invalid_path.headers["content-type"].startswith("application/problem+json")
    assert invalid_path.json()["code"] == "validation-error"


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


def test_operator_cli_duplicate_capture_speaks_and_same_merges_end_to_end(
    tenant: TenantFixture,
    protected_state: None,
) -> None:
    """AC-REQ-09/10: separate-process API + protected CLI speaks, links, and merges."""

    del protected_state
    first_text = "Please keep duplicate-aware Request capture visible to the operator."
    second_text = "Please keep duplicate aware Request capture visible for the operator."
    with running_api(tenant.database.runtime_dsn) as base_url:
        first = _accepted_cli_mutation(
            tenant,
            base_url,
            tenant.operator_credential,
            [
                "request",
                "capture",
                "--command-id",
                str(uuid4()),
                "--project-key",
                "ctower",
                first_text,
            ],
        )
        second = _accepted_cli_mutation(
            tenant,
            base_url,
            tenant.operator_credential,
            [
                "request",
                "capture",
                "--command-id",
                str(uuid4()),
                "--project-key",
                "ctower",
                second_text,
            ],
        )
        first_result = cast(dict[str, object], first["result"])
        second_result = cast(dict[str, object], second["result"])
        second_request_id = str(second_result["request_id"])
        expected_acknowledgement = (
            f"captured as {second_result['reference']}, resembles {first_result['reference']} "
            "(NEW), linked — say same to merge."
        )
        listed_status, listed = _run(
            ["--base-url", base_url, "request", "list", "--project-key", "ctower"],
            tenant.operator_credential,
        )
        merged = _accepted_cli_mutation(
            tenant,
            base_url,
            tenant.operator_credential,
            [
                "request",
                "same",
                second_request_id,
                "--command-id",
                str(uuid4()),
                "--expected-version",
                "1",
            ],
        )
        merged_status, merged_list = _run(
            ["--base-url", base_url, "request", "list", "--project-key", "ctower"],
            tenant.operator_credential,
        )

    assert second_result["acknowledgement"] == expected_acknowledgement
    assert cast(dict[str, object], second_result["resemblance"])["other_request_id"] == str(
        first_result["request_id"]
    )
    assert listed_status == merged_status == EXIT_SUCCESS
    rows = {row["request_id"]: row for row in cast(list[dict[str, object]], listed["rows"])}
    assert cast(list[object], rows[second_request_id]["resemblances"])
    merged_rows = {
        row["request_id"]: row for row in cast(list[dict[str, object]], merged_list["rows"])
    }
    provenance = cast(dict[str, object], merged_rows[second_request_id]["merge_provenance"])
    assert cast(dict[str, object], merged["result"])["operation"] == "same"
    assert merged_rows[second_request_id]["triage"] == "DUPLICATE"
    assert provenance["duplicate_content"] == second_text
    assert provenance["canonical_content"] == first_text
    print(
        "DEPLOYED_REQUEST_DUPLICATE_E2E"
        f" acknowledgement={second_result['acknowledgement']!r}"
        f" merge={cast(dict[str, object], merged['result'])['operation']}:DUPLICATE"
        f" provenance={provenance['duplicate_reference']}->{provenance['canonical_reference']}"
    )


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
