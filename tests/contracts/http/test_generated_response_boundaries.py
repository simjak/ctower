"""Runtime response-boundary parity for the generated Python and TypeScript clients."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from ctower_client import (
    CtowerClient,
    CtowerProblemError,
    IntakeSubmitRequest,
    SourceReference,
)

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
TSC = ROOT / "node_modules/typescript/bin/tsc"
UUID = "018f7a40-1234-7abc-8def-1234567890ab"


@pytest.mark.parametrize(
    "invalid",
    (
        [],
        {"malformed": True},
        {"command_id": "not-a-uuid"},
    ),
)
def test_generated_python_client_rejects_malformed_success_payloads(
    invalid: object,
) -> None:
    payload = _intake_result()
    if isinstance(invalid, dict) and "command_id" in invalid:
        payload.update(invalid)
        invalid = payload
    client = _python_client(invalid, status=202)
    with pytest.raises(ValidationError):
        client.submit_intake(_python_request(), command_id=uuid4())
    client.close()


@pytest.mark.parametrize(
    "mutation",
    (
        {"unknown": "field"},
        {"outcome": "not-an-outcome"},
        {"thread_version": 0},
        {"quarantine_reason": 3},
        {
            "created_at": "2026-07-25T20:00:00Z",
            "custodian_id": UUID,
            "durability_state": "accepted",
            "priority": "P2",
            "source": {"kind": "test", "ref": "wrong-operation"},
            "ticket_id": UUID,
            "title": "Ticket resource",
            "version": 1,
        },
    ),
)
def test_generated_python_client_rejects_unknown_invalid_and_wrong_operation(
    mutation: dict[str, object],
) -> None:
    payload = (
        mutation
        if "created_at" in mutation
        else {
            **_intake_result(),
            **mutation,
        }
    )
    client = _python_client(payload, status=202)
    with pytest.raises(ValidationError):
        client.submit_intake(_python_request(), command_id=uuid4())
    client.close()


def test_generated_python_client_validates_problem_payloads() -> None:
    valid = _problem()
    client = _python_client(valid, status=409, problem=True)
    with pytest.raises(CtowerProblemError) as raised:
        client.submit_intake(_python_request(), command_id=uuid4())
    assert raised.value.problem.code == "version-conflict"
    client.close()

    invalid_payloads: tuple[object, ...] = (
        [],
        {**valid, "unknown": "field"},
        {**valid, "code": "not-a-problem"},
        {**valid, "status": 399},
    )
    for invalid in invalid_payloads:
        client = _python_client(invalid, status=409, problem=True)
        with pytest.raises(ValidationError):
            client.submit_intake(_python_request(), command_id=uuid4())
        client.close()


def test_generated_typescript_client_runtime_validates_success_and_problem_vectors(
    tmp_path: Path,
) -> None:
    _compile_typescript_client(tmp_path)
    runner = tmp_path / "runtime-boundary.mjs"
    runner.write_text(_typescript_runner(), encoding="utf-8")
    completed = _run_command((_node_executable(), str(runner)), cwd=tmp_path)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "typescript response vectors: passed"


def test_typescript_runtime_fails_closed_without_node_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(RuntimeError, match=r"Node\.js is required"):
        _node_executable()


def _python_client(
    payload: object,
    *,
    status: int,
    problem: bool = False,
) -> CtowerClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        content_type = "application/problem+json" if problem else "application/json"
        return httpx.Response(status, headers={"content-type": content_type}, json=payload)

    client = CtowerClient("http://contract.invalid", credential="opaque")
    client._http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://contract.invalid",
    )
    return client


def _python_request() -> IntakeSubmitRequest:
    return IntakeSubmitRequest(
        content="runtime response validation",
        project_key="ctower",
        source=SourceReference(kind="test", ref=f"generated:{uuid4()}"),
    )


def _intake_result() -> dict[str, object]:
    return {
        "command_id": UUID,
        "durability_state": "durability_pending",
        "event_ids": [UUID],
        "inbound_event_id": UUID,
        "outcome": "discussion",
        "project_key": "ctower",
        "quarantine_reason": None,
        "source": {"kind": "test", "ref": "generated:response"},
        "thread_id": UUID,
        "thread_version": 1,
        "ticket_id": None,
        "ticket_version": None,
    }


def _problem() -> dict[str, object]:
    return {
        "code": "version-conflict",
        "command_id": UUID,
        "current_version": 2,
        "detail": "The expected version is stale.",
        "status": 409,
        "title": "Version conflict",
        "type": "https://ctower.dev/problems/version-conflict",
    }


def _compile_typescript_client(target: Path) -> None:
    completed = _run_command(
        (
            _node_executable(),
            str(TSC),
            "--project",
            str(ROOT / "generated/typescript/ctower-client/tsconfig.json"),
            "--noEmit",
            "false",
            "--outDir",
            str(target),
        ),
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    (target / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")


def _node_executable() -> str:
    node = shutil.which("node", path=os.environ.get("PATH"))
    if node is None:
        raise RuntimeError("Node.js is required on PATH for TypeScript runtime vectors")
    return node


def _run_command(
    command: tuple[str, ...],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "CTOWER_TEST_COMMAND": json.dumps(command)}
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            "import json, os; "
            "command = json.loads(os.environ.pop('CTOWER_TEST_COMMAND')); "
            "os.execv(command[0], command)",
        ),
        check=False,
        cwd=cwd,
        capture_output=True,
        env=environment,
        text=True,
        timeout=30,
    )


def _typescript_runner() -> str:
    result = json.dumps(_intake_result(), sort_keys=True)
    problem = json.dumps(_problem(), sort_keys=True)
    return f"""
import {{ CtowerClient, CtowerProblemError }} from "./index.js";

const valid = {result};
const problem = {problem};
const responses = [];
const client = new CtowerClient({{
  baseUrl: "http://contract.invalid",
  telemetry: () => ({{}}),
  fetch: async () => {{
    const next = responses.shift();
    if (next === undefined) throw new Error("response queue exhausted");
    return new Response(JSON.stringify(next.payload), {{
      status: next.status,
      headers: {{"content-type": next.problem ? "application/problem+json" : "application/json"}},
    }});
  }},
}});
const submit = () => client.submitIntake({{
  IdempotencyKey: "{UUID}",
  body: {{content: "runtime", project_key: "ctower", source: {{kind: "test", ref: "runtime"}}}},
}});
const promote = () => client.promoteIntakeEvent({{
  inboundEventId: "{UUID}",
  IdempotencyKey: "{UUID}",
  body: {{expected_thread_version: 1, intent: "create_ticket"}},
}});
async function expectTypeError(payload, operation = submit, status = 202, isProblem = false) {{
  responses.push({{payload, status, problem: isProblem}});
  try {{
    await operation();
  }} catch (error) {{
    if (error instanceof TypeError) return;
    throw error;
  }}
  throw new Error("invalid response was accepted");
}}

responses.push({{payload: valid, status: 202, problem: false}});
if ((await submit()).thread_version !== 1) throw new Error("valid success rejected");
responses.push({{payload: valid, status: 200, problem: false}});
if ((await promote()).outcome !== "discussion") throw new Error("valid promotion rejected");

await expectTypeError([]);
await expectTypeError({{malformed: true}});
await expectTypeError({{...valid, unknown: "field"}});
await expectTypeError({{...valid, command_id: "not-a-uuid"}});
await expectTypeError({{...valid, outcome: "not-an-outcome"}});
await expectTypeError({{...valid, thread_version: 0}});
await expectTypeError({{...valid, quarantine_reason: 3}});
const {{quarantine_reason: omitted, ...missingNullable}} = valid;
void omitted;
await expectTypeError(missingNullable);
await expectTypeError({{
  created_at: "2026-07-25T20:00:00Z",
  custodian_id: "{UUID}",
  durability_state: "accepted",
  priority: "P2",
  source: {{kind: "test", ref: "wrong-operation"}},
  ticket_id: "{UUID}",
  title: "Ticket resource",
  version: 1,
}});
await expectTypeError({{...valid, unknown: "promotion-field"}}, promote, 200);

responses.push({{payload: problem, status: 409, problem: true}});
try {{
  await submit();
  throw new Error("valid problem was returned as success");
}} catch (error) {{
  if (!(error instanceof CtowerProblemError)) throw error;
}}
await expectTypeError([], submit, 409, true);
await expectTypeError({{...problem, unknown: "field"}}, submit, 409, true);
await expectTypeError({{...problem, code: "not-a-problem"}}, submit, 409, true);
await expectTypeError({{...problem, status: 399}}, submit, 409, true);
await expectTypeError(problem, submit, 418, true);

console.log("typescript response vectors: passed");
""".lstrip()
