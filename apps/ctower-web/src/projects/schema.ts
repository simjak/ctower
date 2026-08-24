import authored from "../../../../contracts/components/project.schema.json";

/**
 * What the record will accept for a project, read out of the record's own
 * contract.
 *
 * `contracts/components/project.schema.json` is the authored schema the kernel
 * validates a `ctower.project/v1` payload against; a payload that fails it
 * comes back `bundle-schema-invalid`. This module imports that file rather than
 * restating it, so the rule the browser enforces before Review and the rule the
 * server enforces at apply are the same bytes. Restating the patterns here
 * would put a second copy of the contract in a place nothing checks, and the
 * two would drift the first time the contract moved.
 *
 * Nothing here is a JSON Schema evaluator. Only the constraints this form can
 * act on are read — a pattern, a length, a required list — because the point is
 * to tell an operator which field to fix, and a generic validator answers a
 * different question.
 */
const PROPERTIES = authored.properties;

/** Every field the record insists a project carries. */
export const REQUIRED: readonly string[] = authored.required;

/**
 * The pattern the record holds a field to, as the record wrote it.
 *
 * Anchored where the schema anchors it: these patterns already carry `^` and
 * `$`, so the expression is the contract's string and not a widened version of
 * it that would accept a value the kernel refuses.
 */
export function patternFor(field: PatternedField): RegExp {
  return new RegExp(PROPERTIES[field].pattern);
}

export type PatternedField = "key" | "prefix" | "repository_ref";

/** How long the record lets a display name be. */
export const NAME_LENGTH: { readonly min: number; readonly max: number } = {
  min: PROPERTIES.display_name.minLength,
  max: PROPERTIES.display_name.maxLength,
};

/** The schema every project payload declares itself to be. */
export const PROJECT_SCHEMA_REF: string = PROPERTIES.schema.const;

/** How many goals the record insists a project serves. */
export const GOALS_AT_LEAST: number = PROPERTIES.goal_refs.minItems;
