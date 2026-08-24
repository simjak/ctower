/**
 * The shell's map. Two workspaces, and every destination the product will have.
 *
 * The split is what a destination is *about*. A company workspace holds the
 * things that are true of the tenant however many projects it runs — the
 * company's own definition, the crews, the harnesses they run on, the inbox,
 * the console's admissions. A project workspace holds the things that are only
 * ever about one project, and the rail's project dropdown says which one.
 *
 * `DESIGN.md`: an unbuilt destination renders honestly — dimmed, with its
 * reason on focus — never a dead route and never a pretend page. So the list is
 * the whole product, and `built` is the only thing that changes as features
 * land. Labels are the operator's jobs; not one of them is an API operation.
 */
export type Workspace = "COMPANY" | "PROJECT";

export type DestinationKey =
  | "company"
  | "projects"
  | "agents"
  | "crews"
  | "harnesses"
  | "inbox"
  | "admin"
  | "tickets"
  | "board"
  | "workflows"
  | "requests"
  | "lanes";

export interface Destination {
  readonly key: DestinationKey;
  readonly label: string;
  readonly workspace: Workspace;
  /** A destination is built when a real screen answers on it. */
  readonly built: boolean;
}

export const DESTINATIONS: readonly Destination[] = [
  { key: "company", label: "Company", workspace: "COMPANY", built: true },
  { key: "projects", label: "Projects", workspace: "COMPANY", built: true },
  { key: "agents", label: "Agents", workspace: "COMPANY", built: true },
  { key: "crews", label: "Crews", workspace: "COMPANY", built: true },
  { key: "inbox", label: "Inbox", workspace: "COMPANY", built: true },
  { key: "harnesses", label: "Harnesses", workspace: "COMPANY", built: true },
  { key: "admin", label: "Admin", workspace: "COMPANY", built: true },
  { key: "tickets", label: "Tickets", workspace: "PROJECT", built: true },
  { key: "board", label: "Board", workspace: "PROJECT", built: true },
  { key: "workflows", label: "Workflows", workspace: "PROJECT", built: true },
  { key: "requests", label: "Requests", workspace: "PROJECT", built: true },
  { key: "lanes", label: "Lanes", workspace: "PROJECT", built: false },
];

export const WORKSPACES: readonly Workspace[] = ["COMPANY", "PROJECT"];

/**
 * The one destination the rail draws as a section of its own rather than as a
 * link.
 *
 * T-025 §1: the operator asked for his staff in the sidebar, by name, with one
 * way to the whole list. So the rail carries an AGENTS section whose rows are
 * the agents themselves, and the section is how this destination is reached —
 * a link labelled "Agents" beside it would be a second door to one room.
 * It stays in the map because it is still a destination: it has an address, a
 * screen, and a `built` flag that says whether either exists yet.
 */
export const RAIL_SECTION: DestinationKey = "agents";

export function destinationsIn(workspace: Workspace): readonly Destination[] {
  return DESTINATIONS.filter((destination) => destination.workspace === workspace);
}

/** The destinations of a workspace the rail draws as ordinary links. */
export function linksIn(workspace: Workspace): readonly Destination[] {
  return destinationsIn(workspace).filter((destination) => destination.key !== RAIL_SECTION);
}

/** Whether a screen is about one project rather than about the company. */
export function scopedToProject(key: DestinationKey): boolean {
  return DESTINATIONS.find((destination) => destination.key === key)?.workspace === "PROJECT";
}

/**
 * Where the address says the operator is.
 *
 * A screen is a link: `?at=board&project=ctower` reopens exactly what was being
 * looked at, and `?at=tickets&project=ctower&ticket=<id>` is the same screen one
 * level in. Only a built destination is honoured, so a stale link to a screen
 * that does not exist yet lands on the shell's own first destination rather than
 * on a blank pane.
 */
export function destinationFromSearch(search: string): DestinationKey | null {
  const asked = new URLSearchParams(search).get("at");
  const found = DESTINATIONS.find((destination) => destination.key === asked);
  return found?.built === true ? found.key : null;
}

/** The project the address is pointed at, when it names one. */
export function projectFromSearch(search: string): string | null {
  const asked = new URLSearchParams(search).get("project");
  return asked === null || asked === "" ? null : asked;
}

/**
 * The address a destination is written as, path unchanged.
 *
 * A project workspace screen carries its project, because the screen means
 * nothing without it: sending someone `?at=board` alone would open whichever
 * project their own console happened to remember. A company workspace screen
 * carries none, because none would be true of it.
 *
 * Nothing else survives. A ticket id belongs to the project it was raised in,
 * so moving to another project — or to another screen — drops it rather than
 * carrying a key into an address where it names nothing.
 */
export function addressFor(
  key: DestinationKey,
  project: string | null,
  /** What the destination itself needs to reopen on: a ticket, a raise. */
  place: Readonly<Record<string, string>> = {}
): string {
  const asked = new URLSearchParams({ at: key });
  if (project !== null && scopedToProject(key)) {
    asked.set("project", project);
  }
  for (const [name, value] of Object.entries(place)) {
    asked.set(name, value);
  }
  return `?${asked.toString()}`;
}
