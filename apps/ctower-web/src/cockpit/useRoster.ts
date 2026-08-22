import { useMemo, useState } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { findCrew, firstCrew, rosterOf } from "./roster";
import type { Crew, Project } from "./roster";

/**
 * Which crew the cockpit is looking at.
 *
 * This is a hook rather than state inside `Cockpit` because the two things it
 * feeds now render in different places: the rail draws in the shell's single
 * column, and the panes draw in the shell's content. The selection is one fact
 * and it cannot live inside either half.
 *
 * The document is nullable because the company read has four answers that are
 * not a company, and the shell renders under all of them. No company read means
 * no roster — never an empty one standing in for an unread one, which is the
 * distinction the rest of this console is careful about too.
 */
export interface Roster {
  readonly projects: readonly Project[];
  /** The selected crew, defaulting to the first the rail draws. */
  readonly crew: Crew | null;
  readonly pick: (subject: string) => void;
}

export function useRoster(document: CompanyBundleDocument | null): Roster {
  const [picked, setPicked] = useState<string | null>(null);
  const projects = useMemo(() => (document === null ? [] : rosterOf(document)), [document]);
  return {
    projects,
    crew: findCrew(projects, picked) ?? firstCrew(projects),
    pick: setPicked,
  };
}
