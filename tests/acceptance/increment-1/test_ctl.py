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
from typing import cast
from uuid import UUID, uuid4

import uvicorn
from support.postgres import DatabaseFixture
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.record.postgres import (
    PostgresRecord,
    apply_migrations,
    provision_bootstrap,
    provision_database_roles,
)
from ctowerctl import main

__all__: tuple[str, ...] = ()


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
    assert status == 0
    assert payload["command_id"] == str(command_id)
    assert payload["durability_state"] == "durability_pending"
    assert stderr == ""
    assert capability not in stdout


def test_ticket_create_show_and_assign_use_stable_command_ids(tenant: TenantFixture) -> None:
    create_id = uuid4()
    assign_id = uuid4()
    with _server(tenant.database.runtime_dsn) as base_url:
        create_status, created_text, create_error = _run(
            _create_arguments(base_url, tenant, create_id),
            authority=tenant.operator_credential,
        )
        created = json.loads(created_text)
        ticket_id = UUID(created["ticket"]["ticket_id"])
        show_status, shown_text, show_error = _run(
            ["--base-url", base_url, "ticket", "show", str(ticket_id)],
            authority=tenant.operator_credential,
        )
        assign_status, assigned_text, assign_error = _run(
            _assign_arguments(base_url, tenant, ticket_id, assign_id),
            authority=tenant.operator_credential,
        )

    shown = json.loads(shown_text)
    assigned = json.loads(assigned_text)
    assert (create_status, show_status, assign_status) == (0, 0, 0)
    assert create_error == show_error == assign_error == ""
    assert created["command_id"] == str(create_id)
    assert created["durability_state"] == "durability_pending"
    assert shown == created["ticket"]
    assert assigned["command_id"] == str(assign_id)
    assert assigned["ticket"]["custodian_id"] == str(tenant.operator_id)
    assert tenant.operator_credential not in created_text + shown_text + assigned_text


def test_offline_mutation_is_loudly_unsent_with_caller_command_id(
    tenant: TenantFixture,
) -> None:
    command_id = uuid4()
    status, stdout, stderr = _run(
        _create_arguments(_unused_base_url(), tenant, command_id),
        authority=tenant.operator_credential,
    )

    assert status != 0
    assert stdout == ""
    assert stderr == f"unsent command_id={command_id}: ctower is unreachable\n"
    assert tenant.operator_credential not in stderr


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
        "--from-custodian-id",
        str(tenant.commander_id),
        "--to-custodian-id",
        str(tenant.operator_id),
        "--reason",
        "Protected CLI transfer",
        "--protected-transfer",
    ]


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
def _server(dsn: str) -> Iterator[str]:
    port = _unused_port()
    config = uvicorn.Config(
        create_app(PostgresRecord(dsn)),
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
