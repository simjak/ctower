"""Thin online CLI acceptance through the generated HTTP client."""

from __future__ import annotations

import io
import json
import secrets
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
import uvicorn
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from support.acceptance import accept_pending_commands
from support.catalog import activate_project_prefixes
from support.postgres import DatabaseFixture
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.catalog import PostgresCatalog
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record.postgres import (
    PostgresRecord,
    apply_migrations,
    provision_bootstrap,
    provision_database_roles,
)
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork
from ctowerctl import main
from ctowerctl.spool import Spool

__all__: tuple[str, ...] = ()

EXIT_TEMPORARY = 75
EXIT_LOCAL_FAILURE = 74
EXIT_PERMANENT = 69
HTTP_PENDING = 202
INITIAL_CUSTODY_REFUSAL = {"status": 403, "name": "unauthorized"}
PII_MARKER = "jane.doe+ct180@example.invalid"
BEARER_MARKER = "Bearer synthetic-refusal-probe-not-a-credential"
MARKED_REFUSAL: dict[str, object] = {
    "code": "unauthorized",
    "detail": f"Initial custody refused for {PII_MARKER} presenting {BEARER_MARKER}.",
    "status": 403,
    "title": f"Refused for {PII_MARKER}",
    "type": "https://ctower.example/problems/unauthorized",
}


class _MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


@pytest.fixture
def cli_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _MemoryBackend:
    backend = _MemoryBackend()
    monkeypatch.setattr("ctowerctl.spool._keyring._secure_backend", lambda: backend)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return backend


def test_bootstrap_reads_capability_from_stdin_and_prints_pending(
    database: DatabaseFixture,
) -> None:
    provision_database_roles(database.admin_dsn)
    apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)
    capability = secrets.token_urlsafe(32)
    provision_bootstrap(
        database.migrator_dsn,
        capability_input=io.StringIO(f"{capability}\n"),
        allowed_origin="127.0.0.1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    command_id = uuid4()
    with _server(database.runtime_dsn) as base_url:
        status, stdout, stderr = _run(
            _bootstrap_arguments(base_url, command_id),
            authority=capability,
        )

    payload = json.loads(stdout)
    assert status == EXIT_TEMPORARY
    assert payload["command_id"] == str(command_id)
    assert payload["durability_state"] == "durability_pending"
    assert stderr == ""
    assert capability not in stdout


def test_ticket_capture_and_query_use_stable_queued_command(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
) -> None:
    del cli_state
    activate_project_prefixes(tenant.database.runtime_dsn, tenant.tenant_id, tenant.operator_id)
    create_id = uuid4()
    with _server(tenant.database.runtime_dsn) as base_url:
        create_status, created_text, create_error = _run(
            _create_arguments(base_url, tenant, create_id),
            authority=tenant.operator_credential,
        )
        created = json.loads(created_text)
        ticket_id = UUID(created["result"]["ticket"]["ticket_id"])
        show_status, shown_text, show_error = _run(
            [
                "--base-url",
                base_url,
                "ticket",
                "query",
                str(ticket_id),
                "--project-key",
                "ctower",
            ],
            authority=tenant.operator_credential,
        )

    shown = json.loads(shown_text)
    assert (create_status, show_status) == (EXIT_TEMPORARY, 0)
    assert create_error == show_error == ""
    assert created["command_id"] == str(create_id)
    assert created["state"] == "queued"
    assert created["reason_code"] == "durability_pending"
    assert created["result"]["durability_state"] == "durability_pending"
    assert shown["display_key"] == "CTW-1"
    assert shown == created["result"]["ticket"]
    assert tenant.operator_credential not in created_text + shown_text


def test_ticket_create_without_hand_minted_identifiers_uses_authenticated_principal(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
) -> None:
    del cli_state
    with _server(tenant.database.runtime_dsn) as base_url:
        status, created_text, error = _run(
            _first_day_create_arguments(base_url, source_ref="R2257-defaults"),
            authority=tenant.commander_credential,
        )

    created = json.loads(created_text)
    assert status == EXIT_TEMPORARY
    assert error == ""
    assert UUID(created["command_id"])
    assert created["result"]["ticket"]["custodian_id"] == str(tenant.commander_id)
    assert created["result"]["ticket"]["source"] == {
        "kind": "mission-control",
        "ref": "R2257-defaults",
    }


def test_board_query_by_source_ref_returns_the_ticket_carrying_that_source(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
) -> None:
    del cli_state
    with _server(
        tenant.database.runtime_dsn,
        projections_dsn=tenant.database.projection_dsn,
    ) as base_url:
        create_status, created_text, create_error = _run(
            _first_day_create_arguments(base_url, source_ref="R74-live-hit"),
            authority=tenant.commander_credential,
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(tenant.tenant_id)
        query_status, query_text, query_error = _run(
            _board_query_arguments(base_url, source_ref="R74-live-hit"),
            authority=tenant.commander_credential,
        )

    created = json.loads(created_text)
    board = json.loads(query_text)
    assert (create_status, query_status) == (EXIT_TEMPORARY, 0)
    assert create_error == query_error == ""
    assert [card["ticket_id"] for card in board["cards"]] == [
        created["result"]["ticket"]["ticket_id"]
    ]


def test_board_query_by_source_ref_returns_no_rows_for_an_unrecognized_source(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
) -> None:
    del cli_state
    with _server(
        tenant.database.runtime_dsn,
        projections_dsn=tenant.database.projection_dsn,
    ) as base_url:
        create_status, _, create_error = _run(
            _first_day_create_arguments(base_url, source_ref="R74-live-miss-seed"),
            authority=tenant.commander_credential,
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(tenant.tenant_id)
        query_status, query_text, query_error = _run(
            _board_query_arguments(base_url, source_ref="R74-live-miss-unknown"),
            authority=tenant.commander_credential,
        )

    assert (create_status, query_status) == (EXIT_TEMPORARY, 0)
    assert create_error == query_error == ""
    assert json.loads(query_text)["cards"] == []


def test_server_rejected_capture_carries_its_named_refusal_to_the_spool_listing(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
) -> None:
    """A refused intake must stay named after the refusing invocation has exited."""

    del cli_state
    with _server(tenant.database.runtime_dsn) as base_url:
        status, captured_text, error = _run(
            _first_day_create_arguments(base_url, source_ref="R2597"),
            authority=tenant.operator_credential,
        )
        listing_status, listing_text, listing_error = _run(
            ["--base-url", base_url, "spool", "quarantine", "list"],
            authority=tenant.operator_credential,
        )

    captured = json.loads(captured_text)
    entries = json.loads(listing_text)["entries"]
    assert (status, listing_status) == (EXIT_PERMANENT, 0)
    assert error == listing_error == ""
    assert captured["state"] == "quarantined"
    assert captured["reason_code"] == "permanent_server_rejection"
    assert captured["server_refusal"] == INITIAL_CUSTODY_REFUSAL
    assert [entry["command_id"] for entry in entries] == [captured["command_id"]]
    assert entries[0]["reason_code"] == "permanent_server_rejection"
    assert entries[0]["server_refusal"] == INITIAL_CUSTODY_REFUSAL
    assert tenant.operator_credential not in captured_text + listing_text


def test_refusal_body_text_never_reaches_the_quarantine_receipt_or_its_listing(
    tmp_path: Path,
    cli_state: _MemoryBackend,
) -> None:
    """A schema-valid refusal may carry anything; only its allowlisted name survives.

    The refusing invocation still prints the response it just received as its own live
    `result`; nothing of that body reaches the durable receipt or any later listing.
    """

    del cli_state
    with _refusing_server(MARKED_REFUSAL) as base_url:
        status, captured_text, error = _run(
            _first_day_create_arguments(base_url, source_ref="R2597-marked"),
            authority="synthetic-marked-refusal-identity",
        )
        listing_status, listing_text, listing_error = _run(
            ["--base-url", base_url, "spool", "quarantine", "list"],
            authority="synthetic-marked-refusal-identity",
        )

    captured = json.loads(captured_text)
    entries = json.loads(listing_text)["entries"]
    receipts = _state_bytes(tmp_path)
    durable = json.dumps({key: captured[key] for key in captured if key != "result"})
    assert (status, listing_status) == (EXIT_PERMANENT, 0)
    assert error == listing_error == ""
    assert captured["reason_code"] == "permanent_server_rejection"
    assert captured["server_refusal"] == INITIAL_CUSTODY_REFUSAL
    assert entries[0]["server_refusal"] == INITIAL_CUSTODY_REFUSAL
    for marker in (PII_MARKER, BEARER_MARKER):
        assert marker not in durable
        assert marker not in listing_text
        assert marker.encode() not in receipts
        assert marker in captured["result"]["detail"] + captured["result"]["title"]


def test_explicit_ticket_command_id_replay_still_deduplicates_with_default_custodian(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
) -> None:
    del cli_state
    command_id = uuid4()
    with _server(tenant.database.runtime_dsn) as base_url:
        arguments = _first_day_create_arguments(
            base_url,
            source_ref="R2257-explicit-replay",
            command_id=command_id,
        )
        first = _run(arguments, authority=tenant.commander_credential)
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        replay = _run(arguments, authority=tenant.commander_credential)

    first_payload = json.loads(first[1])
    replay_payload = json.loads(replay[1])
    assert (first[0], replay[0]) == (EXIT_TEMPORARY, 0)
    assert first[2] == replay[2] == ""
    assert first_payload["command_id"] == replay_payload["command_id"] == str(command_id)
    assert {
        **first_payload["result"]["ticket"],
        "durability_state": "accepted",
    } == replay_payload["result"]["ticket"]
    assert first_payload["result"]["event_ids"] == replay_payload["result"]["event_ids"]
    assert _ticket_count(tenant.database.admin_dsn) == 1


def test_assignment_and_protected_custody_are_distinct_generated_commands(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
) -> None:
    del cli_state
    assigned_ticket = _seed_ticket(tenant, "Ordinary assignment")
    custody_ticket = _seed_ticket(tenant, "Protected custody")
    assign_id = uuid4()
    custody_id = uuid4()
    with _server(tenant.database.runtime_dsn) as assignment_url:
        assign_status, assigned_text, assign_error = _run(
            _assign_arguments(assignment_url, tenant, assigned_ticket, assign_id),
            authority=tenant.operator_credential,
        )
    with _server(tenant.database.runtime_dsn) as custody_url:
        custody_status, custody_text, custody_error = _run(
            _custody_arguments(custody_url, tenant, custody_ticket, custody_id),
            authority=tenant.operator_credential,
        )

    assigned = json.loads(assigned_text)
    transferred = json.loads(custody_text)
    assert (assign_status, custody_status) == (EXIT_TEMPORARY, EXIT_TEMPORARY)
    assert assign_error == custody_error == ""
    assert "result" in assigned, assigned
    assert "result" in transferred, transferred
    assert assigned["result"]["operation"] == "assignment_changed"
    assert assigned["result"]["ticket_id"] == str(assigned_ticket)
    assert transferred["result"]["ticket"]["custodian_id"] == str(tenant.operator_id)
    assert transferred["result"]["ticket"]["ticket_id"] == str(custody_ticket)


def test_ticket_assign_without_hand_minted_command_id_derives_one(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
) -> None:
    del cli_state
    ticket_id = _seed_ticket(tenant, "Derived command id assignment")
    with _server(tenant.database.runtime_dsn) as base_url:
        status, assigned_text, error = _run(
            _assign_arguments(base_url, tenant, ticket_id),
            authority=tenant.operator_credential,
        )

    assigned = json.loads(assigned_text)
    assert status == EXIT_TEMPORARY
    assert error == ""
    assert UUID(assigned["command_id"])
    assert assigned["result"]["operation"] == "assignment_changed"
    assert assigned["result"]["ticket_id"] == str(ticket_id)


def test_offline_mutation_is_durably_queued_with_caller_command_id(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
) -> None:
    del cli_state
    command_id = uuid4()
    base_url = _unused_base_url()
    status, stdout, stderr = _run(
        _create_arguments(base_url, tenant, command_id),
        authority=tenant.operator_credential,
    )

    payload = json.loads(stdout)
    assert status == EXIT_TEMPORARY
    assert payload["command_id"] == str(command_id)
    assert payload["state"] == "queued"
    assert payload["reason_code"] == "temporary_server_response"
    assert stderr == ""
    assert Spool.for_origin(base_url).status().pending_count == 1
    assert tenant.operator_credential not in stdout


def test_missing_keyring_blocks_mutation_before_send_but_reads_continue(
    tenant: TenantFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket_id = _seed_ticket(tenant, "Readable without spool key")
    before = _ticket_count(tenant.database.admin_dsn)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr("keyring.get_keyring", object)
    command_id = uuid4()
    with _server(tenant.database.runtime_dsn) as base_url:
        blocked = _run(
            _create_arguments(base_url, tenant, command_id),
            authority=tenant.operator_credential,
        )
        readable = _run(
            [
                "--base-url",
                base_url,
                "ticket",
                "query",
                str(ticket_id),
                "--project-key",
                "ctower",
            ],
            authority=tenant.operator_credential,
        )

    local = json.loads(blocked[1])
    assert blocked[0] == EXIT_LOCAL_FAILURE
    assert local == {
        "command_id": str(command_id),
        "reason_code": "keyring_unavailable",
        "state": "local_failure",
    }
    assert readable[0] == 0
    assert json.loads(readable[1])["ticket_id"] == str(ticket_id)
    assert _ticket_count(tenant.database.admin_dsn) == before


def test_control_health_exits_nonzero_while_a_contributor_is_unknown(
    tenant: TenantFixture,
) -> None:
    with _server(
        tenant.database.runtime_dsn,
        projections_dsn=tenant.database.projection_dsn,
    ) as base_url:
        status, output, error = _run(
            ["--base-url", base_url, "control", "health"],
            authority=tenant.operator_credential,
        )

    health = json.loads(output)
    assert status == EXIT_PERMANENT
    assert error == ""
    assert health["status"] != "HEALTHY"
    assert any(
        contributor["status"] == "STATE_UNKNOWN"
        for dimension in ("availability", "completeness", "integrity")
        for contributor in health[dimension]["contributors"]
    )


def _create_arguments(base_url: str, tenant: TenantFixture, command_id: UUID) -> list[str]:
    return [
        "--base-url",
        base_url,
        "ticket",
        "create",
        "--command-id",
        str(command_id),
        "--initial-custodian-id",
        str(tenant.commander_id),
        "--priority",
        "P1",
        "--project-key",
        "ctower",
        "--source-kind",
        "mission-control",
        "--source-ref",
        "mission-control:cli",
        "--title",
        "CLI durable ticket",
    ]


def _first_day_create_arguments(
    base_url: str,
    *,
    source_ref: str,
    command_id: UUID | None = None,
) -> list[str]:
    arguments = [
        "--base-url",
        base_url,
        "ticket",
        "create",
        "--priority",
        "P2",
        "--project-key",
        "ctower",
        "--source-kind",
        "mission-control",
        "--source-ref",
        source_ref,
        "--title",
        "First-day usable ticket",
    ]
    if command_id is not None:
        arguments.extend(("--command-id", str(command_id)))
    return arguments


def _board_query_arguments(base_url: str, *, source_ref: str) -> list[str]:
    return [
        "--base-url",
        base_url,
        "board",
        "query",
        "ctower",
        "--source-ref",
        source_ref,
    ]


def _bootstrap_arguments(base_url: str, command_id: UUID) -> list[str]:
    return [
        "--base-url",
        base_url,
        "bootstrap",
        "first-tenant",
        "--command-id",
        str(command_id),
        "--tenant-name",
        "CLI Tenant",
        "--tenant-slug",
        "cli-tenant",
        "--operator-name",
        "CLI Operator",
        "--operator-credential-ref",
        "credential-ref:cli/operator",
        "--operator-vault-ref",
        "vault-ref:cli/operator",
        "--commander-name",
        "CLI Commander",
        "--commander-vault-ref",
        "vault-ref:cli/commander",
    ]


def _assign_arguments(
    base_url: str,
    tenant: TenantFixture,
    ticket_id: UUID,
    command_id: UUID | None = None,
) -> list[str]:
    arguments = ["--base-url", base_url, "ticket", "assign", str(ticket_id)]
    arguments += ["--expected-version", "1", "--kind", "current_assignee"]
    arguments += ["--to-principal-id", str(tenant.operator_id)]
    arguments += ["--reason", "Ordinary CLI assignment"]
    if command_id is not None:
        arguments.extend(("--command-id", str(command_id)))
    return arguments


def _custody_arguments(
    base_url: str, tenant: TenantFixture, ticket_id: UUID, command_id: UUID
) -> list[str]:
    arguments = ["--base-url", base_url, "ticket", "custody", "transfer", str(ticket_id)]
    arguments += ["--command-id", str(command_id), "--expected-version", "1"]
    arguments += ["--from-custodian-id", str(tenant.commander_id)]
    arguments += ["--to-custodian-id", str(tenant.operator_id)]
    arguments += ["--reason", "Protected CLI transfer", "--protected-transfer"]
    return arguments


def _seed_ticket(tenant: TenantFixture, title: str) -> UUID:
    with TestClient(create_app(PostgresRecord(tenant.database.runtime_dsn))) as client:
        response = client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(tenant.commander_id),
                "priority": "P1",
                "project_key": "ctower",
                "source": {"kind": "test", "ref": "test:ctl-seed"},
                "title": title,
            },
            headers={
                "Authorization": f"Bearer {tenant.operator_credential}",
                "Idempotency-Key": str(uuid4()),
                **telemetry_headers(),
            },
        )
    assert response.status_code == HTTP_PENDING
    return UUID(cast(str, response.json()["ticket"]["ticket_id"]))


def _ticket_count(dsn: str) -> int:
    with psycopg.connect(dsn) as connection:
        row = connection.execute("SELECT count(*) FROM tickets").fetchone()
    assert row is not None
    return int(cast(int, row[0]))


def _run(arguments: list[str], *, authority: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    status = main(
        arguments,
        stdin=io.StringIO(f"{authority}\n"),
        stdout=stdout,
        stderr=stderr,
    )
    return status, stdout.getvalue(), stderr.getvalue()


@contextmanager
def _server(
    dsn: str,
    *,
    catalog: PostgresCatalog | None = None,
    projections_dsn: str | None = None,
) -> Iterator[str]:
    record = PostgresRecord(dsn)
    application = create_app(
        record,
        work=Work(record, writer=PostgresWork(dsn)),
        catalog=catalog,
        projections=(
            Projections(PostgresProjections(projections_dsn))
            if projections_dsn is not None
            else None
        ),
    )
    with _serve(application) as base_url:
        yield base_url


@contextmanager
def _refusing_server(problem: dict[str, object]) -> Iterator[str]:
    """Serve one schema-valid refusal whose body is whatever the origin chose to send."""

    application = FastAPI()
    body = json.dumps(problem)

    @application.post("/v1/tickets")
    def _refuse() -> Response:
        return Response(content=body, status_code=403, media_type="application/problem+json")

    with _serve(application) as base_url:
        yield base_url


@contextmanager
def _serve(application: FastAPI) -> Iterator[str]:
    port = _unused_port()
    config = uvicorn.Config(
        application,
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_config=None,
        log_level="critical",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_until_started(server, thread)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("acceptance API server did not stop")


def _wait_until_started(server: uvicorn.Server, thread: threading.Thread) -> None:
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        raise RuntimeError("acceptance API server did not start")


def _state_bytes(state: Path) -> bytes:
    return b"".join(path.read_bytes() for path in state.rglob("*") if path.is_file())


def _unused_base_url() -> str:
    return f"http://127.0.0.1:{_unused_port()}"


def _unused_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return cast(int, candidate.getsockname()[1])
