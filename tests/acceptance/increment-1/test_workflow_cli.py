"""First-day Workflow lifecycle through ctowerctl alone."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from support.acceptance import accept_pending_commands
from support.server import running_api
from support.tenant_fixture import TenantFixture

from ctowerctl import main

__all__: tuple[str, ...] = ()

EXIT_PENDING = 75
EXIT_PERMANENT = 69


class _MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


def test_cli_reaches_resolved_closed_with_installed_defaults(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_spool(monkeypatch, tmp_path)
    proof_input = _proof_input(tmp_path)

    with running_api(tenant.database.runtime_dsn) as base_url:
        ticket_id, workflow_ref, started = _begin(base_url, tenant)
        _reach_verification(base_url, tenant, ticket_id, workflow_ref, proof_input)
        _prove(base_url, tenant, ticket_id, proof_input)
        closed = _finish(base_url, tenant, ticket_id, workflow_ref)

    start_result = cast(dict[str, object], started["result"])
    close_result = cast(dict[str, object], closed["result"])
    assert start_result["workflow_ref"] == workflow_ref
    assert close_result["workflow_ref"] == workflow_ref
    assert close_result["lifecycle_facts"] == ["resolved", "closed"]


def test_cli_accepts_exact_selection_and_refuses_wrong_digest(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_spool(monkeypatch, tmp_path)
    with running_api(tenant.database.runtime_dsn) as base_url:
        discovery = _success(base_url, ["ticket", "workflow", "list"])
        revision = cast(list[dict[str, object]], discovery["revisions"])[0]
        exact_ticket = _admitted_ticket(base_url, tenant, "R2426-exact")
        exact = _pending(
            base_url,
            tenant.commander_credential,
            _explicit_start(exact_ticket, revision),
        )
        _accept(tenant)
        _drain(base_url, tenant.commander_credential)
        wrong_ticket = _admitted_ticket(base_url, tenant, "R2426-wrong")
        wrong_revision = dict(revision)
        wrong_revision["workflow_digest"] = "sha256:" + "f" * 64
        wrong_status, wrong = _run(
            base_url,
            tenant.commander_credential,
            _explicit_start(wrong_ticket, wrong_revision),
        )

    exact_result = cast(dict[str, object], exact["result"])
    wrong_result = cast(dict[str, object], wrong["result"])
    assert exact_result["workflow_ref"] == revision["workflow_ref"]
    assert wrong_status == EXIT_PERMANENT
    assert wrong["state"] == "quarantined"
    assert wrong_result["code"] == "workflow-pin-mismatch"


def _configure_spool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    backend = _MemoryBackend()
    monkeypatch.setattr("ctowerctl.spool._keyring._secure_backend", lambda: backend)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def _proof_input(tmp_path: Path) -> tuple[str, str, Path, Path]:
    content = "workflow cli evidence"
    candidate_digest = "sha256:" + "c" * 64
    artifact_digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    criteria_path = tmp_path / "criteria.json"
    evidence_path = tmp_path / "evidence.txt"
    criteria_path.write_text(
        json.dumps(
            [
                {
                    "key": "artifact-current",
                    "description": "Artifact evidence matches the current candidate.",
                    "candidate_dependent": True,
                    "requires_verdict": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    evidence_path.write_text(content, encoding="utf-8")
    return candidate_digest, artifact_digest, criteria_path, evidence_path


def _begin(base_url: str, tenant: TenantFixture) -> tuple[str, str, dict[str, object]]:
    discovery = _success(base_url, ["ticket", "workflow", "list"])
    revisions = cast(list[dict[str, object]], discovery["revisions"])
    workflow_ref = cast(str, revisions[0]["workflow_ref"])
    ticket_id = _admitted_ticket(base_url, tenant, "R2426")
    started = _pending(
        base_url,
        tenant.commander_credential,
        _ticket_command("workflow", "start", ticket_id),
    )
    _accept(tenant)
    return ticket_id, workflow_ref, started


def _admitted_ticket(base_url: str, tenant: TenantFixture, source_ref: str) -> str:
    created = _pending(
        base_url,
        tenant.commander_credential,
        [
            "ticket",
            "create",
            "--priority",
            "P2",
            "--source-kind",
            "acceptance",
            "--source-ref",
            source_ref,
            "--title",
            "Reachable lifecycle",
        ],
    )
    create_result = cast(dict[str, object], created["result"])
    created_ticket = cast(dict[str, object], create_result["ticket"])
    ticket_id = cast(str, created_ticket["ticket_id"])
    _accept(tenant)
    _pending(
        base_url,
        tenant.commander_credential,
        _ticket_command(
            "admit",
            ticket_id,
            "--expected-version",
            "1",
            "--reason",
            "Ready for Workflow",
        ),
    )
    _accept(tenant)
    return ticket_id


def _reach_verification(
    base_url: str,
    tenant: TenantFixture,
    ticket_id: str,
    workflow_ref: str,
    proof_input: tuple[str, str, Path, Path],
) -> None:
    candidate_digest, _, criteria_path, _ = proof_input
    _pending(
        base_url,
        tenant.commander_credential,
        _transition(ticket_id, workflow_ref, 1, "capture", "frame"),
    )
    _accept(tenant)
    _pending(
        base_url,
        tenant.commander_credential,
        _ticket_command(
            "criteria",
            "freeze",
            ticket_id,
            "--expected-version",
            "0",
            "--candidate-digest",
            candidate_digest,
            "--criteria-file",
            str(criteria_path),
        ),
    )
    _accept(tenant)
    _pending(
        base_url,
        tenant.commander_credential,
        _transition(ticket_id, workflow_ref, 2, "frame", "verify"),
    )
    _accept(tenant)


def _prove(
    base_url: str,
    tenant: TenantFixture,
    ticket_id: str,
    proof_input: tuple[str, str, Path, Path],
) -> None:
    candidate_digest, artifact_digest, _, evidence_path = proof_input
    _pending(
        base_url,
        tenant.commander_credential,
        _ticket_command(
            "evidence",
            "add",
            ticket_id,
            "--expected-version",
            "1",
            "--evidence-id",
            str(uuid4()),
            "--criterion-key",
            "artifact-current",
            "--candidate-digest",
            candidate_digest,
            "--artifact-digest",
            artifact_digest,
            "--content-file",
            str(evidence_path),
        ),
    )
    _accept(tenant)
    _drain(base_url, tenant.commander_credential)
    _pending(
        base_url,
        tenant.operator_credential,
        _ticket_command(
            "gate",
            "verdict",
            ticket_id,
            "--expected-version",
            "2",
            "--verdict-id",
            str(uuid4()),
            "--criterion-key",
            "artifact-current",
            "--candidate-digest",
            candidate_digest,
            "--decision",
            "pass",
        ),
    )
    _accept(tenant)
    _drain(base_url, tenant.operator_credential)


def _finish(
    base_url: str,
    tenant: TenantFixture,
    ticket_id: str,
    workflow_ref: str,
) -> dict[str, object]:
    _pending(
        base_url,
        tenant.commander_credential,
        _transition(ticket_id, workflow_ref, 3, "verify", "close"),
    )
    _accept(tenant)
    closed = _pending(
        base_url,
        tenant.commander_credential,
        _ticket_command("resolve", ticket_id, "--expected-version", "4"),
    )
    _accept(tenant)
    _drain(base_url, tenant.commander_credential)
    return closed


def _ticket_command(*parts: str) -> list[str]:
    return ["ticket", *parts, "--command-id", str(uuid4())]


def _transition(
    ticket_id: str,
    workflow_ref: str,
    version: int,
    source: str,
    destination: str,
) -> list[str]:
    return _ticket_command(
        "transition",
        ticket_id,
        "--expected-version",
        str(version),
        "--workflow-ref",
        workflow_ref,
        "--source-stage",
        source,
        "--destination-stage",
        destination,
    )


def _explicit_start(ticket_id: str, revision: dict[str, object]) -> list[str]:
    command = _ticket_command("workflow", "start", ticket_id)
    for field in (
        "workflow_ref",
        "workflow_digest",
        "execution_policy_ref",
        "execution_policy_digest",
        "gate_policy_ref",
        "gate_policy_digest",
        "evidence_policy_ref",
        "evidence_policy_digest",
    ):
        command.extend(("--" + field.replace("_", "-"), cast(str, revision[field])))
    return command


def _pending(base_url: str, credential: str, arguments: list[str]) -> dict[str, object]:
    status, payload = _run(base_url, credential, arguments)
    assert status == EXIT_PENDING
    return payload


def _success(base_url: str, arguments: list[str]) -> dict[str, object]:
    status, payload = _run(base_url, "", arguments)
    assert status == 0
    return payload


def _drain(base_url: str, credential: str) -> None:
    status, _ = _run(base_url, credential, ["spool", "drain"])
    assert status == 0


def _run(
    base_url: str,
    credential: str,
    arguments: list[str],
) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    status = main(
        ["--base-url", base_url, *arguments],
        stdin=io.StringIO(credential + "\n"),
        stdout=stdout,
        stderr=stderr,
    )
    assert stderr.getvalue() == ""
    return status, cast(dict[str, object], json.loads(stdout.getvalue()))


def _accept(tenant: TenantFixture) -> None:
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
