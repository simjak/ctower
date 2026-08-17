"""CLI roundtrip driver for native inbox acceptance evidence."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from support.acceptance import accept_pending_commands
from support.server import running_api
from support.tenant_fixture import TenantFixture

from ctower_kernel.inbox import InboxAcknowledgementState
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctowerctl import main

__all__: tuple[str, ...] = ()

EXIT_SUCCESS = 0
EXIT_TEMPORARY = 75


@dataclass(frozen=True, slots=True)
class AcknowledgementRoundTrip:
    after_ack: dict[str, object]
    delivered_ack: dict[str, object]
    delivered_state: dict[str, object]
    initial_state: dict[str, object]
    read_ack: dict[str, object]
    read_state: dict[str, object]


@dataclass(frozen=True, slots=True)
class RoundTrip:
    acknowledgements: AcknowledgementRoundTrip
    commander_list: dict[str, object]
    commander_read: dict[str, object]
    first: dict[str, object]
    projections: Projections
    qa_list: dict[str, object]
    qa_read: dict[str, object]
    reply: dict[str, object]
    thread_id: UUID


def promote(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    thread_id: UUID,
    *,
    ticket_id: UUID | None = None,
) -> dict[str, object]:
    """Drive the public CLI promotion mutation through pending and accepted states."""

    with running_api(
        tenant.database.runtime_dsn,
        projection_dsn=tenant.database.projection_dsn,
    ) as base_url:
        arguments = [
            "--base-url",
            base_url,
            "inbox",
            "promote",
            "--command-id",
            str(uuid4()),
            str(thread_id),
        ]
        if ticket_id is not None:
            arguments.extend(("--ticket", str(ticket_id)))
        pending_status, pending = _run(
            monkeypatch,
            tmp_path / "commander",
            tenant.commander_credential,
            arguments,
        )
        assert pending_status == EXIT_TEMPORARY
        assert pending["state"] == "queued"
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        accepted_status, accepted = _run(
            monkeypatch,
            tmp_path / "commander",
            tenant.commander_credential,
            arguments,
        )
    assert accepted_status == EXIT_SUCCESS
    assert accepted["state"] == "accepted"
    return accepted


def roundtrip(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    qa_credential: str,
) -> RoundTrip:
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    commander_state, qa_state = tmp_path / "commander", tmp_path / "qa"
    with running_api(
        tenant.database.runtime_dsn,
        projection_dsn=tenant.database.projection_dsn,
    ) as base_url:
        first = _accepted_send(
            tenant,
            monkeypatch,
            state=commander_state,
            base_url=base_url,
            credential=tenant.commander_credential,
            to="qa-agent",
            text="Please verify the native inbox roundtrip.",
        )
        first_result = cast(dict[str, object], first["result"])
        thread_id = UUID(str(first_result["thread_id"]))
        projections.catch_up(tenant.tenant_id)
        qa_list = _initial_list(monkeypatch, qa_state, qa_credential, base_url)
        acknowledgements = _acknowledgements(
            tenant,
            monkeypatch,
            projections,
            qa_state,
            qa_credential,
            base_url,
            thread_id,
            UUID(str(first_result["message_id"])),
        )
        qa_read = _query(
            monkeypatch,
            qa_state,
            qa_credential,
            ["--base-url", base_url, "inbox", "read", str(thread_id)],
        )
        reply = _accepted_send(
            tenant,
            monkeypatch,
            state=qa_state,
            base_url=base_url,
            credential=qa_credential,
            to="ctower-commander",
            text="Verified; the reply is durable.",
            thread_id=thread_id,
        )
        projections.catch_up(tenant.tenant_id)
        commander = _commander_queries(tenant, monkeypatch, commander_state, base_url, thread_id)
    return RoundTrip(
        acknowledgements,
        commander[0],
        commander[1],
        first,
        projections,
        qa_list,
        qa_read,
        reply,
        thread_id,
    )


def _acknowledgements(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    projections: Projections,
    state: Path,
    credential: str,
    base_url: str,
    thread_id: UUID,
    message_id: UUID,
) -> AcknowledgementRoundTrip:
    query = ["--base-url", base_url, "inbox", "read-state", str(thread_id)]
    initial_state = _query(monkeypatch, state, credential, query)
    delivered_ack = _accepted_ack(
        tenant,
        monkeypatch,
        state=state,
        base_url=base_url,
        credential=credential,
        message_id=message_id,
        acknowledgement=InboxAcknowledgementState.DELIVERED,
    )
    projections.catch_up(tenant.tenant_id)
    delivered_state = _query(monkeypatch, state, credential, query)
    read_ack = _accepted_ack(
        tenant,
        monkeypatch,
        state=state,
        base_url=base_url,
        credential=credential,
        message_id=message_id,
        acknowledgement=InboxAcknowledgementState.READ,
    )
    projections.catch_up(tenant.tenant_id)
    read_state = _query(monkeypatch, state, credential, query)
    after_ack = _query(
        monkeypatch,
        state,
        credential,
        ["--base-url", base_url, "inbox", "list", "--unread"],
    )
    return AcknowledgementRoundTrip(
        after_ack, delivered_ack, delivered_state, initial_state, read_ack, read_state
    )


def _initial_list(
    monkeypatch: pytest.MonkeyPatch, state: Path, credential: str, base_url: str
) -> dict[str, object]:
    return _query(
        monkeypatch,
        state,
        credential,
        ["--base-url", base_url, "inbox", "list", "--unread"],
    )


def _commander_queries(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    base_url: str,
    thread_id: UUID,
) -> tuple[dict[str, object], dict[str, object]]:
    listed = _query(
        monkeypatch,
        state,
        tenant.commander_credential,
        ["--base-url", base_url, "inbox", "list", "--unread"],
    )
    read = _query(
        monkeypatch,
        state,
        tenant.commander_credential,
        ["--base-url", base_url, "inbox", "read", str(thread_id)],
    )
    return listed, read


def _accepted_send(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    *,
    state: Path,
    base_url: str,
    credential: str,
    to: str,
    text: str,
    severity: str = "info",
    project_key: str = "ctower",
    thread_id: UUID | None = None,
) -> dict[str, object]:
    command_id = uuid4()
    arguments = [
        "--base-url",
        base_url,
        "inbox",
        "send",
        "--command-id",
        str(command_id),
        "--to",
        to,
        "--severity",
        severity,
        "--project-key",
        project_key,
    ]
    if thread_id is not None:
        arguments.extend(("--thread", str(thread_id)))
    arguments.append(text)
    pending_status, pending = _run(monkeypatch, state, credential, arguments)
    assert pending_status == EXIT_TEMPORARY
    assert pending["state"] == "queued"
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    accepted_status, accepted = _run(monkeypatch, state, credential, arguments)
    assert accepted_status == EXIT_SUCCESS
    assert accepted["state"] == "accepted"
    return accepted


def _accepted_ack(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    *,
    state: Path,
    base_url: str,
    credential: str,
    message_id: UUID,
    acknowledgement: InboxAcknowledgementState,
) -> dict[str, object]:
    arguments = [
        "--base-url",
        base_url,
        "inbox",
        "ack",
        "--command-id",
        str(uuid4()),
        "--state",
        acknowledgement.value,
        str(message_id),
    ]
    pending_status, pending = _run(monkeypatch, state, credential, arguments)
    assert pending_status == EXIT_TEMPORARY
    assert pending["state"] == "queued"
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    accepted_status, accepted = _run(monkeypatch, state, credential, arguments)
    assert accepted_status == EXIT_SUCCESS
    assert accepted["state"] == "accepted"
    return accepted


def _query(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    credential: str,
    arguments: list[str],
) -> dict[str, object]:
    status, payload = _run(monkeypatch, state, credential, arguments)
    assert status == EXIT_SUCCESS
    return payload


def _run(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    credential: str,
    arguments: list[str],
) -> tuple[int, dict[str, object]]:
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    stdout, stderr = io.StringIO(), io.StringIO()
    status = main(arguments, stdin=io.StringIO(credential + "\n"), stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return status, cast(dict[str, object], json.loads(stdout.getvalue()))
