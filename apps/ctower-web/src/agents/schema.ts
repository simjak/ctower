import profile from "../../../../contracts/components/agent-profile.schema.json";
import persona from "../../../../contracts/components/persona.schema.json";

/**
 * What the record will accept for an agent, read out of the record's own
 * contracts.
 *
 * An agent is two authored components — the persona it speaks as and the
 * profile pairing that persona with a harness — so both schemas are imported
 * rather than restated. The rule this form enforces before Review and the rule
 * the kernel enforces at apply are then the same bytes, and a payload that
 * would come back `bundle-schema-invalid` is unreachable instead of merely
 * unlikely.
 *
 * The absences below are the interesting part. Both schemas are
 * `additionalProperties: false`, so what they do not list, an agent cannot
 * carry: no title, no reports-to, no trust level, no model, no thinking effort,
 * no turn limit, no heartbeat. The New Agent screen draws every one of those as
 * a field the record has nowhere to keep, which is why this module exports the
 * required lists — a screen that guesses which fields exist eventually offers
 * one that does not.
 */
export const PERSONA_SCHEMA_REF: string = persona.properties.schema.const;
export const PROFILE_SCHEMA_REF: string = profile.properties.schema.const;

/** Every field the record insists each half of an agent carries. */
export const PERSONA_REQUIRED: readonly string[] = persona.required;
export const PROFILE_REQUIRED: readonly string[] = profile.required;

/** How long the record lets an agent's name be. */
export const NAME_LENGTH: { readonly min: number; readonly max: number } = {
  min: persona.properties.display_name.minLength,
  max: persona.properties.display_name.maxLength,
};

/**
 * The pattern the record holds a component key to, as the record wrote it —
 * anchors included, so this is the contract's string rather than a widened
 * version of it that would accept a key the kernel refuses.
 */
export function keyPattern(): RegExp {
  return new RegExp(persona.properties.key.pattern);
}

/** The pattern a pinned reference takes: a key, then the exact revision. */
export function referencePattern(): RegExp {
  return new RegExp(profile.properties.persona_ref.pattern);
}

/** The one value the contract allows for a component nothing has run yet. */
export const NOT_EXERCISED: string = profile.properties.execution.const;
