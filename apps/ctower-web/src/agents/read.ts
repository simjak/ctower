import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { harnessNamed } from "./harnesses";
import type { Agent } from "./AgentRow";

/**
 * The agents this company records, as people rather than as components.
 *
 * An agent is authored twice over: a `persona` carries the name it speaks
 * under, and an `agent_profile` pairs that persona with the harness it runs on.
 * Neither reference renders. The profile's `persona_ref` is resolved to the
 * name a person recognises, and its `harness_ref` to that harness's adapter,
 * which `harnesses.ts` turns into words somebody says out loud.
 *
 * **What the record does not keep, this does not invent.** There is no job
 * title on a persona, no model on a profile, and nothing ties a recorded run to
 * an agent — the schemas are closed (`additionalProperties: false`) and none of
 * the three fields exists. So `role`, `model`, `lastActive` and `status` come
 * back empty and the screen says once, in one line, what is missing. A row that
 * filled them from a near-enough field would be the console making up staff.
 *
 * The order is the record's. The export is normalized and deterministic
 * (`SPEC.md`, § CompanyBundle), so an agent appears where the company's own
 * record puts it; sorting here would overrule the record with a rule no
 * authored document declares.
 */
export interface ListedAgent {
  /** The key that addresses this agent. It travels; it does not render. */
  readonly key: string;
  readonly agent: Agent;
}

export function agentsIn(document: CompanyBundleDocument): readonly ListedAgent[] {
  const personas = namedBy(document, "persona", "display_name");
  const adapters = namedBy(document, "harness", "adapter");
  const listed: ListedAgent[] = [];
  for (const resource of document.resources) {
    if (resource.component.kind !== "agent_profile") {
      continue;
    }
    const persona = text(resource, "persona_ref");
    const harness = text(resource, "harness_ref");
    listed.push({
      key: resource.component.key,
      agent: {
        // A profile whose persona is not in this bundle has no name here. The
        // key would be one, and printing it is the thing this screen exists to
        // stop, so the row says the one true thing instead.
        name: (persona === null ? null : (personas.get(persona) ?? null)) ?? "Unnamed",
        role: null,
        model: null,
        harness: harnessNamed(harness === null ? null : (adapters.get(harness) ?? null)),
        lastActive: null,
        status: null,
      },
    });
  }
  return listed;
}

/** What one field of one kind of component says, under the reference that pins it. */
function namedBy(
  document: CompanyBundleDocument,
  kind: string,
  field: string
): ReadonlyMap<string, string> {
  const named = new Map<string, string>();
  for (const resource of document.resources) {
    if (resource.component.kind !== kind) {
      continue;
    }
    const value = text(resource, field);
    if (value !== null) {
      named.set(`${resource.component.key}@${String(resource.component.revision)}`, value);
    }
  }
  return named;
}

function text(resource: CompanyBundleResource, field: string): string | null {
  const value = resource.payload[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}
