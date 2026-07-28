"""Recursive free-form JSON parity through both actual generated clients."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Literal, cast

import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML

from ._generated_client_runtime import (
    compile_typescript_client,
    node_executable,
    python_client,
    run_command,
)

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
UUID = "018f7a40-1234-7abc-8def-1234567890ab"
SAFE_MINIMUM = -9_007_199_254_740_991
SAFE_MAXIMUM = 9_007_199_254_740_991
ROUNDED_UNSAFE_FRACTION = 9_007_199_254_740_992.0

ACCEPTED_NUMBERS = (
    ("-9007199254740991", SAFE_MINIMUM, "ordinary"),
    ("0", 0, "ordinary"),
    ("9007199254740991", SAFE_MAXIMUM, "ordinary"),
    ("-0", 0, "ordinary"),
    ("0.1", 0.1, "ordinary"),
    ("1.0", 1.0, "ordinary"),
    ("1e0", 1.0, "ordinary"),
    ("1E+0", 1.0, "ordinary"),
    ("1.5e1", 15.0, "ordinary"),
    ("9007199254740993.0", ROUNDED_UNSAFE_FRACTION, "ordinary"),
    ("-0.0", -0.0, "negative"),
    ("-0e0", -0.0, "negative"),
    ("1e-4000", 0.0, "ordinary"),
    ("-1e-4000", -0.0, "negative"),
)
PROFILE_REJECTIONS = (
    '{"value":-9007199254740992}',
    '{"value":9007199254740992}',
    '{"nested":{"value":9007199254740993}}',
    '{"value":1e309}',
    '{"value":-1e309}',
)
MALFORMED_JSON = (
    '{"value":NaN}',
    '{"value":Infinity}',
    '{"value":-Infinity}',
    '{"value":01}',
    '{"value":+1}',
    '{"value":1e}',
    '{"value":"unterminated}',
    '{"value":"raw\ncontrol"}',
)


def test_generated_python_accepts_exact_current_authored_bundle() -> None:
    client = python_client(_authored_export_raw(), status=200)
    try:
        result = client.export_company_bundle()
    finally:
        client.close()

    numbers = [
        number for resource in result.bundle.resources for number in _numbers(resource.payload)
    ]
    assert numbers == [1, 1, 1, 1]
    assert all(type(number) is int for number in numbers)


def test_generated_python_preserves_recursive_json_primitives_and_containers() -> None:
    payload = _python_payload(
        """{
          "nil": null,
          "flag": true,
          "text": "value",
          "array": [null, false, "nested", {"leaf": [1, 0.5]}],
          "object": {"child": {"ready": true}}
        }"""
    )

    assert payload == {
        "nil": None,
        "flag": True,
        "text": "value",
        "array": [None, False, "nested", {"leaf": [1, 0.5]}],
        "object": {"child": {"ready": True}},
    }
    array = cast(list[object], payload["array"])
    nested = cast(dict[str, object], array[3])
    leaf = cast(list[object], nested["leaf"])
    assert type(leaf[0]) is int
    assert type(leaf[1]) is float


@pytest.mark.parametrize(
    ("token", "expected", "zero_sign"),
    ACCEPTED_NUMBERS,
)
def test_generated_python_enforces_free_form_number_lexemes(
    token: str,
    expected: float,
    zero_sign: Literal["ordinary", "negative"],
) -> None:
    value = _python_payload(f'{{"value":{token}}}')["value"]

    assert type(value) is type(expected)
    assert value == expected
    if type(value) is float and value == 0:
        assert math.copysign(1.0, value) == (-1.0 if zero_sign == "negative" else 1.0)


@pytest.mark.parametrize("payload_raw", PROFILE_REJECTIONS)
def test_generated_python_rejects_unsafe_or_nonfinite_free_form_numbers(
    payload_raw: str,
) -> None:
    client = python_client(_export_raw(payload_raw), status=200)
    try:
        with pytest.raises(ValidationError):
            client.export_company_bundle()
    finally:
        client.close()


@pytest.mark.parametrize("payload_raw", MALFORMED_JSON)
def test_generated_python_rejects_non_json_grammar_before_return(
    payload_raw: str,
) -> None:
    client = python_client(_export_raw(payload_raw), status=200)
    try:
        with pytest.raises(ValidationError):
            client.export_company_bundle()
    finally:
        client.close()


@pytest.mark.parametrize(
    ("payload_raw", "expected"),
    (
        ('{"n":1,"n":2}', 2),
        ('{"n":2,"n":1}', 1),
    ),
)
def test_generated_python_preserves_recursive_last_member_wins(
    payload_raw: str,
    expected: int,
) -> None:
    assert _python_payload(payload_raw)["n"] == expected


@pytest.mark.parametrize(
    "payload_raw",
    (
        '{"n":1,"n":9007199254740992}',
        '{"n":1,"n":1e309}',
    ),
)
def test_generated_python_validates_the_selected_duplicate_member(
    payload_raw: str,
) -> None:
    client = python_client(_export_raw(payload_raw), status=200)
    try:
        with pytest.raises(ValidationError):
            client.export_company_bundle()
    finally:
        client.close()


def test_generated_python_keeps_prototype_like_names_as_dictionary_keys() -> None:
    payload = _python_payload('{"__proto__":{"polluted":true},"constructor":1,"prototype":[2]}')

    assert type(payload) is dict
    assert payload == {
        "__proto__": {"polluted": True},
        "constructor": 1,
        "prototype": [2],
    }


def test_generated_typescript_enforces_the_complete_free_form_matrix(
    tmp_path: Path,
) -> None:
    compile_typescript_client(tmp_path)
    runner = tmp_path / "free-form-json.mjs"
    runner.write_text(_typescript_runner(), encoding="utf-8")

    completed = run_command((node_executable(), str(runner)), cwd=tmp_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "typescript free-form JSON: passed"


def _python_payload(payload_raw: str) -> dict[str, object]:
    client = python_client(_export_raw(payload_raw), status=200)
    try:
        result = client.export_company_bundle()
        return result.bundle.resources[0].payload
    finally:
        client.close()


def _authored_bundle() -> dict[str, object]:
    loaded: object = YAML(typ="safe", pure=True).load(
        (ROOT / "company/company.bundle.yaml").read_text(encoding="utf-8")
    )
    if not isinstance(loaded, dict):
        raise TypeError("authored CompanyBundle must be an object")
    return cast(dict[str, object], loaded)


def _export_envelope(bundle: dict[str, object]) -> dict[str, object]:
    return {
        "active_version": 1,
        "bundle": bundle,
        "bundle_digest": f"sha256:{'2' * 64}",
        "metadata": {
            "activated_at": "2026-07-25T20:00:00Z",
            "actor_principal_id": UUID,
            "checks": [],
            "command_id": UUID,
        },
    }


def _authored_export_raw() -> str:
    bundle = _authored_bundle()
    payload_numbers = [
        number
        for resource in cast(list[dict[str, object]], bundle["resources"])
        for number in _numbers(resource["payload"])
    ]
    assert payload_numbers == [1, 1, 1, 1]
    return json.dumps(_export_envelope(bundle), separators=(",", ":"), sort_keys=True)


def _export_raw(payload_raw: str) -> str:
    authored = _authored_bundle()
    resource = deepcopy(cast(list[dict[str, object]], authored["resources"])[0])
    marker = "__FREE_FORM_JSON__"
    resource["payload"] = marker
    bundle = {
        "assignments": [],
        "company": authored["company"],
        "resources": [resource],
        "schema": authored["schema"],
        "secret_binding_refs": [],
    }
    rendered = json.dumps(_export_envelope(bundle), separators=(",", ":"), sort_keys=True)
    encoded_marker = json.dumps(marker)
    assert rendered.count(encoded_marker) == 1
    return rendered.replace(encoded_marker, payload_raw)


def _numbers(value: object) -> list[float]:
    if type(value) in (int, float):
        return [cast(float, value)]
    if isinstance(value, list | tuple):
        return [number for item in value for number in _numbers(item)]
    if isinstance(value, dict):
        return [number for item in value.values() for number in _numbers(item)]
    return []


def _typescript_runner() -> str:
    accepted_numbers = [
        {
            "raw": _export_raw(f'{{"value":{token}}}'),
            "expected": expected,
            "negativeZero": zero_sign == "negative",
        }
        for token, expected, zero_sign in ACCEPTED_NUMBERS
    ]
    vectors = {
        "authored": _authored_export_raw(),
        "recursive": _export_raw(
            '{"nil":null,"flag":true,"text":"value",'
            '"array":[null,false,"nested",{"leaf":[1,0.5]}],'
            '"object":{"child":{"ready":true}}}'
        ),
        "acceptedNumbers": accepted_numbers,
        "profileRejections": [_export_raw(value) for value in PROFILE_REJECTIONS],
        "malformed": [_export_raw(value) for value in MALFORMED_JSON],
        "duplicates": [
            (_export_raw('{"n":1,"n":2}'), 2),
            (_export_raw('{"n":2,"n":1}'), 1),
        ],
        "selectedDuplicateRejections": [
            _export_raw('{"n":1,"n":9007199254740992}'),
            _export_raw('{"n":1,"n":1e309}'),
        ],
        "prototypeNames": _export_raw(
            '{"__proto__":{"polluted":true},"constructor":1,"prototype":[2]}'
        ),
    }
    return f"""
import {{ CtowerClient }} from "./index.js";

const vectors = {json.dumps(vectors, ensure_ascii=False, separators=(",", ":"))};
const responses = [];
const client = new CtowerClient({{
  baseUrl: "http://contract.invalid",
  telemetry: () => ({{}}),
  fetch: async () => new Response(responses.shift(), {{
    status: 200,
    headers: {{"content-type": "application/json"}},
  }}),
}});
const invoke = async (raw) => {{
  responses.push(raw);
  return client.exportCompanyBundle({{}});
}};
const payload = (result) => result.bundle.resources[0].payload;
async function expectError(raw, ErrorClass) {{
  try {{
    await invoke(raw);
  }} catch (error) {{
    if (error instanceof ErrorClass) return;
    throw error;
  }}
  throw new Error(`invalid free-form response accepted: ${{raw}}`);
}}
function collectPayloadNumbers(value, found = []) {{
  if (typeof value === "number") found.push(value);
  else if (Array.isArray(value)) {{
    for (const item of value) collectPayloadNumbers(item, found);
  }} else if (value !== null && typeof value === "object") {{
    for (const item of Object.values(value)) collectPayloadNumbers(item, found);
  }}
  return found;
}}

const authored = await invoke(vectors.authored);
const authoredNumbers = authored.bundle.resources.flatMap(
  (resource) => collectPayloadNumbers(resource.payload),
);
if (
  authoredNumbers.length !== 4 ||
  !authoredNumbers.every((value) => Object.is(value, 1))
) throw new Error("current authored CompanyBundle numbers changed");

const recursive = payload(await invoke(vectors.recursive));
if (
  recursive.nil !== null ||
  recursive.flag !== true ||
  recursive.text !== "value" ||
  recursive.array[3].leaf[0] !== 1 ||
  recursive.array[3].leaf[1] !== 0.5 ||
  recursive.object.child.ready !== true
) throw new Error("recursive free-form structure changed");

for (const vector of vectors.acceptedNumbers) {{
  const value = payload(await invoke(vector.raw)).value;
  if (!Object.is(value, vector.expected)) {{
    throw new Error(`free-form number changed: ${{vector.raw}}`);
  }}
  if (Object.is(value, -0) !== vector.negativeZero) {{
    throw new Error(`free-form zero sign changed: ${{vector.raw}}`);
  }}
}}
for (const raw of vectors.profileRejections) await expectError(raw, TypeError);
for (const raw of vectors.malformed) await expectError(raw, SyntaxError);
for (const [raw, expected] of vectors.duplicates) {{
  if (!Object.is(payload(await invoke(raw)).n, expected)) {{
    throw new Error("last duplicate member was not selected");
  }}
}}
for (const raw of vectors.selectedDuplicateRejections) {{
  await expectError(raw, TypeError);
}}

const prototypeNames = payload(await invoke(vectors.prototypeNames));
for (const name of ["__proto__", "constructor", "prototype"]) {{
  if (!Object.hasOwn(prototypeNames, name)) throw new Error(`missing own property ${{name}}`);
}}
if (
  Object.getPrototypeOf(prototypeNames) !== Object.prototype ||
  Object.hasOwn(Object.prototype, "polluted")
) throw new Error("prototype-like free-form key changed the prototype");

console.log("typescript free-form JSON: passed");
""".lstrip()
