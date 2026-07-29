"""First-day Workflow lifecycle through the installed ctowerctl executable alone."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import IO, Self, cast
from uuid import uuid4

import pytest
from support.acceptance import accept_pending_commands
from support.installed_cli import install_ctowerctl
from support.server import running_api
from support.tenant_fixture import TenantFixture

__all__: tuple[str, ...] = ()

EXIT_PENDING = 75
EXIT_PERMANENT = 69
_ROOT = Path(__file__).parents[3]
_SECRET_SERVICE_LAUNCHER = _ROOT / "tests/integration/keyring/secret_service_launcher.py"
_CLI_BROKER = Path(__file__).with_name("support") / "cli_broker.py"


def test_cli_reaches_resolved_closed_with_installed_defaults(
    tenant: TenantFixture,
    tmp_path: Path,
    installed_ctowerctl: Path,
) -> None:
    with (
        _InstalledCli(tmp_path, installed_ctowerctl) as cli,
        running_api(tenant.database.runtime_dsn) as base_url,
    ):
        ticket_id, workflow_ref, started = _begin(cli, base_url, tenant, "R2426")
        frozen = _reach_verification(cli, base_url, tenant, ticket_id, workflow_ref)
        evidence, verdict = _prove(cli, base_url, tenant, ticket_id)
        closed = _finish(cli, base_url, tenant, ticket_id, workflow_ref)

    start_result = _result(started)
    frozen_result = _result(frozen)
    evidence_result = _result(evidence)
    verdict_result = _result(verdict)
    close_result = _result(closed)
    assert start_result["workflow_ref"] == workflow_ref
    assert frozen_result["candidate_digest"] == evidence_result["candidate_digest"]
    assert cast(str, evidence_result["artifact_digest"]).startswith("sha256:")
    assert verdict_result["candidate_digest"] == frozen_result["candidate_digest"]
    assert verdict_result["artifact_digest"] is None
    assert close_result["workflow_ref"] == workflow_ref
    assert close_result["lifecycle_facts"] == ["resolved", "closed"]


def test_cli_accepts_exact_workflow_selection_and_refuses_wrong_digest(
    tenant: TenantFixture,
    tmp_path: Path,
    installed_ctowerctl: Path,
) -> None:
    with (
        _InstalledCli(tmp_path, installed_ctowerctl) as cli,
        running_api(tenant.database.runtime_dsn) as base_url,
    ):
        discovery = _success(cli, base_url, ["ticket", "workflow", "list"])
        revision = cast(list[dict[str, object]], discovery["revisions"])[0]
        exact_ticket = _admitted_ticket(cli, base_url, tenant, "R2426-exact")
        exact = _pending(
            cli,
            base_url,
            tenant.commander_credential,
            _explicit_start(exact_ticket, revision),
        )
        _accept(tenant)
        _drain(cli, base_url, tenant.commander_credential)
        wrong_ticket = _admitted_ticket(cli, base_url, tenant, "R2426-wrong")
        wrong_revision = dict(revision)
        wrong_revision["workflow_digest"] = "sha256:" + "f" * 64
        wrong_status, wrong = _run(
            cli,
            base_url,
            tenant.commander_credential,
            _explicit_start(wrong_ticket, wrong_revision),
        )

    assert _result(exact)["workflow_ref"] == revision["workflow_ref"]
    assert wrong_status == EXIT_PERMANENT
    assert wrong["state"] == "quarantined"
    assert _result(wrong)["code"] == "workflow-pin-mismatch"


def test_cli_accepts_explicit_proof_digests_and_refuses_a_wrong_one(
    tenant: TenantFixture,
    tmp_path: Path,
    installed_ctowerctl: Path,
) -> None:
    with (
        _InstalledCli(tmp_path, installed_ctowerctl) as cli,
        running_api(tenant.database.runtime_dsn) as base_url,
    ):
        proof_ticket, workflow_ref, _ = _begin(cli, base_url, tenant, "R2426-explicit-proof")
        frozen = _reach_verification(cli, base_url, tenant, proof_ticket, workflow_ref)
        candidate_digest = cast(str, _result(frozen)["candidate_digest"])
        derived = _pending(
            cli,
            base_url,
            tenant.commander_credential,
            _ticket_command(
                "evidence",
                "add",
                proof_ticket,
                "--expected-version",
                "1",
                "--evidence-id",
                str(uuid4()),
                "--content",
                "explicit proof evidence",
            ),
        )
        _accept(tenant)
        _drain(cli, base_url, tenant.commander_credential)
        artifact_digest = cast(str, _result(derived)["artifact_digest"])
        explicit, wrong_status, wrong = _explicit_proof_attempts(
            cli,
            base_url,
            tenant,
            proof_ticket,
            candidate_digest,
            artifact_digest,
        )

    _assert_explicit_proof(explicit, wrong_status, wrong, candidate_digest, artifact_digest)


def _assert_explicit_proof(
    explicit: dict[str, object],
    wrong_status: int,
    wrong: dict[str, object],
    candidate_digest: str,
    artifact_digest: str,
) -> None:
    explicit_result, wrong_result = _result(explicit), _result(wrong)
    assert (
        explicit_result["candidate_digest"],
        explicit_result["artifact_digest"],
    ) == (candidate_digest, artifact_digest)
    assert (wrong_status, wrong["state"], wrong_result["code"]) == (
        EXIT_PERMANENT,
        "quarantined",
        "proof-evidence-digest-mismatch",
    )


def _explicit_proof_attempts(
    cli: _InstalledCli,
    base_url: str,
    tenant: TenantFixture,
    ticket_id: str,
    candidate_digest: str,
    artifact_digest: str,
) -> tuple[dict[str, object], int, dict[str, object]]:
    explicit = _pending(
        cli,
        base_url,
        tenant.commander_credential,
        _explicit_evidence_command(ticket_id, "2", candidate_digest, artifact_digest),
    )
    _accept(tenant)
    _drain(cli, base_url, tenant.commander_credential)
    wrong_status, wrong = _run(
        cli,
        base_url,
        tenant.commander_credential,
        _explicit_evidence_command(ticket_id, "3", candidate_digest, "sha256:" + "f" * 64),
    )
    return explicit, wrong_status, wrong


def _explicit_evidence_command(
    ticket_id: str,
    expected_version: str,
    candidate_digest: str,
    artifact_digest: str,
) -> list[str]:
    return _ticket_command(
        "evidence",
        "add",
        ticket_id,
        "--expected-version",
        expected_version,
        "--evidence-id",
        str(uuid4()),
        "--candidate-digest",
        candidate_digest,
        "--artifact-digest",
        artifact_digest,
        "--content",
        "explicit proof evidence",
    )


class _InstalledCli:
    """Keep one isolated Secret Service alive across installed CLI invocations."""

    def __init__(self, state_root: Path, executable: Path) -> None:
        self._state_root = state_root
        self._executable = executable
        self._process: subprocess.Popen[str] | None = None

    def __enter__(self) -> Self:
        environment = os.environ.copy()
        environment["XDG_STATE_HOME"] = str(self._state_root / "state")
        self._process = subprocess.Popen(  # noqa: S603 - fixed repository harness
            (
                sys.executable,
                str(_SECRET_SERVICE_LAUNCHER),
                str(_CLI_BROKER),
                str(self._executable),
            ),
            cwd=_ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return self

    def __exit__(self, *_: object) -> None:
        process = self._require_process()
        if process.poll() is not None:
            stderr = cast(IO[str], process.stderr).read()
            raise AssertionError(f"installed CLI broker exited early: {stderr}")
        stdin = cast(IO[str], process.stdin)
        stdout = cast(IO[str], process.stdout)
        stdin.write("null\n")
        stdin.flush()
        response = json.loads(stdout.readline())
        assert response == {"stopped": True}
        status = process.wait(timeout=30)
        stderr = cast(IO[str], process.stderr).read()
        assert status == 0, stderr

    def run(
        self,
        base_url: str,
        credential: str,
        arguments: list[str],
    ) -> tuple[int, str, str]:
        process = self._require_process()
        stdin = cast(IO[str], process.stdin)
        stdout = cast(IO[str], process.stdout)
        stdin.write(
            json.dumps(
                {
                    "arguments": arguments,
                    "base_url": base_url,
                    "credential": credential,
                }
            )
            + "\n"
        )
        stdin.flush()
        response = cast(dict[str, object], json.loads(stdout.readline()))
        return (
            cast(int, response["status"]),
            cast(str, response["stdout"]),
            cast(str, response["stderr"]),
        )

    def _require_process(self) -> subprocess.Popen[str]:
        if self._process is None:
            raise RuntimeError("installed CLI broker is not running")
        return self._process


@pytest.fixture(scope="module")
def installed_ctowerctl(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace = tmp_path_factory.mktemp("workflow-cli-installed")
    return install_ctowerctl(workspace)


def _begin(
    cli: _InstalledCli,
    base_url: str,
    tenant: TenantFixture,
    source_ref: str,
) -> tuple[str, str, dict[str, object]]:
    discovery = _success(cli, base_url, ["ticket", "workflow", "list"])
    revisions = cast(list[dict[str, object]], discovery["revisions"])
    workflow_ref = cast(str, revisions[0]["workflow_ref"])
    ticket_id = _admitted_ticket(cli, base_url, tenant, source_ref)
    started = _pending(
        cli,
        base_url,
        tenant.commander_credential,
        _ticket_command("workflow", "start", ticket_id),
    )
    _accept(tenant)
    return ticket_id, workflow_ref, started


def _admitted_ticket(
    cli: _InstalledCli,
    base_url: str,
    tenant: TenantFixture,
    source_ref: str,
) -> str:
    created = _pending(
        cli,
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
    created_ticket = cast(dict[str, object], _result(created)["ticket"])
    ticket_id = cast(str, created_ticket["ticket_id"])
    _accept(tenant)
    _pending(
        cli,
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
    cli: _InstalledCli,
    base_url: str,
    tenant: TenantFixture,
    ticket_id: str,
    workflow_ref: str,
) -> dict[str, object]:
    _pending(
        cli,
        base_url,
        tenant.commander_credential,
        _transition(ticket_id, workflow_ref, 1, "capture", "frame"),
    )
    _accept(tenant)
    frozen = _pending(
        cli,
        base_url,
        tenant.commander_credential,
        _ticket_command(
            "criteria",
            "freeze",
            ticket_id,
            "--expected-version",
            "0",
            "--candidate-content",
            "workflow cli candidate",
        ),
    )
    _accept(tenant)
    _pending(
        cli,
        base_url,
        tenant.commander_credential,
        _transition(ticket_id, workflow_ref, 2, "frame", "verify"),
    )
    _accept(tenant)
    return frozen


def _prove(
    cli: _InstalledCli,
    base_url: str,
    tenant: TenantFixture,
    ticket_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    evidence = _pending(
        cli,
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
            "--content",
            "workflow cli evidence",
        ),
    )
    _accept(tenant)
    _drain(cli, base_url, tenant.commander_credential)
    verdict = _pending(
        cli,
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
            "--decision",
            "pass",
        ),
    )
    _accept(tenant)
    _drain(cli, base_url, tenant.operator_credential)
    return evidence, verdict


def _finish(
    cli: _InstalledCli,
    base_url: str,
    tenant: TenantFixture,
    ticket_id: str,
    workflow_ref: str,
) -> dict[str, object]:
    _pending(
        cli,
        base_url,
        tenant.commander_credential,
        _transition(ticket_id, workflow_ref, 3, "verify", "close"),
    )
    _accept(tenant)
    closed = _pending(
        cli,
        base_url,
        tenant.commander_credential,
        _ticket_command("resolve", ticket_id, "--expected-version", "4"),
    )
    _accept(tenant)
    _drain(cli, base_url, tenant.commander_credential)
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


def _pending(
    cli: _InstalledCli,
    base_url: str,
    credential: str,
    arguments: list[str],
) -> dict[str, object]:
    status, payload = _run(cli, base_url, credential, arguments)
    assert status == EXIT_PENDING
    return payload


def _success(
    cli: _InstalledCli,
    base_url: str,
    arguments: list[str],
) -> dict[str, object]:
    status, payload = _run(cli, base_url, "", arguments)
    assert status == 0
    return payload


def _drain(cli: _InstalledCli, base_url: str, credential: str) -> None:
    status, _ = _run(cli, base_url, credential, ["spool", "drain"])
    assert status == 0


def _run(
    cli: _InstalledCli,
    base_url: str,
    credential: str,
    arguments: list[str],
) -> tuple[int, dict[str, object]]:
    status, stdout, stderr = cli.run(base_url, credential, arguments)
    assert stderr == ""
    return status, cast(dict[str, object], json.loads(stdout))


def _result(payload: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], payload["result"])


def _accept(tenant: TenantFixture) -> None:
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
