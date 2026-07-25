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
from ctower_contracts import CATALOG
from fastapi.testclient import TestClient
from support.catalog import MemoryObjectStore, minimal_bundle
from support.postgres import DatabaseFixture
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.catalog import CompanyBundle, PostgresCatalog
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
HTTP_PENDING = 202


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
    create_id = uuid4()
    with _server(tenant.database.runtime_dsn) as base_url:
        create_status, created_text, create_error = _run(
            _create_arguments(base_url, tenant, create_id),
            authority=tenant.operator_credential,
        )
        created = json.loads(created_text)
        ticket_id = UUID(created["result"]["ticket"]["ticket_id"])
        show_status, shown_text, show_error = _run(
            ["--base-url", base_url, "ticket", "query", str(ticket_id)],
            authority=tenant.operator_credential,
        )

    shown = json.loads(shown_text)
    assert (create_status, show_status) == (EXIT_TEMPORARY, 0)
    assert create_error == show_error == ""
    assert created["command_id"] == str(create_id)
    assert created["state"] == "queued"
    assert created["reason_code"] == "durability_pending"
    assert created["result"]["durability_state"] == "durability_pending"
    assert shown == created["result"]["ticket"]
    assert tenant.operator_credential not in created_text + shown_text


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


def test_company_bundle_cli_validate_plan_apply_export_round_trip(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
    tmp_path: Path,
) -> None:
    del cli_state
    bundle_file = tmp_path / "company-bundle.yaml"
    bundle_file.write_text(
        json.dumps(_tenant_bundle().model_dump(mode="json", by_alias=True)),
        encoding="utf-8",
    )
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        CATALOG,
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
    )
    with _server(tenant.database.runtime_dsn, catalog=catalog) as base_url:
        validated, planned, applied, exported, replanned = _company_round_trip(
            base_url,
            bundle_file,
            tenant.operator_credential,
            tmp_path,
        )

    assert validated[0] == 0
    assert json.loads(validated[1])["valid"] is True
    assert planned[0] == 0
    assert applied[0] == EXIT_TEMPORARY
    assert json.loads(applied[1])["state"] == "queued"
    assert exported[0] == 0
    assert exported[1].endswith("\n") and not exported[1].endswith("\n\n")
    assert "metadata:" not in exported[1]
    assert json.loads(replanned[1])["actions"] == []


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
            ["--base-url", base_url, "ticket", "query", str(ticket_id)],
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
        "--source-kind",
        "mission-control",
        "--source-ref",
        "mission-control:cli",
        "--title",
        "CLI durable ticket",
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
    base_url: str, tenant: TenantFixture, ticket_id: UUID, command_id: UUID
) -> list[str]:
    return [
        "--base-url",
        base_url,
        "ticket",
        "assign",
        str(ticket_id),
        "--command-id",
        str(command_id),
        "--expected-version",
        "1",
        "--kind",
        "current_assignee",
        "--to-principal-id",
        str(tenant.operator_id),
        "--reason",
        "Ordinary CLI assignment",
    ]


def _custody_arguments(
    base_url: str, tenant: TenantFixture, ticket_id: UUID, command_id: UUID
) -> list[str]:
    return [
        "--base-url",
        base_url,
        "ticket",
        "custody",
        "transfer",
        str(ticket_id),
        "--command-id",
        str(command_id),
        "--expected-version",
        "1",
        "--from-custodian-id",
        str(tenant.commander_id),
        "--to-custodian-id",
        str(tenant.operator_id),
        "--reason",
        "Protected CLI transfer",
        "--protected-transfer",
    ]


def _seed_ticket(tenant: TenantFixture, title: str) -> UUID:
    with TestClient(create_app(PostgresRecord(tenant.database.runtime_dsn))) as client:
        response = client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(tenant.commander_id),
                "priority": "P1",
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


def _run_company(
    base_url: str,
    command: list[str],
    authority: str,
) -> tuple[int, str, str]:
    return _run(
        ["--base-url", base_url, "company", "bundle", *command],
        authority=authority,
    )


def _company_round_trip(
    base_url: str,
    bundle_file: Path,
    authority: str,
    output_directory: Path,
) -> tuple[
    tuple[int, str, str],
    tuple[int, str, str],
    tuple[int, str, str],
    tuple[int, str, str],
    tuple[int, str, str],
]:
    validated = _run_company(base_url, ["validate", str(bundle_file)], authority)
    planned = _run_company(base_url, ["plan", str(bundle_file)], authority)
    plan = json.loads(planned[1])
    applied = _run_company(
        base_url,
        [
            "apply",
            str(bundle_file),
            "--command-id",
            str(uuid4()),
            "--expected-active-version",
            "0",
            "--plan-digest",
            plan["plan_digest"],
        ],
        authority,
    )
    exported = _run_company(base_url, ["export"], authority)
    exported_file = output_directory / "exported.yaml"
    exported_file.write_text(exported[1], encoding="utf-8")
    replanned = _run_company(base_url, ["plan", str(exported_file)], authority)
    return validated, planned, applied, exported, replanned


def _tenant_bundle() -> CompanyBundle:
    bundle = minimal_bundle()
    return bundle.model_copy(
        update={
            "company": bundle.company.model_copy(
                update={"key": "ctower", "display_name": "Ctower"}
            ),
            "resources": tuple(
                resource.model_copy(
                    update={
                        "component": resource.component.model_copy(
                            update={
                                "scope": resource.component.scope.model_copy(
                                    update={"tenant": "ctower"}
                                )
                            }
                        )
                    }
                )
                for resource in bundle.resources
            ),
        }
    )


@contextmanager
def _server(
    dsn: str,
    *,
    catalog: PostgresCatalog | None = None,
) -> Iterator[str]:
    port = _unused_port()
    record = PostgresRecord(dsn)
    config = uvicorn.Config(
        create_app(
            record,
            work=Work(record, writer=PostgresWork(dsn)),
            catalog=catalog,
        ),
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


def _unused_base_url() -> str:
    return f"http://127.0.0.1:{_unused_port()}"


def _unused_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return cast(int, candidate.getsockname()[1])
