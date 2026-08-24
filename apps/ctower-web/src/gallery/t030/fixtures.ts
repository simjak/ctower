import type { ProjectChoice } from "../../shell/ProjectSwitcher";

/**
 * The project the T-030 bench draws with, and it is a real one.
 *
 * These are the exact bytes of `packs/components/projects/ctower.control-plane`
 * — the name, the prefix, the repository, the one goal it serves — so the four
 * rows the record can already answer are answered with the record's own words.
 * Everything else on the bench is drawn as a proposal and marked as one; no
 * fixture here pretends a field exists.
 */
export const HERE: ProjectChoice = { key: "ctower", name: "Ctower control plane", prefix: "CTW" };

export const PROJECTS: readonly ProjectChoice[] = [
  { key: "bh-loop", name: "BH Loop", prefix: "BHL" },
  HERE,
  { key: "manibo", name: "Manibo delivery", prefix: "MNB" },
];

export const COMPANY = "Manibo";

/** `repository_ref: repository:github/simjak/ctower`, as a person reads it. */
export const REPOSITORY = {
  label: "github/simjak/ctower",
  url: "https://github.com/simjak/ctower",
};

/** `goal_refs: ["company.trusted-delivery@1"]`, resolved to the goal's name. */
export const GOALS: readonly string[] = ["Trusted delivery"];

/**
 * The company's secret bindings, which is the whole of what an environment row
 * may point at. `company.bundle.yaml` declares one; the second is drawn to show
 * a list, and both are names of bindings rather than values of anything.
 */
export const BINDINGS: readonly string[] = ["SOURCE_CONTROL_TOKEN", "REGISTRY_TOKEN"];

/**
 * How a missing field is missing.
 *
 * The task asked for two marks and the record answers with four. Two of the
 * seven things this tab draws and cannot fill are already in the record —
 * `catalog_components.created_at` is a column, `lifecycle` and `supersedes` are
 * envelope fields — so marking them `needs-schema` would send an engineer to
 * put a clock inside a content-addressed payload. Each mark names a different
 * owner, which is the only reason a mark is worth drawing.
 */
export type Disposition = "record-backed" | "needs-schema" | "needs-read" | "needs-ceremony";

export const LEGEND: readonly { readonly mark: Disposition; readonly means: string }[] = [
  { mark: "record-backed", means: "The bundle carries it. Renders today." },
  { mark: "needs-schema", means: "Nothing holds it. Waits for a new project contract." },
  { mark: "needs-read", means: "The record holds it; the export does not carry it." },
  { mark: "needs-ceremony", means: "The record holds it; no screen writes it yet." },
];

export const MARK_LABEL: Readonly<Record<Disposition, string>> = {
  "record-backed": "record-backed",
  "needs-schema": "needs schema",
  "needs-read": "needs read",
  "needs-ceremony": "needs ceremony",
};

/** Why each row carries the mark it carries, in the words the ticket uses. */
export const WHY: Readonly<Record<string, string>> = {
  name: "display_name",
  prefix: "prefix",
  description: "proposed: description, 1–500 characters",
  status: "proposed: status, a closed set of four",
  goals: "goal_refs, resolved to each goal's name",
  created: "catalog_components.created_at, not exported",
  updated: "catalog_component_revisions.created_at, not exported",
  env: "proposed: env, each entry a name and a chosen binding",
  repository: "repository_ref, rendered as a link",
  archive: "lifecycle and supersedes, already on the envelope",
};
