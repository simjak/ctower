"""Runtime response-boundary parity for the generated Python and TypeScript clients."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from ctower_client import (
    CtowerClient,
    CtowerProblemError,
    IntakeSubmitRequest,
    Problem,
    SourceReference,
)

from ._generated_client_runtime import (
    compile_typescript_client,
    node_executable,
    run_command,
)

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
UUID = "018f7a40-1234-7abc-8def-1234567890ab"
LEAP_YEAR = 2024
HTTP_FORBIDDEN = 403
JSON_SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991
JSON_UNSAFE_INTEGER = 9_007_199_254_740_993


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
    assert cast(Problem, raised.value.problem).type_uri == valid["type"]
    client.close()

    invalid_payloads: tuple[object, ...] = (
        [],
        {**valid, "unknown": "field"},
        {**valid, "code": "not-a-problem"},
        {**valid, "status": 399},
        {**valid, "type": "not-an-absolute-uri"},
    )
    for invalid in invalid_payloads:
        client = _python_client(invalid, status=409, problem=True)
        with pytest.raises(ValidationError):
            client.submit_intake(_python_request(), command_id=uuid4())
        client.close()

    mismatch = _python_client({**valid, "status": 404}, status=409, problem=True)
    with pytest.raises(ValueError, match="Problem status does not match"):
        mismatch.submit_intake(_python_request(), command_id=uuid4())
    mismatch.close()


def test_generated_python_client_declares_project_scope_refusals() -> None:
    problem = {
        **_problem(),
        "code": "project-scope-denied",
        "detail": "The authenticated project seat cannot reach this project.",
        "status": 403,
        "title": "Project scope denied",
    }

    board_client = _python_client(problem, status=403, problem=True)
    with pytest.raises(CtowerProblemError) as board_raised:
        board_client.get_board(project_key="ctower")
    assert cast(Problem, board_raised.value.problem).status == HTTP_FORBIDDEN
    board_client.close()

    delivery_client = _python_client(problem, status=403, problem=True)
    with pytest.raises(CtowerProblemError) as delivery_raised:
        delivery_client.get_project_delivery("ctower")
    assert cast(Problem, delivery_raised.value.problem).status == HTTP_FORBIDDEN
    delivery_client.close()


def test_generated_python_client_rejects_undeclared_success_status() -> None:
    client = _python_client(_intake_result(), status=299)
    with pytest.raises(httpx.HTTPStatusError, match="undeclared success status"):
        client.submit_intake(_python_request(), command_id=uuid4())
    client.close()


@pytest.mark.parametrize(
    ("timestamp", "accepted"),
    (
        ("2024-02-29T23:59:59.123456+23:59", True),
        ("2023-02-29T20:00:00Z", False),
        ("2026-07-25T20:00:00", False),
        ("2026-07-25T20:00:00+24:00", False),
        ("2026-07-25T20:00:60Z", False),
        ("2026-07-25T20:00:00-00:00", False),
        (
            "\u0662\u0660\u0662\u0666-\u0660\u0667-\u0662\u0665"
            "T\u0662\u0660:\u0660\u0660:\u0660\u0660Z",
            False,
        ),
    ),
)
def test_generated_python_client_enforces_authored_rfc3339_profile(
    timestamp: str,
    *,
    accepted: bool,
) -> None:
    client = _python_client(_ticket(timestamp), status=200)
    if accepted:
        assert client.get_ticket(uuid4(), project_key="ctower").created_at.year == LEAP_YEAR
    else:
        with pytest.raises(ValidationError):
            client.get_ticket(uuid4(), project_key="ctower")
    client.close()


def test_generated_python_client_enforces_lossless_json_integers() -> None:
    client = _python_client(
        _ticket("2026-07-25T20:00:00Z", version=JSON_SAFE_INTEGER_MAXIMUM), status=200
    )
    assert client.get_ticket(uuid4(), project_key="ctower").version == JSON_SAFE_INTEGER_MAXIMUM
    client.close()

    client = _python_client(
        _ticket("2026-07-25T20:00:00Z", version=JSON_UNSAFE_INTEGER), status=200
    )
    with pytest.raises(ValidationError):
        client.get_ticket(uuid4(), project_key="ctower")
    client.close()


def test_generated_typescript_client_runtime_validates_success_and_problem_vectors(
    tmp_path: Path,
) -> None:
    compile_typescript_client(tmp_path)
    runner = tmp_path / "runtime-boundary.mjs"
    runner.write_text(_typescript_runner(), encoding="utf-8")
    completed = run_command((node_executable(), str(runner)), cwd=tmp_path)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "typescript response vectors: passed"


def test_typescript_runtime_fails_closed_without_node_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(RuntimeError, match=r"Node\.js is required"):
        node_executable()


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
        "request_id": None,
        "request_number": None,
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
        "type": "HTTPS://CTOWER.DEV:443/problems/version-conflict?source=%2Fwire#Exact",
    }


def _ticket(created_at: str, *, version: int = 1) -> dict[str, object]:
    return {
        "created_at": created_at,
        "custodian_id": UUID,
        "durability_state": "accepted",
        "priority": "P2",
        "source": {"kind": "test", "ref": "generated:ticket"},
        "ticket_id": UUID,
        "title": "Ticket resource",
        "version": version,
    }


def _typescript_runner() -> str:
    result = json.dumps(_intake_result(), sort_keys=True)
    problem = json.dumps(_problem(), sort_keys=True)
    ticket = json.dumps(_ticket("2024-02-29T23:59:59.123456+23:59"), sort_keys=True)
    unsafe_ticket = json.dumps(
        _ticket("2026-07-25T20:00:00Z", version=JSON_UNSAFE_INTEGER),
        sort_keys=True,
    )
    successes, problems = _authored_response_inventories()
    success_inventory = json.dumps(successes, sort_keys=True)
    problem_inventory = json.dumps(problems, sort_keys=True)
    return f"""
import {{
  CtowerClient,
  CtowerProblemError,
  OPERATION_PROBLEM_MODELS,
  OPERATION_SUCCESS_MODELS,
}} from "./index.js";

const valid = {result};
const problem = {problem};
const ticket = {ticket};
const unsafeTicketJson = {json.dumps(unsafe_ticket)};
const expectedSuccesses = {success_inventory};
const expectedProblems = {problem_inventory};
const canonical = (value) => {{
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {{
    return Object.fromEntries(
      Object.entries(value).sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nested]) => [key, canonical(nested)]),
    );
  }}
  return value;
}};
if (
  JSON.stringify(canonical(OPERATION_SUCCESS_MODELS)) !==
  JSON.stringify(canonical(expectedSuccesses))
) throw new Error("generated success inventory diverges from OpenAPI");
if (
  JSON.stringify(canonical(OPERATION_PROBLEM_MODELS)) !==
  JSON.stringify(canonical(expectedProblems))
) throw new Error("generated Problem inventory diverges from OpenAPI");
const responses = [];
const client = new CtowerClient({{
  baseUrl: "http://contract.invalid",
  telemetry: () => ({{}}),
  fetch: async () => {{
    const next = responses.shift();
    if (next === undefined) throw new Error("response queue exhausted");
    return new Response(next.raw ?? JSON.stringify(next.payload), {{
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
const getTicket = () => client.getTicket({{ticketId: "{UUID}", projectKey: "ctower"}});
const getBoard = () => client.getBoard({{projectKey: "ctower"}});
const getProjectDelivery = () => client.getProjectDelivery({{projectKey: "ctower"}});
async function expectTypeError(
  payload,
  operation = submit,
  status = 202,
  isProblem = false,
  raw = false,
) {{
  responses.push(
    raw
      ? {{raw: payload, status, problem: isProblem}}
      : {{payload, status, problem: isProblem}},
  );
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
responses.push({{payload: ticket, status: 200, problem: false}});
if ((await getTicket()).version !== 1) throw new Error("valid leap-day timestamp rejected");
responses.push({{
  payload: {{...ticket, version: {JSON_SAFE_INTEGER_MAXIMUM}}},
  status: 200,
  problem: false,
}});
if ((await getTicket()).version !== {JSON_SAFE_INTEGER_MAXIMUM}) {{
  throw new Error("safe integer boundary rejected");
}}

await expectTypeError([]);
await expectTypeError(valid, submit, 299);
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
await expectTypeError({{...ticket, created_at: "2023-02-29T20:00:00Z"}}, getTicket, 200);
await expectTypeError({{...ticket, created_at: "2026-07-25T20:00:00"}}, getTicket, 200);
await expectTypeError({{...ticket, created_at: "2026-07-25T20:00:00+24:00"}}, getTicket, 200);
await expectTypeError({{...ticket, created_at: "2026-07-25T20:00:60Z"}}, getTicket, 200);
await expectTypeError({{...ticket, created_at: "2026-07-25T20:00:00-00:00"}}, getTicket, 200);
await expectTypeError({{
  ...ticket,
  created_at: "\u0662\u0660\u0662\u0666-\u0660\u0667-\u0662\u0665"
    + "T\u0662\u0660:\u0660\u0660:\u0660\u0660Z",
}}, getTicket, 200);
await expectTypeError(unsafeTicketJson, getTicket, 200, false, true);

const scopeProblem = {{
  ...problem,
  code: "project-scope-denied",
  detail: "The authenticated project seat cannot reach this project.",
  status: 403,
  title: "Project scope denied",
}};
async function expectProjectScopeRefusal(operation) {{
  responses.push({{payload: scopeProblem, status: 403, problem: true}});
  try {{
    await operation();
    throw new Error("project scope refusal was returned as success");
  }} catch (error) {{
    if (!(error instanceof CtowerProblemError)) throw error;
    if (error.problem.status !== 403) throw new Error("project scope status was not preserved");
  }}
}}
await expectProjectScopeRefusal(getBoard);
await expectProjectScopeRefusal(getProjectDelivery);

responses.push({{payload: problem, status: 409, problem: true}});
try {{
  await submit();
  throw new Error("valid problem was returned as success");
}} catch (error) {{
  if (!(error instanceof CtowerProblemError)) throw error;
  if (error.problem.type !== problem.type) throw new Error("valid absolute URI was normalized");
}}
await expectTypeError([], submit, 409, true);
await expectTypeError({{...problem, unknown: "field"}}, submit, 409, true);
await expectTypeError({{...problem, code: "not-a-problem"}}, submit, 409, true);
await expectTypeError({{...problem, status: 399}}, submit, 409, true);
await expectTypeError({{...problem, type: "not-an-absolute-uri"}}, submit, 409, true);
await expectTypeError({{...problem, status: 404}}, submit, 409, true);
await expectTypeError(problem, submit, 418, true);

console.log("typescript response vectors: passed");
""".lstrip()


def _authored_response_inventories() -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
]:
    document = cast(
        dict[str, object],
        json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8")),
    )
    paths = cast(dict[str, dict[str, object]], document["paths"])
    components = cast(dict[str, object], document["components"])
    definitions = cast(dict[str, dict[str, object]], components["responses"])
    successes: dict[str, dict[str, str]] = {}
    problems: dict[str, dict[str, str]] = {}
    for path_item in paths.values():
        for method, value in path_item.items():
            if method not in {"get", "post"}:
                continue
            operation = cast(dict[str, object], value)
            if operation.get("x-ctower-generated-client", True) is False:
                continue
            operation_id = cast(str, operation["operationId"])
            successes[operation_id] = {}
            problems[operation_id] = {}
            responses = cast(dict[str, dict[str, object]], operation["responses"])
            for status, response_value in responses.items():
                response = response_value
                reference = response.get("$ref")
                if isinstance(reference, str):
                    response = definitions[reference.rsplit("/", 1)[-1]]
                content = cast(dict[str, dict[str, object]], response["content"])
                media_type = (
                    "application/json" if status.startswith("2") else "application/problem+json"
                )
                schema = cast(dict[str, str], content[media_type]["schema"])
                model = schema["$ref"].rsplit("/", 1)[-1]
                target = successes if status.startswith("2") else problems
                target[operation_id][status] = model
    return successes, problems
