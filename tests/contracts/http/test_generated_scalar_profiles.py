"""Raw-response scalar parity through both actual generated clients."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ctower_client import (
    CtowerProblemError,
    IntakeSubmitRequest,
    Problem,
    SourceReference,
)

from ._generated_client_runtime import (
    compile_typescript_client,
    node_executable,
    python_client,
    run_command,
)

__all__: tuple[str, ...] = ()

UUID = "018f7a40-1234-7abc-8def-1234567890ab"
SAFE_MAXIMUM = 9_007_199_254_740_991
PROBLEM_STATUS = 409
POSITIVE_URIS = (
    "HTTPS://CTOWER.DEV:443/problems/version-conflict?source=%2Fwire#Exact",
    "https://ctower.dev/problems/version-conflict",
    "https://ctower.dev:",
    "https://ctower.dev:0",
    "https://ctower.dev:00080",
    "https://[::1]",
    "https://[::1]:",
    "https://[::1]:00080",
    "https://ctower.dev/%2fwire?x=%2F#Case",
    "mailto:ops@ctower.dev",
    "urn:ctower:problem:version-conflict",
)
NEGATIVE_URIS = (
    "not-an-absolute-uri",
    "/relative/problem",
    "1https://ctower.dev/problem",
    "https://",
    "https://:",
    "https://:80",
    "https://ctower.dev:x",
    "https://ctower.dev:+80",
    "https://[]:",
    "https://ctower.dev/%",
    "https://ctower.dev/%0",
    "https://ctower.dev/%GG",
    "https://ctower.dev\\evil",
    " https://ctower.dev/problems/conflict",
    "https://ctower.dev/problems/conflict ",
    "https://ctower.dev\t/problems/conflict",
    "https://ctower.dev\r@evil.com",
    "https://ctower.dev\n@evil.com",
    "https://ctower.dev/\x00",
    "https://ctower.dev/\x7f",
    "https://münich.example/problem",
)
INVALID_INTEGER_TOKENS = (
    "0",
    "9007199254740992",
    "9007199254740993",
    "1.1",
    "9007199254740990.5",
    "9007199254740991.1",
    "1.0",
    "1e0",
    "1E+0",
    "10e-1",
    "1.5e1",
)
MALFORMED_NUMBER_TOKENS = ("01", "+1", "--1", "NaN", "Infinity")
MALFORMED_TITLE_TOKENS = ('"bad\\x"', '"bad\\u12"', '"unterminated')


@pytest.mark.parametrize(
    ("token", "expected"),
    (
        ("1", 1),
        ("9007199254740990", 9_007_199_254_740_990),
        ("9007199254740991", SAFE_MAXIMUM),
    ),
)
def test_generated_python_accepts_exact_ticket_integer_tokens(
    token: str,
    expected: int,
) -> None:
    client = python_client(_ticket_raw(token), status=200)
    try:
        assert client.get_ticket(uuid4(), project_key="ctower").version == expected
    finally:
        client.close()


@pytest.mark.parametrize("token", INVALID_INTEGER_TOKENS)
def test_generated_python_rejects_inexact_or_out_of_range_ticket_tokens(
    token: str,
) -> None:
    client = python_client(_ticket_raw(token), status=200)
    try:
        with pytest.raises(ValidationError):
            client.get_ticket(uuid4(), project_key="ctower")
    finally:
        client.close()


def test_generated_python_problem_integer_tokens_and_status_bounds() -> None:
    for token in ("0", "-0"):
        client = python_client(_problem_raw(current_version=token), status=409, problem=True)
        try:
            with pytest.raises(CtowerProblemError) as raised:
                client.submit_intake(_request(), command_id=uuid4())
            problem = cast(Problem, raised.value.problem)
            current = problem.current_version
            assert type(current) is int and current == 0
            assert problem.status == PROBLEM_STATUS
        finally:
            client.close()
    for token in ("399", "600"):
        client = python_client(_problem_raw(status=token), status=409, problem=True)
        try:
            with pytest.raises(ValidationError):
                client.submit_intake(_request(), command_id=uuid4())
        finally:
            client.close()


@pytest.mark.parametrize(
    ("token", "expected"),
    (("0", 0), ("8", 8), ("-1", None), ("9", None)),
)
def test_generated_python_enforces_synthetic_attempt_bounds(
    token: str,
    expected: int | None,
) -> None:
    client = python_client(_synthetic_raw(token), status=200)
    try:
        if expected is None:
            with pytest.raises(ValidationError):
                client.get_synthetic_workflow_run(uuid4())
        else:
            assert client.get_synthetic_workflow_run(uuid4()).attempt_count == expected
    finally:
        client.close()


@pytest.mark.parametrize("token", MALFORMED_NUMBER_TOKENS)
def test_generated_python_rejects_malformed_number_tokens_before_return(token: str) -> None:
    client = python_client(_ticket_raw(token), status=200)
    try:
        with pytest.raises(ValidationError):
            client.get_ticket(uuid4(), project_key="ctower")
    finally:
        client.close()


def test_generated_python_rejects_unescaped_json_newline_before_return() -> None:
    raw = _ticket_raw("1").replace("Ticket resource", "Ticket\nresource")
    client = python_client(raw, status=200)
    try:
        with pytest.raises(ValidationError):
            client.get_ticket(uuid4(), project_key="ctower")
    finally:
        client.close()


@pytest.mark.parametrize("title_token", MALFORMED_TITLE_TOKENS)
def test_generated_python_rejects_malformed_json_strings(title_token: str) -> None:
    raw = _ticket_raw("1").replace(json.dumps("Ticket resource"), title_token)
    client = python_client(raw, status=200)
    try:
        with pytest.raises(ValidationError):
            client.get_ticket(uuid4(), project_key="ctower")
    finally:
        client.close()


def test_generated_python_preserves_last_duplicate_object_member() -> None:
    client = python_client(_ticket_with_duplicate_versions("0", "1"), status=200)
    try:
        assert client.get_ticket(uuid4(), project_key="ctower").version == 1
    finally:
        client.close()
    client = python_client(_ticket_with_duplicate_versions("1", "0"), status=200)
    try:
        with pytest.raises(ValidationError):
            client.get_ticket(uuid4(), project_key="ctower")
    finally:
        client.close()


@pytest.mark.parametrize("uri", POSITIVE_URIS)
def test_generated_python_preserves_absolute_uri_exactly(uri: str) -> None:
    client = python_client(_problem_raw(uri=uri), status=409, problem=True)
    try:
        with pytest.raises(CtowerProblemError) as raised:
            client.submit_intake(_request(), command_id=uuid4())
        assert cast(Problem, raised.value.problem).type_uri == uri
    finally:
        client.close()


@pytest.mark.parametrize("uri", NEGATIVE_URIS)
def test_generated_python_rejects_invalid_uri_before_typed_problem(uri: str) -> None:
    client = python_client(_problem_raw(uri=uri), status=409, problem=True)
    try:
        with pytest.raises(ValidationError):
            client.submit_intake(_request(), command_id=uuid4())
    finally:
        client.close()


@pytest.mark.parametrize("zero", ("\u0660", "\u06f0", "\u0966", "\uff10"))
def test_generated_python_rejects_non_ascii_rfc3339_digit_families(zero: str) -> None:
    timestamp = "2026-07-25T20:00:00Z".translate(
        str.maketrans("0123456789", "".join(chr(ord(zero) + index) for index in range(10)))
    )
    client = python_client(_ticket_raw("1", created_at=timestamp), status=200)
    try:
        with pytest.raises(ValidationError):
            client.get_ticket(uuid4(), project_key="ctower")
    finally:
        client.close()


def test_generated_typescript_enforces_full_raw_scalar_matrix(tmp_path: Path) -> None:
    compile_typescript_client(tmp_path)
    runner = tmp_path / "scalar-profiles.mjs"
    runner.write_text(_typescript_runner(), encoding="utf-8")

    completed = run_command((node_executable(), str(runner)), cwd=tmp_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "typescript scalar profiles: passed"


def _request() -> IntakeSubmitRequest:
    return IntakeSubmitRequest(
        content="scalar profile response",
        project_key="ctower",
        source=SourceReference(kind="test", ref=f"scalar:{uuid4()}"),
    )


def _ticket_raw(token: str, *, created_at: str = "2026-07-25T20:00:00Z") -> str:
    return _raw_payload(
        {
            "created_at": created_at,
            "custodian_id": UUID,
            "display_key": "CTW-4",
            "durability_state": "accepted",
            "priority": "P2",
            "source": {"kind": "test", "ref": "generated:ticket"},
            "ticket_id": UUID,
            "title": "Ticket resource",
            "version": "__VERSION_TOKEN__",
        },
        {"__VERSION_TOKEN__": token},
    )


def _problem_raw(
    *,
    current_version: str = "0",
    status: str = "409",
    uri: str = POSITIVE_URIS[0],
) -> str:
    return _raw_payload(
        {
            "code": "version-conflict",
            "command_id": UUID,
            "current_version": "__CURRENT_VERSION_TOKEN__",
            "detail": "The expected version is stale.",
            "status": "__STATUS_TOKEN__",
            "title": "Version conflict",
            "type": uri,
        },
        {
            "__CURRENT_VERSION_TOKEN__": current_version,
            "__STATUS_TOKEN__": status,
        },
    )


def _synthetic_raw(token: str) -> str:
    return _raw_payload(
        {
            "attempt_count": "__ATTEMPT_TOKEN__",
            "completed_at": None,
            "created_at": "2026-07-25T20:00:00Z",
            "detail_code": None,
            "job_id": UUID,
            "lifecycle_facts": [],
            "run_id": UUID,
            "state": "pending",
            "ticket_id": None,
            "workflow_ref": "ctower.trust-spine-four-stage@1",
        },
        {"__ATTEMPT_TOKEN__": token},
    )


def _raw_payload(payload: object, tokens: dict[str, str]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for marker, token in tokens.items():
        quoted = json.dumps(marker)
        assert rendered.count(quoted) == 1
        rendered = rendered.replace(quoted, token)
    return rendered


def _ticket_with_duplicate_versions(first: str, last: str) -> str:
    rendered = _ticket_raw(first)
    field = f'"version":{first}'
    assert rendered.count(field) == 1
    return rendered.replace(field, f'{field},"version":{last}')


def _non_ascii_timestamps() -> list[str]:
    timestamps: list[str] = []
    for zero in ("\u0660", "\u06f0", "\u0966", "\uff10"):
        table = str.maketrans(
            "0123456789",
            "".join(chr(ord(zero) + index) for index in range(10)),
        )
        timestamps.append("2026-07-25T20:00:00Z".translate(table))
    return timestamps


def _typescript_runner() -> str:
    accepted_tickets = [
        (_ticket_raw("1"), 1),
        (_ticket_raw("9007199254740990"), 9_007_199_254_740_990),
        (_ticket_raw("9007199254740991"), SAFE_MAXIMUM),
        (_ticket_with_duplicate_versions("0", "1"), 1),
    ]
    rejected_tickets = [
        *(_ticket_raw(token) for token in INVALID_INTEGER_TOKENS),
        _ticket_with_duplicate_versions("1", "0"),
    ]
    malformed = [
        *(_ticket_raw(token) for token in MALFORMED_NUMBER_TOKENS),
        _ticket_raw("1").replace("Ticket resource", "Ticket\nresource"),
        *(
            _ticket_raw("1").replace(json.dumps("Ticket resource"), token)
            for token in MALFORMED_TITLE_TOKENS
        ),
    ]
    problems = [(_problem_raw(current_version=token), 0) for token in ("0", "-0")]
    invalid_problem_statuses = [_problem_raw(status=token) for token in ("399", "600")]
    accepted_synthetic = [(_synthetic_raw(token), int(token)) for token in ("0", "8")]
    rejected_synthetic = [_synthetic_raw(token) for token in ("-1", "9")]
    positive_uris = [(_problem_raw(uri=uri), uri) for uri in POSITIVE_URIS]
    negative_uris = [_problem_raw(uri=uri) for uri in NEGATIVE_URIS]
    invalid_timestamps = [_ticket_raw("1", created_at=value) for value in _non_ascii_timestamps()]
    vectors = {
        "acceptedTickets": accepted_tickets,
        "rejectedTickets": rejected_tickets,
        "malformed": malformed,
        "malformedProblems": ("{", _problem_raw().replace('"title":', '"title":NaN,')),
        "problems": problems,
        "invalidProblemStatuses": invalid_problem_statuses,
        "acceptedSynthetic": accepted_synthetic,
        "rejectedSynthetic": rejected_synthetic,
        "positiveUris": positive_uris,
        "negativeUris": negative_uris,
        "invalidTimestamps": invalid_timestamps,
    }
    return f"""
import {{ CtowerClient, CtowerProblemError }} from "./index.js";

const vectors = {json.dumps(vectors, ensure_ascii=False, separators=(",", ":"))};
const responses = [];
const client = new CtowerClient({{
  baseUrl: "http://contract.invalid",
  telemetry: () => ({{}}),
  fetch: async () => {{
    const next = responses.shift();
    if (next === undefined) throw new Error("response queue exhausted");
    return new Response(next.raw, {{
      status: next.status,
      headers: {{
        "content-type": next.problem ? "application/problem+json" : "application/json",
      }},
    }});
  }},
}});
const enqueue = (raw, status, problem = false) => responses.push({{raw, status, problem}});
const ticket = () => client.getTicket({{ticketId: "{UUID}", projectKey: "ctower"}});
const synthetic = () => client.getSyntheticWorkflowRun({{runId: "{UUID}"}});
const submit = () => client.submitIntake({{
  IdempotencyKey: "{UUID}",
  body: {{
    content: "runtime",
    project_key: "ctower",
    source: {{kind: "test", ref: "scalar"}},
  }},
}});
async function expectTypeError(raw, operation, status = 200, problem = false) {{
  enqueue(raw, status, problem);
  try {{
    await operation();
  }} catch (error) {{
    if (error instanceof TypeError) return;
    throw error;
  }}
  throw new Error(`invalid scalar response accepted: ${{raw}}`);
}}
async function expectSyntaxError(raw, operation, status = 200, problem = false) {{
  enqueue(raw, status, problem);
  try {{
    await operation();
  }} catch (error) {{
    if (error instanceof SyntaxError) return;
    throw error;
  }}
  throw new Error(`malformed JSON response accepted: ${{raw}}`);
}}
async function acceptProblem(raw, expectedCurrent, expectedUri) {{
  enqueue(raw, 409, true);
  try {{
    await submit();
  }} catch (error) {{
    if (!(error instanceof CtowerProblemError)) throw error;
    if (!Object.is(error.problem.current_version, expectedCurrent)) {{
      throw new Error("Problem.current_version changed");
    }}
    if (expectedUri !== undefined && error.problem.type !== expectedUri) {{
      throw new Error("Problem.type was normalized");
    }}
    return;
  }}
  throw new Error("valid Problem returned as success");
}}

for (const [raw, expected] of vectors.acceptedTickets) {{
  enqueue(raw, 200);
  if (!Object.is((await ticket()).version, expected)) throw new Error("integer changed");
}}
for (const raw of vectors.rejectedTickets) await expectTypeError(raw, ticket);
for (const raw of vectors.malformed) await expectSyntaxError(raw, ticket);
for (const raw of vectors.malformedProblems) {{
  await expectSyntaxError(raw, submit, 409, true);
}}
for (const [raw, expected] of vectors.problems) await acceptProblem(raw, expected);
for (const raw of vectors.invalidProblemStatuses) {{
  await expectTypeError(raw, submit, 409, true);
}}
for (const [raw, expected] of vectors.acceptedSynthetic) {{
  enqueue(raw, 200);
  if (!Object.is((await synthetic()).attempt_count, expected)) {{
    throw new Error("attempt_count changed");
  }}
}}
for (const raw of vectors.rejectedSynthetic) await expectTypeError(raw, synthetic);
for (const [raw, uri] of vectors.positiveUris) await acceptProblem(raw, 0, uri);
for (const raw of vectors.negativeUris) await expectTypeError(raw, submit, 409, true);
for (const raw of vectors.invalidTimestamps) await expectTypeError(raw, ticket);

console.log("typescript scalar profiles: passed");
""".lstrip()
