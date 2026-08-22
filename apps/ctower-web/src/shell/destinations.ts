/**
 * The shell's map. Five groups, and every destination the product will have.
 *
 * `DESIGN.md`: an unbuilt destination renders honestly — dimmed, with its
 * reason on focus — never a dead route and never a pretend page. So the list is
 * the whole product, and `built` is the only thing that changes as features
 * land. Labels are the operator's jobs; not one of them is an API operation.
 */
export type GroupName = "LIVE" | "WORK" | "TEAM" | "RUNTIME" | "SYSTEM";

export type DestinationKey =
  | "lanes"
  | "inbox"
  | "board"
  | "workflows"
  | "requests"
  | "crews"
  | "company"
  | "harnesses"
  | "projects"
  | "admin";

export interface Destination {
  readonly key: DestinationKey;
  readonly label: string;
  readonly group: GroupName;
  /** A destination is built when a real screen answers on it. */
  readonly built: boolean;
}

export const DESTINATIONS: readonly Destination[] = [
  { key: "lanes", label: "Lanes", group: "LIVE", built: false },
  { key: "inbox", label: "Inbox", group: "LIVE", built: false },
  { key: "board", label: "Board", group: "WORK", built: false },
  { key: "workflows", label: "Workflows", group: "WORK", built: true },
  { key: "requests", label: "Requests", group: "WORK", built: false },
  { key: "crews", label: "Crews", group: "TEAM", built: false },
  { key: "company", label: "Company", group: "TEAM", built: true },
  { key: "harnesses", label: "Harnesses", group: "RUNTIME", built: false },
  { key: "projects", label: "Projects", group: "RUNTIME", built: false },
  { key: "admin", label: "Admin", group: "SYSTEM", built: false },
];

export const GROUPS: readonly GroupName[] = ["LIVE", "WORK", "TEAM", "RUNTIME", "SYSTEM"];

export function destinationsIn(group: GroupName): readonly Destination[] {
  return DESTINATIONS.filter((destination) => destination.group === group);
}
