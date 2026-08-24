/**
 * The operator's rule, made checkable: no technical text on a rendered surface.
 *
 * Stated 2026-08-24 and binding on every screen — *"I dont need any machine
 * backend language here"*, then *"do not leave any technical text on UI"*. What
 * the record needs and the operator did not type is derived, or it sits behind
 * an explicit developer affordance. It does not sit on the screen.
 *
 * So this reads a screen exactly as a person sees it — the rendered text of the
 * whole document, shell chrome included, because a rail that prints a component
 * key is as much a violation as a page that does — and names every family it
 * finds. It reports; it never repairs, and it never guesses at intent.
 *
 * What is deliberately NOT a violation, so the grep has a stated boundary
 * rather than a judgement call per reviewer:
 *
 * - **Product names a person says out loud.** `Claude Code`, `Codex`,
 *   `claude-fable-5`. A hyphenated model name is a name, not a wire value, and
 *   none of the patterns below match one.
 * - **Numbers, times and counts.** `0.32.0`, `2026-08-24 11:12`, `12 tickets`.
 * - **The operator's own words**, whatever he typed into a field.
 *
 * Every family below is one the operator named, plus file paths, which the
 * ticket's own wording bans in the same breath.
 */

const FAMILIES = [
  {
    name: "digest",
    what: "a content digest",
    pattern: /sha256:[0-9a-f]{4,}|\b[0-9a-f]{32,}\b/g,
  },
  {
    name: "revision",
    what: "a component revision suffix",
    pattern: /@\d+\b/g,
  },
  {
    name: "uuid",
    what: "a record identifier",
    pattern: /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
  },
  {
    name: "dotted-key",
    what: "a component or document key",
    pattern: /\b[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+\b/g,
  },
  {
    name: "schema-ref",
    what: "a schema reference",
    pattern: /\bschema\/|\/v\d\b/g,
  },
  {
    name: "path",
    what: "a file path",
    pattern: /(?:^|[\s(])\/(?:srv|home|tmp|usr|var|etc|opt)\/\S+/gm,
  },
  {
    name: "repository-ref",
    what: "a repository reference",
    pattern: /\brepository:\S+/g,
  },
];

/**
 * Every hit on one screen, by family, with what it actually found.
 *
 * The samples carry the offending strings verbatim. That is the point of the
 * report — it is read by whoever has to remove them — and a report is not a
 * rendered surface.
 */
export function techTextIn(rendered) {
  const found = [];
  for (const family of FAMILIES) {
    const hits = [...new Set(rendered.match(family.pattern) ?? [])].map((hit) => hit.trim());
    if (hits.length > 0) {
      found.push({
        family: family.name,
        what: family.what,
        count: hits.length,
        samples: hits.slice(0, 4).map((hit) => hit.slice(0, 60)),
      });
    }
  }
  return found;
}

/** One line an operator can read, for a screen that carried some. */
export function techTextLine(found) {
  return found
    .map((one) => `${one.family} ×${String(one.count)} (${one.samples.join(", ")})`)
    .join(" · ");
}
