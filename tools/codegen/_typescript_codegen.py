"""Render strict TypeScript models, operation inventory, and fetch client."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from tools.codegen._absolute_uri_codegen import require_absolute_uri_profile
from tools.codegen._json_integer_codegen import require_json_integer_profile
from tools.codegen._rfc3339_codegen import require_rfc3339_profile
from tools.codegen._typescript_json_codegen import render_typescript_json_parser
from tools.codegen._typescript_validation_codegen import render_validators

__all__ = ["render_typescript"]


@dataclass(frozen=True, slots=True)
class _Parameter:
    wire_name: str
    input_name: str
    location: str
    type_expression: str
    required: bool


@dataclass(frozen=True, slots=True)
class _Operation:
    operation_id: str
    method: str
    path: str
    parameters: tuple[_Parameter, ...]
    request_model: str | None
    response_model: str | None
    success_models: tuple[tuple[int, str], ...]
    problem_models: tuple[tuple[int, str], ...]
    authenticated: bool


def render_typescript(document: dict[str, object], contract_digest: str) -> dict[str, str]:
    integer_profile = require_json_integer_profile(document)
    require_rfc3339_profile(document)
    uri_profile = require_absolute_uri_profile(document)
    operations = _operations(document)
    components = _mapping(document.get("components"), "components")
    schemas = _mapping(components.get("schemas"), "components.schemas")
    validators = render_validators(
        schemas,
        {item.operation_id: item.success_models for item in operations},
        {item.operation_id: item.problem_models for item in operations},
        contract_digest,
        integer_profile=integer_profile,
        uri_profile=uri_profile,
    )
    return {
        "client.ts": _client(operations, contract_digest),
        "index.ts": _index(contract_digest),
        "models.ts": _models(document, contract_digest),
        "operations.ts": _operation_registry(operations, contract_digest),
        "package.json": _package(),
        "response-json.ts": render_typescript_json_parser(contract_digest),
        "tsconfig.json": _tsconfig(),
        "validators.ts": validators,
    }


def _models(document: dict[str, object], digest: str) -> str:
    components = _mapping(document.get("components"), "components")
    schemas = _mapping(components.get("schemas"), "components.schemas")
    rendered = "\n\n".join(
        f"export type {name} = {_type(_mapping(schema, f'schema {name}'), indent=0)};"
        for name, schema in sorted(schemas.items())
    )
    return f"""// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:{digest}

{rendered}
"""


def _type(schema: Mapping[str, object], *, indent: int) -> str:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return _reference_name(reference)
    if "const" in schema:
        return _literal(schema["const"])
    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        return " | ".join(_type(_mapping(item, "oneOf item"), indent=indent) for item in one_of)
    enum = schema.get("enum")
    if isinstance(enum, list):
        return " | ".join(_literal(item) for item in enum)
    return _primitive_type(schema, indent=indent)


def _primitive_type(schema: Mapping[str, object], *, indent: int) -> str:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(
            "null" if item == "null" else _type({**schema, "type": item}, indent=indent)
            for item in schema_type
        )
    scalar = {
        "boolean": "boolean",
        "integer": "number",
        "null": "null",
        "number": "number",
        "string": "string",
    }.get(str(schema_type))
    if scalar is not None:
        return scalar
    if schema_type == "array":
        items = _type(_mapping(schema.get("items"), "array items"), indent=indent)
        return f"ReadonlyArray<{items}>"
    if schema_type == "object":
        return _object_type(schema, indent=indent)
    raise ValueError(f"unsupported TypeScript schema shape: {dict(schema)}")


def _object_type(schema: Mapping[str, object], *, indent: int) -> str:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return "Readonly<Record<string, unknown>>"
    required_value = schema.get("required", [])
    if not isinstance(required_value, list):
        raise TypeError("object required must be an array")
    required = {str(item) for item in required_value}
    spaces = " " * (indent + 2)
    fields = "\n".join(
        f"{spaces}readonly {json.dumps(str(name))}{'' if name in required else '?'}: "
        f"{_type(_mapping(value, f'property {name}'), indent=indent + 2)};"
        for name, value in sorted(properties.items())
    )
    return "Readonly<{\n" + fields + "\n" + (" " * indent) + "}>"


def _operation_registry(operations: tuple[_Operation, ...], digest: str) -> str:
    ids = " | ".join(json.dumps(item.operation_id) for item in operations)
    entries = "\n".join(_operation_entry(item) for item in operations)
    return f"""// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:{digest}

export type OperationId = {ids};
export type ParameterLocation = "path" | "header" | "query";

export type ParameterSpec = Readonly<{{
  wireName: string;
  inputName: string;
  location: ParameterLocation;
  required: boolean;
}}>;

export type OperationSpec = Readonly<{{
  operationId: OperationId;
  method: "GET" | "POST";
  path: string;
  authenticated: boolean;
  parameters: ReadonlyArray<ParameterSpec>;
  hasBody: boolean;
}}>;

export const OPERATIONS: Readonly<Record<OperationId, OperationSpec>> = {{
{entries}
}};
"""


def _operation_entry(operation: _Operation) -> str:
    parameters = ", ".join(
        "{ "
        + f"wireName: {json.dumps(item.wire_name)}, "
        + f"inputName: {json.dumps(item.input_name)}, "
        + f"location: {json.dumps(item.location)}, required: {str(item.required).lower()}"
        + " }"
        for item in operation.parameters
    )
    return (
        f"  {json.dumps(operation.operation_id)}: {{ operationId: "
        f"{json.dumps(operation.operation_id)}, method: {json.dumps(operation.method)}, "
        f"path: {json.dumps(operation.path)}, authenticated: "
        f"{str(operation.authenticated).lower()}, parameters: [{parameters}], "
        f"hasBody: {str(operation.request_model is not None).lower()} }},"
    )


def _client(operations: tuple[_Operation, ...], digest: str) -> str:
    input_types = "\n\n".join(_input_type(item) for item in operations)
    result_map = "\n".join(
        f"  readonly {json.dumps(item.operation_id)}: {_model_type(item.response_model)};"
        for item in operations
    )
    methods = "\n\n".join(_client_method(item) for item in operations)
    return f"""// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:{digest}

import type * as Models from "./models.js";
import {{ OPERATIONS, type OperationId }} from "./operations.js";
import {{ parseJsonResponse }} from "./response-json.js";
import {{ decodeOperationProblem, decodeOperationResult }} from "./validators.js";

export type ClientOptions = Readonly<{{
  baseUrl: string;
  credential?: string;
  telemetry: () => Models.TelemetryContext;
  fetch?: typeof globalThis.fetch;
}}>;

{input_types}

export type OperationInputs = Readonly<{{
{_operation_input_map(operations)}
}}>;

export type OperationResults = Readonly<{{
{result_map}
}}>;

export class CtowerProblemError extends Error {{
  public constructor(public readonly problem: Models.Problem) {{
    super(`${{problem.code}}: ${{problem.detail}}`);
  }}
}}

export class CtowerClient {{
  readonly #baseUrl: string;
  readonly #credential: string | undefined;
  readonly #telemetry: () => Models.TelemetryContext;
  readonly #fetch: typeof globalThis.fetch;

  public constructor(options: ClientOptions) {{
    this.#baseUrl = options.baseUrl;
    this.#credential = options.credential;
    this.#telemetry = options.telemetry;
    this.#fetch = options.fetch ?? globalThis.fetch;
  }}

{methods}

  private async execute<Id extends OperationId>(
    operationId: Id,
    typedInput: OperationInputs[Id],
  ): Promise<OperationResults[Id]> {{
    const operation = OPERATIONS[operationId];
    const input = typedInput as Readonly<Record<string, unknown>>;
    let path = operation.path;
    const headers = new Headers({{
      Accept: "application/json",
      "X-Ctower-Telemetry-Context": JSON.stringify(this.#telemetry()),
    }});
    if (this.#credential !== undefined) {{
      headers.set("Authorization", `Bearer ${{this.#credential}}`);
    }}
    const query = new URLSearchParams();
    for (const parameter of operation.parameters) {{
      const value = input[parameter.inputName];
      if (value === undefined || value === null) {{
        if (parameter.required) {{
          throw new TypeError(`Missing required parameter ${{parameter.inputName}}`);
        }}
        continue;
      }}
      if (parameter.location === "path") {{
        path = path.replace(`{{${{parameter.wireName}}}}`, encodeURIComponent(String(value)));
      }} else if (parameter.location === "header") {{
        headers.set(parameter.wireName, String(value));
      }} else {{
        query.set(parameter.wireName, String(value));
      }}
    }}
    const url = new URL(path, this.#baseUrl);
    url.search = query.toString();
    const body = operation.hasBody ? JSON.stringify(input.body) : undefined;
    if (body !== undefined) {{
      headers.set("Content-Type", "application/json");
    }}
    const response = await this.#fetch(url, {{
      method: operation.method,
      headers,
      ...(body === undefined ? {{}} : {{ body }}),
    }});
    const payload = parseJsonResponse(await response.text());
    if (response.status < 200 || response.status > 299) {{
      const contentType = response.headers.get("content-type")?.split(";", 1)[0];
      if (contentType !== "application/problem+json") {{
        throw new TypeError("ctower returned a non-problem failure");
      }}
      const problem = decodeOperationProblem(
        operationId,
        response.status,
        payload,
      ) as Models.Problem;
      throw new CtowerProblemError(problem);
    }}
    return decodeOperationResult(
      operationId,
      response.status,
      payload,
    ) as OperationResults[Id];
  }}
}}
"""


def _input_type(operation: _Operation) -> str:
    fields: list[str] = []
    for parameter in operation.parameters:
        optional = "" if parameter.required else "?"
        fields.append(
            f"  readonly {json.dumps(parameter.input_name)}{optional}: {parameter.type_expression};"
        )
    if operation.request_model is not None:
        fields.append(f"  readonly body: Models.{operation.request_model};")
    content = "\n".join(fields)
    return f"export type {_input_name(operation)} = Readonly<{{\n{content}\n}}>;"


def _operation_input_map(operations: tuple[_Operation, ...]) -> str:
    return "\n".join(
        f"  readonly {json.dumps(item.operation_id)}: {_input_name(item)};" for item in operations
    )


def _client_method(operation: _Operation) -> str:
    return f"""  public async {operation.operation_id}(
    input: {_input_name(operation)},
  ): Promise<{_model_type(operation.response_model)}> {{
    return this.execute({json.dumps(operation.operation_id)}, input);
  }}"""


def _input_name(operation: _Operation) -> str:
    return operation.operation_id[0].upper() + operation.operation_id[1:] + "Input"


def _model_type(name: str | None) -> str:
    return f"Models.{name}" if name is not None else "never"


def _index(digest: str) -> str:
    return f"""// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:{digest}

export {{ CtowerClient, CtowerProblemError }} from "./client.js";
export type {{ ClientOptions, OperationInputs, OperationResults }} from "./client.js";
export {{ OPERATIONS }} from "./operations.js";
export type {{ OperationId, OperationSpec }} from "./operations.js";
export {{
  OPERATION_PROBLEM_MODELS,
  OPERATION_SUCCESS_MODELS,
}} from "./validators.js";
export type * from "./models.js";
"""


def _package() -> str:
    return """{
  "_notice": "DO NOT EDIT: generated file; regenerate from declared inputs.",
  "name": "@ctower/client",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "exports": "./src/index.ts",
  "scripts": {
    "typecheck": "tsc --noEmit --project tsconfig.json"
  }
}
"""


def _tsconfig() -> str:
    return """{
  "_notice": "DO NOT EDIT: generated file; regenerate from declared inputs.",
  "extends": "../../../tsconfig.base.json",
  "compilerOptions": {
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "rootDir": "src"
  },
  "include": ["src/**/*.ts"]
}
"""


def _operations(document: dict[str, object]) -> tuple[_Operation, ...]:
    paths = _mapping(document.get("paths"), "paths")
    components = _mapping(document.get("components"), "components")
    definitions = _mapping(components.get("parameters"), "components.parameters")
    response_definitions = _mapping(components.get("responses"), "components.responses")
    operations: list[_Operation] = []
    for path, path_item in paths.items():
        for method, value in _mapping(path_item, f"path {path}").items():
            if method not in {"get", "post"}:
                continue
            operation = _mapping(value, f"{method} {path}")
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str):
                raise TypeError(f"{method} {path} lacks operationId")
            success_models = _success_models(operation)
            operations.append(
                _Operation(
                    operation_id,
                    method.upper(),
                    path,
                    _parameters(operation, definitions),
                    _request_model(operation),
                    _response_model(success_models),
                    success_models,
                    _problem_models(operation, response_definitions),
                    bool(operation.get("security")),
                )
            )
    return tuple(sorted(operations, key=lambda item: item.operation_id))


def _parameters(
    operation: Mapping[str, object], definitions: Mapping[str, object]
) -> tuple[_Parameter, ...]:
    value = operation.get("parameters", [])
    if not isinstance(value, list):
        raise TypeError("operation parameters must be an array")
    parameters: list[_Parameter] = []
    for item in value:
        parameter = _mapping(item, "operation parameter")
        reference = parameter.get("$ref")
        if isinstance(reference, str):
            name = reference.removeprefix("#/components/parameters/")
            parameter = _mapping(definitions.get(name), f"parameter {name}")
        wire_name = str(parameter["name"])
        location = str(parameter["in"])
        required = parameter.get("required", False)
        if not isinstance(required, bool):
            raise TypeError("parameter required must be boolean")
        schema = _mapping(parameter.get("schema"), f"parameter {wire_name}.schema")
        parameters.append(
            _Parameter(
                wire_name,
                _camel(wire_name),
                location,
                _type(schema, indent=0),
                required,
            )
        )
    return tuple(parameters)


def _request_model(operation: Mapping[str, object]) -> str | None:
    body = operation.get("requestBody")
    if body is None:
        return None
    content = _mapping(_mapping(body, "requestBody").get("content"), "requestBody.content")
    media = _mapping(content.get("application/json"), "requestBody application/json")
    return _reference_name(str(_mapping(media.get("schema"), "request schema")["$ref"]))


def _success_models(
    operation: Mapping[str, object],
) -> tuple[tuple[int, str], ...]:
    responses = _mapping(operation.get("responses"), "responses")
    models: list[tuple[int, str]] = []
    for status, value in sorted(responses.items()):
        if not status.startswith("2"):
            continue
        try:
            status_code = int(status)
        except ValueError as error:
            raise ValueError(f"success response status must be exact: {status}") from error
        content = _mapping(_mapping(value, f"response {status}").get("content"), "content")
        media = _mapping(content.get("application/json"), "application/json")
        model = _reference_name(str(_mapping(media.get("schema"), "response schema")["$ref"]))
        models.append((status_code, model))
    return tuple(models)


def _response_model(success_models: tuple[tuple[int, str], ...]) -> str | None:
    models = {model for _, model in success_models}
    if len(models) > 1:
        raise ValueError("one operation cannot expose multiple TypeScript success model types")
    return next(iter(models), None)


def _problem_models(
    operation: Mapping[str, object], definitions: Mapping[str, object]
) -> tuple[tuple[int, str], ...]:
    responses = _mapping(operation.get("responses"), "responses")
    models: list[tuple[int, str]] = []
    for status, value in sorted(responses.items()):
        if status.startswith("2"):
            continue
        try:
            status_code = int(status)
        except ValueError as error:
            raise ValueError(f"failure response status must be exact: {status}") from error
        response = _mapping(value, f"response {status}")
        reference = response.get("$ref")
        if isinstance(reference, str):
            name = reference.removeprefix("#/components/responses/")
            response = _mapping(definitions.get(name), f"response {name}")
        content = _mapping(response.get("content"), f"response {status}.content")
        media = _mapping(
            content.get("application/problem+json"),
            f"response {status} application/problem+json",
        )
        schema = _mapping(media.get("schema"), f"response {status}.schema")
        models.append((status_code, _reference_name(str(schema["$ref"]))))
    return tuple(models)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _reference_name(reference: str) -> str:
    prefix = "#/components/schemas/"
    if not reference.startswith(prefix):
        raise ValueError(f"unsupported TypeScript reference {reference}")
    return reference.removeprefix(prefix)


def _camel(value: str) -> str:
    parts = re.split(r"[-_]", value)
    rendered = parts[0] + "".join(item[:1].upper() + item[1:] for item in parts[1:])
    return "commandId" if rendered == "idempotencyKey" else rendered


def _literal(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
