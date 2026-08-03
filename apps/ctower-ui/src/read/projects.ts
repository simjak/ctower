/**
 * The projects this fleet runs, declared once.
 *
 * The operator has three and says so: *"see manibo ctower and bh-loop boards, I
 * dont need other boards, I have three active projects"*. Two screens need that
 * list — the Board scopes its read by project key, and Metrics measures each
 * project's trunk — and before this it was written out in `mergeHistory.ts` and
 * would have been written out again in the Board. One list, both screens: adding
 * a fourth project is one edit here, and no screen can drift to a different set.
 *
 * Three spellings are kept apart on purpose, because they are three different
 * things and collapsing them would break something:
 *
 * * `key` is what the **record** scopes by — `/v1/board?project_key=…`, whose
 *   contract pattern is `^[a-z][a-z0-9-]{2,63}$`. This is also what the operator
 *   calls the project.
 * * `scopeToken` is what the **vendored stylesheet** keys its Metrics radios on
 *   (`#s-bhloop`). `design-reference/app.css` is re-vendored byte-for-byte from
 *   the approved mockups and is not edited to suit this file.
 * * `deliveryLabel` is the overlay spelling SPEC uses for the same project
 *   (SPEC.md line 1253 names `lastmachines`/`bh-loop`). Metrics shows it because
 *   that is the delivery context; the Board shows `key`, because that is the
 *   operator's word and the record's.
 *
 * Every repository root is overridable, so a copy can be measured — the same
 * variables that already existed for Metrics. No new environment variable.
 */

export interface ConfiguredProject {
  /** The project key the record's read API scopes by. */
  readonly key: string;
  /** The token the vendored Metrics stylesheet keys its scope radios on. */
  readonly scopeToken: string;
  /** SPEC's overlay spelling, for the delivery surface. */
  readonly deliveryLabel: string;
  /** The repository whose trunk history Metrics measures. */
  readonly root: string;
}

function environment(name: string, fallback: string): string {
  const value = process.env[name];
  return value === undefined || value === "" ? fallback : value;
}

export function configuredProjects(): readonly ConfiguredProject[] {
  return [
    {
      key: "manibo",
      scopeToken: "manibo",
      deliveryLabel: "lastmachines",
      root: environment("CTOWER_UI_PROJECT_MANIBO", "/srv/projects/manibo"),
    },
    {
      key: "ctower",
      scopeToken: "ctower",
      deliveryLabel: "ctower",
      root: environment("CTOWER_UI_PROJECT_CTOWER", "/srv/projects/ctower"),
    },
    {
      key: "bh-loop",
      scopeToken: "bhloop",
      deliveryLabel: "bh-loop",
      root: environment("CTOWER_UI_PROJECT_BHLOOP", "/srv/projects/bh-loop"),
    },
  ];
}

/**
 * The project a screen opens on when the reader has not chosen one.
 *
 * This is a ctower surface reading ctower's own instance, so it opens on ctower
 * — the same rule the Inbox uses to open on the ctower seat. The tab order is
 * the operator's own, and the default is not the first tab.
 */
export function defaultProjectKey(): string {
  const home = configuredProjects().find((project) => project.key === "ctower");
  return home?.key ?? configuredProjects()[0]?.key ?? "ctower";
}

/** The requested project when the fleet configures it, otherwise the default. */
export function selectedProjectKey(requested: string | null): string {
  const known = configuredProjects().find((project) => project.key === requested);
  return known?.key ?? defaultProjectKey();
}
