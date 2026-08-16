"""Protected CLI and encrypted-spool parity for thread-first intake."""

from __future__ import annotations

import io
import json
import socket
from pathlib import Path
from uuid import uuid4

import pytest
from support.acceptance import accept_pending_commands
from support.project_hierarchy import declare_ctower_project
from support.server import running_api
from support.tenant_fixture import TenantFixture

from ctowerctl import main
from ctowerctl.spool import Spool

__all__: tuple[str, ...] = ()

EXIT_TEMPORARY = 75
INITIAL_THREAD_VERSION = 1
PROMOTED_THREAD_VERSION = 2


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


def test_intake_cli_uses_generated_client_and_spools_before_every_send(
    tenant: TenantFixture,
    protected_state: None,
    tmp_path: Path,
) -> None:
    del protected_state
    declare_ctower_project(tenant)
    content = tmp_path / "discussion.txt"
    content.write_text("CLI durable discussion", encoding="utf-8")
    with running_api(tenant.database.runtime_dsn) as base_url:
        submit_id = uuid4()
        status, stdout, stderr = _run(
            _submit_arguments(base_url, submit_id, content),
            tenant.commander_credential,
        )
        submitted = json.loads(stdout)
        event_id = submitted["result"]["inbound_event_id"]
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        promotion_id = uuid4()
        promoted_status, promoted_stdout, promoted_stderr = _run(
            _promotion_arguments(
                base_url,
                event_id,
                promotion_id,
                tenant.commander_id,
            ),
            tenant.commander_credential,
        )

    promoted = json.loads(promoted_stdout)
    assert status == promoted_status == EXIT_TEMPORARY
    assert stderr == promoted_stderr == ""
    assert submitted["command_id"] == str(submit_id)
    assert submitted["result"]["outcome"] == "discussion"
    assert promoted["command_id"] == str(promotion_id)
    assert promoted["result"]["outcome"] == "ticket_created"
    spool_status = Spool.for_origin(base_url).status()
    assert spool_status.pending_count == 1
    assert spool_status.accepted_count == 1
    assert tenant.commander_credential not in stdout + promoted_stdout


def test_intake_cli_promotes_submitted_item_and_reads_it_back(
    tenant: TenantFixture,
    protected_state: None,
    tmp_path: Path,
) -> None:
    """The operator journey retains the receipt needed by promotion and exposes the ticket."""

    del protected_state
    declare_ctower_project(tenant)
    content = tmp_path / "promotion-readback.txt"
    content.write_text("CLI promotion read-back", encoding="utf-8")
    with running_api(tenant.database.runtime_dsn) as base_url:
        submit_id = uuid4()
        submit_status, submit_stdout, submit_stderr = _run(
            _submit_arguments(base_url, submit_id, content),
            tenant.commander_credential,
        )
        submitted = json.loads(submit_stdout)
        submitted_result = submitted["result"]
        event_id = submitted_result["inbound_event_id"]
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

        promotion_id = uuid4()
        promote_status, promote_stdout, promote_stderr = _run(
            _promotion_arguments(
                base_url,
                event_id,
                promotion_id,
                tenant.commander_id,
            ),
            tenant.commander_credential,
        )
        promoted = json.loads(promote_stdout)
        promoted_result = promoted["result"]
        ticket_id = promoted_result["ticket_id"]
        show_status, show_stdout, show_stderr = _run(
            [
                "--base-url",
                base_url,
                "ticket",
                "show",
                ticket_id,
                "--project-key",
                "ctower",
            ],
            tenant.operator_credential,
        )

    shown = json.loads(show_stdout)
    assert (submit_status, promote_status, show_status) == (EXIT_TEMPORARY, EXIT_TEMPORARY, 0)
    assert submit_stderr == promote_stderr == show_stderr == ""
    assert submitted_result["inbound_event_id"] == event_id
    assert submitted_result["thread_version"] == INITIAL_THREAD_VERSION
    assert promoted["command_id"] == str(promotion_id)
    assert promoted_result["inbound_event_id"] == event_id
    assert promoted_result["thread_version"] == PROMOTED_THREAD_VERSION
    assert promoted_result["outcome"] == "ticket_created"
    assert shown["ticket_id"] == ticket_id
    assert shown["title"] == "CLI promoted intake"
    assert shown["priority"] == "P2"
    assert shown["custodian_id"] == str(tenant.commander_id)
    assert shown["source"] == {"kind": "cli", "ref": f"cli:{submit_id}"}
    assert tenant.commander_credential not in submit_stdout + promote_stdout


def test_offline_intake_is_encrypted_and_queued_before_network_failure(
    tenant: TenantFixture,
    protected_state: None,
    tmp_path: Path,
) -> None:
    del protected_state
    content = tmp_path / "offline.txt"
    content.write_text("Offline durable discussion", encoding="utf-8")
    base_url = _unused_base_url()
    command_id = uuid4()
    status, stdout, stderr = _run(
        [
            "--base-url",
            base_url,
            "intake",
            "submit",
            "--command-id",
            str(command_id),
            "--project-key",
            "ctower",
            "--source-kind",
            "cli",
            "--source-ref",
            f"offline:{command_id}",
            "--content-file",
            str(content),
        ],
        tenant.commander_credential,
    )

    payload = json.loads(stdout)
    assert status == EXIT_TEMPORARY
    assert stderr == ""
    assert payload["command_id"] == str(command_id)
    assert payload["state"] == "queued"
    assert Spool.for_origin(base_url).status().pending_count == 1
    assert tenant.commander_credential not in stdout


def _submit_arguments(base_url: str, command_id: object, content: Path) -> list[str]:
    return [
        "--base-url",
        base_url,
        "intake",
        "submit",
        "--command-id",
        str(command_id),
        "--project-key",
        "ctower",
        "--source-kind",
        "cli",
        "--source-ref",
        f"cli:{command_id}",
        "--content-file",
        str(content),
    ]


def _promotion_arguments(
    base_url: str,
    event_id: str,
    command_id: object,
    custodian_id: object,
) -> list[str]:
    return [
        "--base-url",
        base_url,
        "intake",
        "promote",
        event_id,
        "--command-id",
        str(command_id),
        "--expected-thread-version",
        "1",
        "--intent",
        "create_ticket",
        "--initial-custodian-id",
        str(custodian_id),
        "--priority",
        "P2",
        "--title",
        "CLI promoted intake",
    ]


def _run(arguments: list[str], authority: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    status = main(
        arguments,
        stdin=io.StringIO(f"{authority}\n"),
        stdout=stdout,
        stderr=stderr,
    )
    return status, stdout.getvalue(), stderr.getvalue()


def _unused_base_url() -> str:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    return f"http://127.0.0.1:{port}"
