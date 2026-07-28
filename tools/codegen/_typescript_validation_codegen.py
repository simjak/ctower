"""Render schema-aware TypeScript response materialization from lossless JSON nodes."""

from __future__ import annotations

import json
from collections.abc import Mapping

from tools.codegen._absolute_uri_codegen import (
    AbsoluteUriProfile,
    render_typescript_uri_validator,
)
from tools.codegen._free_form_json_codegen import (
    FreeFormJsonProfile,
    has_free_form_additional_properties,
    render_typescript_free_form_decoder,
)
from tools.codegen._json_integer_codegen import JsonIntegerProfile

__all__ = ["render_validators"]

_MATERIALIZABLE_SCALAR_TYPES = frozenset({"null", "boolean", "string", "integer", "number"})


def render_validators(
    schemas: Mapping[str, object],
    success_models: Mapping[str, tuple[tuple[int, str], ...]],
    problem_models: Mapping[str, tuple[tuple[int, str], ...]],
    digest: str,
    *,
    free_form_profile: FreeFormJsonProfile,
    integer_profile: JsonIntegerProfile,
    uri_profile: AbsoluteUriProfile,
) -> str:
    """Render one recursive schema decoder and operation boundary maps."""

    _require_materializable_response_graph(schemas, success_models, problem_models)
    successes = {
        operation_id: {str(status): model for status, model in models}
        for operation_id, models in success_models.items()
    }
    problems = {
        operation_id: {str(status): model for status, model in models}
        for operation_id, models in problem_models.items()
    }
    uri_validator = render_typescript_uri_validator(uri_profile)
    free_form_decoder = render_typescript_free_form_decoder(free_form_profile)
    return f"""// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:{digest}

import type {{ OperationId }} from "./operations.js";
import type {{
  JsonArrayNode,
  JsonNode,
  JsonNumberNode,
  JsonObjectNode,
}} from "./response-json.js";

type SchemaObject = Readonly<Record<string, unknown>>;

const JSON_INTEGER_MINIMUM = {integer_profile.minimum};
const JSON_INTEGER_MAXIMUM = {integer_profile.maximum};
const SCHEMAS: SchemaObject = {_json(schemas)};
export const OPERATION_SUCCESS_MODELS: Readonly<
  Record<OperationId, Readonly<Record<string, string>>>
> = {_json(successes)};
export const OPERATION_PROBLEM_MODELS: Readonly<
  Record<OperationId, Readonly<Record<string, string>>>
> = {_json(problems)};

export function decodeOperationResult(
  operationId: OperationId,
  status: number,
  node: JsonNode,
): unknown {{
  const model = OPERATION_SUCCESS_MODELS[operationId][String(status)];
  if (model === undefined) return fail(operationId, `undeclared success status ${{status}}`);
  return decodeNamed(model, node, operationId);
}}

export function decodeOperationProblem(
  operationId: OperationId,
  status: number,
  node: JsonNode,
): unknown {{
  const model = OPERATION_PROBLEM_MODELS[operationId][String(status)];
  if (model === undefined) return fail(operationId, `undeclared problem status ${{status}}`);
  const path = `${{operationId}}.problem`;
  const problem = objectValue(decodeNamed(model, node, path), path);
  if (problem["status"] !== status) {{
    return fail(`${{path}}.status`, "Problem status does not match HTTP status");
  }}
  return problem;
}}

function decodeNamed(name: string, node: JsonNode, path: string): unknown {{
  const schema = SCHEMAS[name];
  if (schema === undefined) return fail(path, `unknown schema ${{name}}`);
  return decodeSchema(schema, node, path);
}}

function decodeSchema(schemaValue: unknown, node: JsonNode, path: string): unknown {{
  const schema = objectValue(schemaValue, `${{path}}.schema`);
  const reference = schema["$ref"];
  if (typeof reference === "string") {{
    return decodeNamed(referenceName(reference, path), node, path);
  }}
  const oneOf = schema["oneOf"];
  if (Array.isArray(oneOf)) return decodeOneOf(oneOf, node, path);
  const declaredType = schema["type"];
  let value: unknown;
  if (Array.isArray(declaredType)) {{
    value = decodeTypeUnion(schema, declaredType, node, path);
  }} else if (typeof declaredType === "string") {{
    value = decodeTyped(schema, declaredType, node, path);
  }} else {{
    value = decodeImplicitScalar(schema, node, path);
  }}
  validateConstAndEnum(schema, value, path);
  return value;
}}

function decodeOneOf(
  branches: ReadonlyArray<unknown>,
  node: JsonNode,
  path: string,
): unknown {{
  const matches: unknown[] = [];
  for (const branch of branches) {{
    try {{
      matches.push(decodeSchema(branch, node, path));
    }} catch (error: unknown) {{
      if (!(error instanceof TypeError)) throw error;
    }}
  }}
  if (matches.length !== 1) return fail(path, "value must match exactly one schema");
  return matches[0];
}}

function decodeTypeUnion(
  schema: SchemaObject,
  types: ReadonlyArray<unknown>,
  node: JsonNode,
  path: string,
): unknown {{
  for (const kind of types) {{
    if (typeof kind !== "string") continue;
    try {{
      return decodeTyped(schema, kind, node, path);
    }} catch (error: unknown) {{
      if (!(error instanceof TypeError)) throw error;
    }}
  }}
  return fail(path, "value has the wrong type");
}}

function decodeImplicitScalar(
  schema: SchemaObject,
  node: JsonNode,
  path: string,
): unknown {{
  const choices = schema["enum"];
  const exemplar = "const" in schema
    ? schema["const"]
    : Array.isArray(choices) && choices.length > 0
      ? choices[0]
      : undefined;
  if (typeof exemplar === "string") return decodeString(schema, node, path);
  if (typeof exemplar === "boolean") return decodeBoolean(node, path);
  if (exemplar === null) return decodeNull(node, path);
  if (typeof exemplar === "number" && Number.isInteger(exemplar)) {{
    return decodeInteger(schema, node, path);
  }}
  if (typeof exemplar === "number") return decodeNumber(schema, node, path);
  return fail(path, "schema has no materializable scalar type");
}}

function decodeTyped(
  schema: SchemaObject,
  kind: string,
  node: JsonNode,
  path: string,
): unknown {{
  if (kind === "null") return decodeNull(node, path);
  if (kind === "boolean") return decodeBoolean(node, path);
  if (kind === "string") return decodeString(schema, node, path);
  if (kind === "integer") return decodeInteger(schema, node, path);
  if (kind === "number") return decodeNumber(schema, node, path);
  if (kind === "array") return decodeArray(schema, node, path);
  if (kind === "object") return decodeObject(schema, node, path);
  return fail(path, `unsupported schema type ${{kind}}`);
}}

function decodeNull(node: JsonNode, path: string): null {{
  if (node !== null) return fail(path, "value is not null");
  return null;
}}

function decodeBoolean(node: JsonNode, path: string): boolean {{
  if (typeof node !== "boolean") return fail(path, "value is not a boolean");
  return node;
}}

function decodeString(schema: SchemaObject, node: JsonNode, path: string): string {{
  if (typeof node !== "string") return fail(path, "value is not a string");
  const minimum = schema["minLength"];
  const maximum = schema["maxLength"];
  if (typeof minimum === "number" && node.length < minimum) fail(path, "string is too short");
  if (typeof maximum === "number" && node.length > maximum) fail(path, "string is too long");
  const pattern = schema["pattern"];
  if (typeof pattern === "string" && !new RegExp(pattern, "u").test(node)) {{
    fail(path, "string does not match pattern");
  }}
  validateFormat(schema["format"], node, path);
  return node;
}}

function decodeInteger(schema: SchemaObject, node: JsonNode, path: string): number {{
  const number = numberNode(node, path);
  if (!/^-?(?:0|[1-9][0-9]*)$/u.test(number.raw)) {{
    return fail(path, "value is not an exact JSON integer token");
  }}
  if (!integerTokenInSharedRange(number.raw)) {{
    return fail(path, "integer is outside the lossless JSON range");
  }}
  const value = number.raw === "-0" ? 0 : Number(number.raw);
  validateNumericBounds(schema, value, path);
  return value;
}}

function decodeNumber(schema: SchemaObject, node: JsonNode, path: string): number {{
  const value = Number(numberNode(node, path).raw);
  if (!Number.isFinite(value)) return fail(path, "number is not finite");
  validateNumericBounds(schema, value, path);
  return value;
}}

function integerTokenInSharedRange(raw: string): boolean {{
  const negative = raw.startsWith("-");
  const digits = negative ? raw.slice(1) : raw;
  const limit = String(negative ? -JSON_INTEGER_MINIMUM : JSON_INTEGER_MAXIMUM);
  return digits.length < limit.length || digits.length === limit.length && digits <= limit;
}}

function validateNumericBounds(schema: SchemaObject, value: number, path: string): void {{
  const minimum = schema["minimum"];
  const maximum = schema["maximum"];
  if (typeof minimum === "number" && value < minimum) fail(path, "number is below minimum");
  if (typeof maximum === "number" && value > maximum) fail(path, "number is above maximum");
}}

function decodeArray(schema: SchemaObject, node: JsonNode, path: string): unknown[] {{
  const array = arrayNode(node, path);
  const minimum = schema["minItems"];
  const maximum = schema["maxItems"];
  if (typeof minimum === "number" && array.items.length < minimum) {{
    fail(path, "array has too few items");
  }}
  if (typeof maximum === "number" && array.items.length > maximum) {{
    fail(path, "array has too many items");
  }}
  const items = schema["items"];
  if (items === undefined) return fail(path, "array schema has unconstrained items");
  return array.items.map((item, index) => decodeSchema(items, item, `${{path}}[${{index}}]`));
}}

function decodeObject(
  schema: SchemaObject,
  node: JsonNode,
  path: string,
): Record<string, unknown> {{
  const object = objectNode(node, path);
  const properties = objectValue(schema["properties"] ?? {{}}, `${{path}}.properties`);
  const members = new Map<string, JsonNode>();
  for (const [name, member] of object.members) members.set(name, member);
  const required = schema["required"];
  if (Array.isArray(required)) {{
    for (const name of required) {{
      if (typeof name !== "string" || !members.has(name)) {{
        fail(path, `missing required field ${{String(name)}}`);
      }}
    }}
  }}
  const result: Record<string, unknown> = {{}};
  for (const [name, member] of members) {{
    let value: unknown;
    if (Object.hasOwn(properties, name)) {{
      value = decodeSchema(properties[name], member, `${{path}}.${{name}}`);
    }} else {{
      const additional = schema["additionalProperties"];
      if (additional === false) fail(path, `unknown field ${{name}}`);
      if (hasFreeFormAdditionalProperties(additional)) {{
        value = decodeUntyped(member, `${{path}}.${{name}}`);
      }} else {{
        value = decodeSchema(additional, member, `${{path}}.${{name}}`);
      }}
    }}
    Object.defineProperty(result, name, {{
      configurable: true,
      enumerable: true,
      value,
      writable: true,
    }});
  }}
  return result;
}}

{free_form_decoder}

function validateConstAndEnum(schema: SchemaObject, value: unknown, path: string): void {{
  if ("const" in schema && !Object.is(value, schema["const"])) {{
    fail(path, "value does not equal const");
  }}
  const choices = schema["enum"];
  if (Array.isArray(choices) && !choices.some((choice) => Object.is(choice, value))) {{
    fail(path, "value is outside enum");
  }}
}}

function validateFormat(format: unknown, value: string, path: string): void {{
  if (format === "uuid" && !UUID_PATTERN.test(value)) fail(path, "string is not a UUID");
  if (format === "date-time") validateDateTime(value, path);
  if (format === "uri" && !isAbsoluteUri(value)) fail(path, "string is not an absolute URI");
}}

function validateDateTime(value: string, path: string): void {{
  const match = DATE_TIME_PATTERN.exec(value);
  if (match === null || match[7] === "-00:00") {{
    fail(path, "string is outside the authored RFC 3339 profile");
  }}
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth(year, month) ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) fail(path, "string is outside the proleptic Gregorian calendar");
  const offsetHour = Number(match[9] ?? 0);
  const offsetMinute = Number(match[10] ?? 0);
  if (offsetHour > 23 || offsetMinute > 59) {{
    fail(path, "string has an invalid RFC 3339 numeric offset");
  }}
}}

function daysInMonth(year: number, month: number): number {{
  if (month === 2) {{
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    return leap ? 29 : 28;
  }}
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}}

function numberNode(node: JsonNode, path: string): JsonNumberNode {{
  if (node === null || typeof node !== "object" || node.kind !== "number") {{
    return fail(path, "value is not a number");
  }}
  return node;
}}

function arrayNode(node: JsonNode, path: string): JsonArrayNode {{
  if (node === null || typeof node !== "object" || node.kind !== "array") {{
    return fail(path, "value is not an array");
  }}
  return node;
}}

function objectNode(node: JsonNode, path: string): JsonObjectNode {{
  if (node === null || typeof node !== "object" || node.kind !== "object") {{
    return fail(path, "value is not an object");
  }}
  return node;
}}

function objectValue(value: unknown, path: string): SchemaObject {{
  if (value === null || typeof value !== "object" || Array.isArray(value)) {{
    return fail(path, "value is not an object");
  }}
  return value as SchemaObject;
}}

function referenceName(reference: string, path: string): string {{
  const prefix = "#/components/schemas/";
  if (!reference.startsWith(prefix)) return fail(path, `unsupported reference ${{reference}}`);
  return reference.slice(prefix.length);
}}

function fail(path: string, reason: string): never {{
  throw new TypeError(`Invalid ctower response at ${{path}}: ${{reason}}`);
}}

const UUID_PATTERN =
  /^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$/iu;
const DATE_TIME_PATTERN =
  /^([0-9]{{4}})-([0-9]{{2}})-([0-9]{{2}})T([0-9]{{2}}):([0-9]{{2}}):([0-9]{{2}})(?:\\.[0-9]{{1,6}})?(Z|([+-])([0-9]{{2}}):([0-9]{{2}}))$/u;

{uri_validator}
"""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _require_materializable_response_graph(
    schemas: Mapping[str, object],
    success_models: Mapping[str, tuple[tuple[int, str], ...]],
    problem_models: Mapping[str, tuple[tuple[int, str], ...]],
) -> None:
    seen: set[int] = set()
    model_names = {
        model
        for inventory in (success_models, problem_models)
        for statuses in inventory.values()
        for _, model in statuses
    }
    for name in sorted(model_names):
        if name not in schemas:
            raise ValueError(f"response references unknown schema {name}")
        _visit_materializable_schema(schemas[name], f"schema {name}", schemas, seen)


def _visit_materializable_schema(
    value: object,
    path: str,
    schemas: Mapping[str, object],
    seen: set[int],
) -> None:
    schema = _schema_mapping(value, path)
    if _already_visited(schema, seen):
        return
    reference = schema.get("$ref")
    if isinstance(reference, str):
        _visit_materializable_reference(reference, path, schemas, seen)
        return
    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        _visit_materializable_branches(one_of, path, schemas, seen)
        return
    declared = schema.get("type")
    if declared is None:
        _require_implicit_scalar(schema, path)
        return
    types = declared if isinstance(declared, list) else [declared]
    for kind in types:
        _visit_materializable_type(kind, schema, path, schemas, seen)


def _schema_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} response schema must be an object")
    return value


def _already_visited(schema: Mapping[str, object], seen: set[int]) -> bool:
    identity = id(schema)
    if identity in seen:
        return True
    seen.add(identity)
    return False


def _visit_materializable_reference(
    reference: str,
    path: str,
    schemas: Mapping[str, object],
    seen: set[int],
) -> None:
    name = reference.rsplit("/", 1)[-1]
    if name not in schemas:
        raise ValueError(f"{path} references unknown response schema {name}")
    _visit_materializable_schema(schemas[name], f"schema {name}", schemas, seen)


def _visit_materializable_branches(
    branches: list[object],
    path: str,
    schemas: Mapping[str, object],
    seen: set[int],
) -> None:
    for index, branch in enumerate(branches):
        _visit_materializable_schema(branch, f"{path}.oneOf[{index}]", schemas, seen)


def _require_implicit_scalar(schema: Mapping[str, object], path: str) -> None:
    if "const" not in schema and not schema.get("enum"):
        raise ValueError(f"{path} has an unconstrained numeric response leaf")


def _visit_materializable_type(
    kind: object,
    schema: Mapping[str, object],
    path: str,
    schemas: Mapping[str, object],
    seen: set[int],
) -> None:
    if kind == "array":
        if "items" not in schema:
            raise ValueError(f"{path} has unconstrained response array items")
        _visit_materializable_schema(schema["items"], f"{path}.items", schemas, seen)
        return
    if kind == "object":
        _visit_materializable_object(schema, path, schemas, seen)
        return
    if not isinstance(kind, str) or kind not in _MATERIALIZABLE_SCALAR_TYPES:
        raise ValueError(f"{path} has unsupported response schema type {kind}")


def _visit_materializable_object(
    schema: Mapping[str, object],
    path: str,
    schemas: Mapping[str, object],
    seen: set[int],
) -> None:
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise TypeError(f"{path}.properties must be an object")
    for name, child in properties.items():
        _visit_materializable_schema(child, f"{path}.{name}", schemas, seen)
    if has_free_form_additional_properties(schema):
        return
    additional = schema.get("additionalProperties")
    if additional is False:
        return
    _visit_materializable_schema(additional, f"{path}.additionalProperties", schemas, seen)
