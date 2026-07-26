"""Render dependency-free TypeScript response validators from OpenAPI schemas."""

from __future__ import annotations

import json
from collections.abc import Mapping

__all__ = ["render_validators"]


def render_validators(
    schemas: Mapping[str, object],
    success_models: Mapping[str, tuple[tuple[int, str], ...]],
    problem_models: Mapping[str, tuple[tuple[int, str], ...]],
    digest: str,
) -> str:
    """Render one strict recursive validator and operation boundary maps."""

    successes = {
        operation_id: {str(status): model for status, model in models}
        for operation_id, models in success_models.items()
    }
    problems = {
        operation_id: {str(status): model for status, model in models}
        for operation_id, models in problem_models.items()
    }
    return f"""// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:{digest}

import type {{ OperationId }} from "./operations.js";

type JsonObject = Readonly<Record<string, unknown>>;

const SCHEMAS: JsonObject = {_json(schemas)};
export const OPERATION_SUCCESS_MODELS: Readonly<
  Record<OperationId, Readonly<Record<string, string>>>
> = {_json(successes)};
export const OPERATION_PROBLEM_MODELS: Readonly<
  Record<OperationId, Readonly<Record<string, string>>>
> = {_json(problems)};

export function validateOperationResult(
  operationId: OperationId,
  status: number,
  value: unknown,
): unknown {{
  const model = OPERATION_SUCCESS_MODELS[operationId][String(status)];
  if (model === undefined) {{
    return fail(operationId, `undeclared success status ${{status}}`);
  }}
  return validateNamed(model, value, operationId);
}}

export function validateOperationProblem(
  operationId: OperationId,
  status: number,
  value: unknown,
): unknown {{
  const model = OPERATION_PROBLEM_MODELS[operationId][String(status)];
  if (model === undefined) {{
    return fail(operationId, `undeclared problem status ${{status}}`);
  }}
  const path = `${{operationId}}.problem`;
  const problem = objectValue(validateNamed(model, value, path), path);
  if (problem["status"] !== status) {{
    return fail(`${{path}}.status`, "Problem status does not match HTTP status");
  }}
  return problem;
}}

function validateNamed(name: string, value: unknown, path: string): unknown {{
  const schema = SCHEMAS[name];
  if (schema === undefined) {{
    return fail(path, `unknown schema ${{name}}`);
  }}
  validateSchema(schema, value, path);
  return value;
}}

function validateSchema(schemaValue: unknown, value: unknown, path: string): void {{
  const schema = objectValue(schemaValue, `${{path}}.schema`);
  const reference = schema["$ref"];
  if (typeof reference === "string") {{
    validateNamed(referenceName(reference, path), value, path);
    return;
  }}
  const oneOf = schema["oneOf"];
  if (Array.isArray(oneOf)) {{
    validateOneOf(oneOf, value, path);
    return;
  }}
  if ("const" in schema && !Object.is(value, schema["const"])) {{
    fail(path, "value does not equal const");
  }}
  const choices = schema["enum"];
  if (Array.isArray(choices) && !choices.some((choice) => Object.is(choice, value))) {{
    fail(path, "value is outside enum");
  }}
  const declaredType = schema["type"];
  if (Array.isArray(declaredType)) {{
    const matched = declaredType.find((item) => matchesType(item, value));
    if (typeof matched !== "string") {{
      fail(path, "value has the wrong type");
    }}
    validateTyped(schema, value, matched, path);
    return;
  }}
  if (typeof declaredType === "string") {{
    if (!matchesType(declaredType, value)) {{
      fail(path, "value has the wrong type");
    }}
    validateTyped(schema, value, declaredType, path);
  }}
}}

function validateOneOf(branches: ReadonlyArray<unknown>, value: unknown, path: string): void {{
  let matches = 0;
  for (const branch of branches) {{
    try {{
      validateSchema(branch, value, path);
      matches += 1;
    }} catch (error: unknown) {{
      if (!(error instanceof TypeError)) {{
        throw error;
      }}
    }}
  }}
  if (matches !== 1) {{
    fail(path, "value must match exactly one schema");
  }}
}}

function validateTyped(schema: JsonObject, value: unknown, kind: string, path: string): void {{
  if (kind === "string") {{
    validateString(schema, value as string, path);
  }} else if (kind === "integer" || kind === "number") {{
    validateNumber(schema, value as number, kind === "integer", path);
  }} else if (kind === "array") {{
    validateArray(schema, value as ReadonlyArray<unknown>, path);
  }} else if (kind === "object") {{
    validateObject(schema, objectValue(value, path), path);
  }}
}}

function validateString(schema: JsonObject, value: string, path: string): void {{
  const minimum = schema["minLength"];
  const maximum = schema["maxLength"];
  if (typeof minimum === "number" && value.length < minimum) {{
    fail(path, "string is too short");
  }}
  if (typeof maximum === "number" && value.length > maximum) {{
    fail(path, "string is too long");
  }}
  const pattern = schema["pattern"];
  if (typeof pattern === "string" && !new RegExp(pattern, "u").test(value)) {{
    fail(path, "string does not match pattern");
  }}
  validateFormat(schema["format"], value, path);
}}

function validateFormat(format: unknown, value: string, path: string): void {{
  if (format === "uuid" && !UUID_PATTERN.test(value)) {{
    fail(path, "string is not a UUID");
  }}
  if (format === "date-time") {{
    validateDateTime(value, path);
  }}
  if (format === "uri") {{
    try {{
      new URL(value);
    }} catch {{
      fail(path, "string is not an absolute URI");
    }}
  }}
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
  ) {{
    fail(path, "string is outside the proleptic Gregorian calendar");
  }}
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

function validateNumber(
  schema: JsonObject,
  value: number,
  integer: boolean,
  path: string,
): void {{
  if (!Number.isFinite(value) || (integer && !Number.isInteger(value))) {{
    fail(path, integer ? "value is not an integer" : "value is not finite");
  }}
  const minimum = schema["minimum"];
  const maximum = schema["maximum"];
  if (typeof minimum === "number" && value < minimum) {{
    fail(path, "number is below minimum");
  }}
  if (typeof maximum === "number" && value > maximum) {{
    fail(path, "number is above maximum");
  }}
}}

function validateArray(
  schema: JsonObject,
  value: ReadonlyArray<unknown>,
  path: string,
): void {{
  const minimum = schema["minItems"];
  const maximum = schema["maxItems"];
  if (typeof minimum === "number" && value.length < minimum) {{
    fail(path, "array has too few items");
  }}
  if (typeof maximum === "number" && value.length > maximum) {{
    fail(path, "array has too many items");
  }}
  const items = schema["items"];
  if (items !== undefined) {{
    value.forEach((item, index) => validateSchema(items, item, `${{path}}[${{index}}]`));
  }}
}}

function validateObject(schema: JsonObject, value: JsonObject, path: string): void {{
  const properties = objectValue(schema["properties"] ?? {{}}, `${{path}}.properties`);
  const required = schema["required"];
  if (Array.isArray(required)) {{
    for (const name of required) {{
      if (typeof name !== "string" || !Object.hasOwn(value, name)) {{
        fail(path, `missing required field ${{String(name)}}`);
      }}
    }}
  }}
  if (schema["additionalProperties"] === false) {{
    for (const name of Object.keys(value)) {{
      if (!Object.hasOwn(properties, name)) {{
        fail(path, `unknown field ${{name}}`);
      }}
    }}
  }}
  for (const [name, propertySchema] of Object.entries(properties)) {{
    if (Object.hasOwn(value, name)) {{
      validateSchema(propertySchema, value[name], `${{path}}.${{name}}`);
    }}
  }}
}}

function matchesType(kind: unknown, value: unknown): boolean {{
  if (kind === "null") return value === null;
  if (kind === "string") return typeof value === "string";
  if (kind === "boolean") return typeof value === "boolean";
  if (kind === "integer") return typeof value === "number" && Number.isInteger(value);
  if (kind === "number") return typeof value === "number";
  if (kind === "array") return Array.isArray(value);
  return kind === "object" && value !== null && typeof value === "object" && !Array.isArray(value);
}}

function objectValue(value: unknown, path: string): JsonObject {{
  if (value === null || typeof value !== "object" || Array.isArray(value)) {{
    return fail(path, "value is not an object");
  }}
  return value as JsonObject;
}}

function referenceName(reference: string, path: string): string {{
  const prefix = "#/components/schemas/";
  if (!reference.startsWith(prefix)) {{
    return fail(path, `unsupported reference ${{reference}}`);
  }}
  return reference.slice(prefix.length);
}}

function fail(path: string, reason: string): never {{
  throw new TypeError(`Invalid ctower response at ${{path}}: ${{reason}}`);
}}

const UUID_PATTERN =
  /^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$/iu;
const DATE_TIME_PATTERN =
  /^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})T(\\d{{2}}):(\\d{{2}}):(\\d{{2}})(?:\\.\\d{{1,6}})?(Z|([+-])(\\d{{2}}):(\\d{{2}}))$/u;
"""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
