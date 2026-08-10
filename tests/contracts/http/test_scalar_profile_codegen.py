"""Generation proofs for the authored scalar and free-form JSON profiles."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast

import pytest

from tools.codegen.generator import CodegenError, render_typescript_fixture, write

from ._generated_client_runtime import (
    compile_typescript_client,
    node_executable,
    run_command,
)

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
AUTHORED_INTEGER_OCCURRENCES = 180
AUTHORED_OPERATION_COUNT = 78
RESPONSE_INTEGER_NODES = 140
PROFILE_KEYS = (
    "x-ctower-rfc3339-profile",
    "x-ctower-json-integer-profile",
    "x-ctower-free-form-json-profile",
    "x-ctower-absolute-uri-profile",
)
SIGNED_FIELDS = (
    "direct_slot",
    "reference_slot",
    "array_slot",
    "nullable_slot",
    "union_slot",
)
_OMITTED = object()


@pytest.mark.parametrize("profile", PROFILE_KEYS)
def test_codegen_refuses_authored_scalar_profile_drift(
    profile: str,
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "fixture"
    shutil.copytree(
        ROOT,
        fixture,
        ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"),
    )
    path = fixture / "contracts/http/openapi.yaml"
    document = json.loads(path.read_text(encoding="utf-8"))
    document[profile] = {}
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(CodegenError, match="must declare"):
        write(fixture)


def test_project_key_parameter_generates_the_python_validator(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    shutil.copytree(
        ROOT,
        fixture,
        ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"),
    )
    path = fixture / "contracts/http/openapi.yaml"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["components"]["parameters"]["ProjectKey"]["schema"]["pattern"] = "^[a-z]{4,8}$"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    write(fixture)
    client = (fixture / "generated/python/ctower_client/client.py").read_text(encoding="utf-8")
    assert 'type ProjectKey = Annotated[str, Field(pattern="^[a-z]{4,8}$")]' in client
    assert "project_key: ProjectKey" in client


def test_response_integer_graph_is_complete_and_uses_one_recursive_branch() -> None:
    document = _authored_document()
    operations = tuple(_operations(document))
    reachable = _reachable_integer_nodes(document, operations)

    assert len(operations) == AUTHORED_OPERATION_COUNT
    assert len(reachable) == RESPONSE_INTEGER_NODES
    assert _integer_occurrences(document) == AUTHORED_INTEGER_OCCURRENCES
    validators = (ROOT / "generated/typescript/ctower-client/src/validators.ts").read_text(
        encoding="utf-8"
    )
    client = (ROOT / "generated/typescript/ctower-client/src/client.ts").read_text(encoding="utf-8")
    index = (ROOT / "generated/typescript/ctower-client/src/index.ts").read_text(encoding="utf-8")
    python_models = (ROOT / "generated/python/ctower_client/models.py").read_text(encoding="utf-8")
    assert validators.count('if (kind === "integer") return decodeInteger') == 1
    assert validators.count("function decodeInteger(") == 1
    assert "parseJsonResponse(await response.text())" in client
    assert "response.json()" not in client
    assert "response-json" not in index
    assert "AnyUrl" not in python_models
    assert "def _is_absolute_uri(" in python_models


def test_signed_fixture_exercises_every_recursive_integer_position(tmp_path: Path) -> None:
    rendered = render_typescript_fixture(_signed_fixture(), "0" * 64)
    package = tmp_path / "fixture/generated/typescript/ctower-client"
    _write_typescript_fixture(package, rendered)
    compiled = tmp_path / "compiled"
    compile_typescript_client(compiled, source_root=package)
    runner = compiled / "signed-integers.mjs"
    runner.write_text(_signed_fixture_runner(), encoding="utf-8")

    completed = run_command((node_executable(), str(runner)), cwd=compiled)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "signed integer fixture: passed"
    decoder = rendered["validators.ts"].split("export function decodeOperationResult", 1)[1]
    assert all(json.dumps(field) not in decoder for field in SIGNED_FIELDS)
    assert decoder.count("function decodeInteger(") == 1


def test_codegen_rejects_an_unconstrained_numeric_response_leaf() -> None:
    document = _signed_fixture()
    components = cast(dict[str, object], document["components"])
    schemas = cast(dict[str, dict[str, object]], components["schemas"])
    response = schemas["SignedFixtureResponse"]
    properties = cast(dict[str, object], response["properties"])
    properties["direct_slot"] = {}

    with pytest.raises(ValueError, match="unconstrained numeric response leaf"):
        render_typescript_fixture(document, "0" * 64)


@pytest.mark.parametrize(
    "additional_properties",
    (_OMITTED, True, {}),
    ids=("omitted", "true", "empty-schema"),
)
def test_free_form_profile_is_selected_by_object_structure(
    additional_properties: object,
    tmp_path: Path,
) -> None:
    fixture = _free_form_fixture(tmp_path, additional_properties)
    write(fixture)
    _assert_structural_free_form_generation(fixture)


def _free_form_fixture(tmp_path: Path, additional_properties: object) -> Path:
    fixture = tmp_path / "fixture"
    shutil.copytree(
        ROOT,
        fixture,
        ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"),
    )
    path = fixture / "contracts/http/openapi.yaml"
    document = cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )
    components = cast(dict[str, object], document["components"])
    schemas = cast(dict[str, dict[str, object]], components["schemas"])
    resource = schemas["CompanyBundleResource"]
    properties = cast(dict[str, object], resource["properties"])
    free_form: dict[str, object] = {"type": "object"}
    if additional_properties is not _OMITTED:
        free_form["additionalProperties"] = additional_properties
    properties["payload"] = free_form
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return fixture


def _assert_structural_free_form_generation(fixture: Path) -> None:
    validators = (fixture / "generated/typescript/ctower-client/src/validators.ts").read_text(
        encoding="utf-8"
    )
    decoder = validators.split("function decodeUntyped", 1)[1].split(
        "function validateConstAndEnum",
        1,
    )[0]
    assert "decodeInteger(FREE_FORM_NUMBER_SCHEMA" in decoder
    assert "decodeNumber(FREE_FORM_NUMBER_SCHEMA" in decoder
    assert all(
        forbidden not in decoder
        for forbidden in (
            "CompanyBundleResource",
            "payload",
            "revision",
            "exportCompanyBundle",
        )
    )
    python_models = (fixture / "generated/python/ctower_client/models.py").read_text(
        encoding="utf-8"
    )
    python_init = (fixture / "generated/python/ctower_client/__init__.py").read_text(
        encoding="utf-8"
    )
    typescript_models = (fixture / "generated/typescript/ctower-client/src/models.ts").read_text(
        encoding="utf-8"
    )
    assert "payload: _FreeFormJsonObject" in python_models
    assert "_FreeFormJsonObject" not in python_init
    assert 'readonly "payload": Readonly<Record<string, unknown>>' in typescript_models


def _authored_document() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8")),
    )


def _operations(document: Mapping[str, object]) -> list[dict[str, object]]:
    paths = cast(dict[str, dict[str, object]], document["paths"])
    return [
        cast(dict[str, object], operation)
        for path in paths.values()
        for method, operation in path.items()
        if method in {"get", "post"}
    ]


def _resolve(document: Mapping[str, object], reference: str) -> object:
    value: object = document
    for part in reference.removeprefix("#/").split("/"):
        value = cast(Mapping[str, object], value)[part]
    return value


def _reachable_integer_nodes(
    document: Mapping[str, object],
    operations: tuple[dict[str, object], ...],
) -> set[int]:
    seen: set[int] = set()
    integers: set[int] = set()
    for schema in _response_schemas(document, operations):
        _visit_schema(document, schema, seen, integers)
    return integers


def _response_schemas(
    document: Mapping[str, object],
    operations: tuple[dict[str, object], ...],
) -> Iterator[object]:
    for operation in operations:
        for response_value in cast(dict[str, dict[str, object]], operation["responses"]).values():
            response = response_value
            reference = response.get("$ref")
            if isinstance(reference, str):
                response = cast(dict[str, object], _resolve(document, reference))
            content = cast(dict[str, dict[str, object]], response.get("content", {}))
            for media in content.values():
                yield media["schema"]


def _visit_schema(
    document: Mapping[str, object],
    value: object,
    seen: set[int],
    integers: set[int],
) -> None:
    if isinstance(value, list):
        for item in value:
            _visit_schema(document, item, seen, integers)
        return
    if not isinstance(value, dict):
        return
    if id(value) in seen:
        return
    seen.add(id(value))
    if value.get("type") == "integer":
        integers.add(id(value))
    reference = value.get("$ref")
    if isinstance(reference, str):
        _visit_schema(document, _resolve(document, reference), seen, integers)
    for item in value.values():
        _visit_schema(document, item, seen, integers)


def _integer_occurrences(value: object) -> int:
    if isinstance(value, list):
        return sum(_integer_occurrences(item) for item in value)
    if not isinstance(value, dict):
        return 0
    return int(value.get("type") == "integer") + sum(
        _integer_occurrences(item) for item in value.values()
    )


def _signed_fixture() -> dict[str, object]:
    authored = _authored_document()
    integer: dict[str, object] = {"type": "integer"}
    return {
        "openapi": "3.1.0",
        **{key: authored[key] for key in PROFILE_KEYS},
        "components": {
            "parameters": {},
            "responses": {},
            "schemas": {
                "Problem": _fixture_problem_schema(),
                "SignedFixtureInteger": integer,
                "SignedFixtureResponse": _signed_response_schema(integer),
                "TelemetryContext": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {},
                },
            },
        },
        "paths": {
            "/fixture": {
                "get": {
                    "operationId": "getSignedFixture",
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/SignedFixtureResponse"}
                                }
                            }
                        }
                    },
                }
            }
        },
    }


def _fixture_problem_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "detail", "status", "title", "type"],
        "properties": {
            "code": {"type": "string"},
            "detail": {"type": "string"},
            "status": {"type": "integer"},
            "title": {"type": "string"},
            "type": {"type": "string", "format": "uri"},
        },
    }


def _signed_response_schema(integer: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(SIGNED_FIELDS),
        "properties": {
            "direct_slot": integer,
            "reference_slot": {"$ref": "#/components/schemas/SignedFixtureInteger"},
            "array_slot": {"type": "array", "items": integer},
            "nullable_slot": {"type": ["integer", "null"]},
            "union_slot": {"oneOf": [integer, {"type": "string", "const": "fallback"}]},
        },
    }


def _write_typescript_fixture(package: Path, rendered: Mapping[str, str]) -> None:
    (package / "src").mkdir(parents=True)
    shutil.copyfile(ROOT / "tsconfig.base.json", package.parents[2] / "tsconfig.base.json")
    for name, content in rendered.items():
        target = package / name if name.endswith(".json") else package / "src" / name
        target.write_text(content, encoding="utf-8")


def _signed_raw(token: str, *, selected: str | None = None) -> str:
    markers = {field: f"__{field.upper()}__" for field in SIGNED_FIELDS}
    payload: dict[str, object] = {
        "direct_slot": markers["direct_slot"],
        "reference_slot": markers["reference_slot"],
        "array_slot": [markers["array_slot"]],
        "nullable_slot": markers["nullable_slot"],
        "union_slot": markers["union_slot"],
    }
    rendered = json.dumps(payload, separators=(",", ":"))
    for field, marker in markers.items():
        replacement = token if selected in (None, field) else "1"
        rendered = rendered.replace(json.dumps(marker), replacement)
    return rendered


def _signed_fixture_runner() -> str:
    accepted = [
        (_signed_raw("-9007199254740991"), -9_007_199_254_740_991),
        (_signed_raw("0"), 0),
        (_signed_raw("9007199254740991"), 9_007_199_254_740_991),
        (_signed_raw("-0"), 0),
    ]
    rejected = [
        _signed_raw("-9007199254740992"),
        _signed_raw("9007199254740992"),
        *[
            _signed_raw(token, selected=field)
            for field in SIGNED_FIELDS
            for token in ("1.0", "1e0")
        ],
    ]
    return f"""
import {{ CtowerClient }} from "./index.js";

const responses = [];
const client = new CtowerClient({{
  baseUrl: "http://contract.invalid",
  telemetry: () => ({{}}),
  fetch: async () => new Response(responses.shift(), {{
    status: 200,
    headers: {{"content-type": "application/json"}},
  }}),
}});
const invoke = () => client.getSignedFixture({{}});
for (const [raw, expected] of {json.dumps(accepted, separators=(",", ":"))}) {{
  responses.push(raw);
  const result = await invoke();
  const values = [
    result.direct_slot,
    result.reference_slot,
    result.array_slot[0],
    result.nullable_slot,
    result.union_slot,
  ];
  if (!values.every((value) => Object.is(value, expected))) {{
    throw new Error(`signed integer changed: ${{raw}}`);
  }}
}}
for (const raw of {json.dumps(rejected, separators=(",", ":"))}) {{
  responses.push(raw);
  try {{
    await invoke();
  }} catch (error) {{
    if (error instanceof TypeError) continue;
    throw error;
  }}
  throw new Error(`invalid signed integer accepted: ${{raw}}`);
}}
console.log("signed integer fixture: passed");
""".lstrip()
