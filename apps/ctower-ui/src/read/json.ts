/**
 * Strict readers for one untrusted JSON payload.
 *
 * Every value that crosses the process boundary is narrowed here or refused.
 * A refusal surfaces on the screen as an explicit `unavailable` reading; it is
 * never silently coerced into a default, because a defaulted field on this
 * surface would read as a recorded fact.
 */

export class PayloadRefusal extends Error {
  public constructor(field: string, expected: string) {
    super(`the record payload field ${field} is not ${expected}`);
    this.name = "PayloadRefusal";
  }
}

export function asRecord(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new PayloadRefusal(field, "an object");
  }
  return value as Record<string, unknown>;
}

export function asArray(value: unknown, field: string): readonly unknown[] {
  if (!Array.isArray(value)) {
    throw new PayloadRefusal(field, "an array");
  }
  return value;
}

export function asString(value: unknown, field: string): string {
  if (typeof value !== "string") {
    throw new PayloadRefusal(field, "a string");
  }
  return value;
}

export function asStringOrNull(value: unknown, field: string): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  return asString(value, field);
}

export function asInteger(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new PayloadRefusal(field, "an integer");
  }
  return value;
}

export function asIntegerOrNull(value: unknown, field: string): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  return asInteger(value, field);
}

export function asBoolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") {
    throw new PayloadRefusal(field, "a boolean");
  }
  return value;
}

export function asStringList(value: unknown, field: string): readonly string[] {
  return asArray(value, field).map((item, index) =>
    asString(item, `${field}[${index.toString()}]`)
  );
}

/** Narrow to one member of a generated literal union, or refuse by name. */
export function asMember<T extends string>(
  value: unknown,
  field: string,
  members: readonly T[]
): T {
  const text = asString(value, field);
  const member = members.find((candidate) => candidate === text);
  if (member === undefined) {
    throw new PayloadRefusal(field, `one of ${members.join(", ")}`);
  }
  return member;
}
