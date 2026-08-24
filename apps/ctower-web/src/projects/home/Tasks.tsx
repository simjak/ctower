import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { TicketsView } from "../../tickets/TicketsView";
import type { ProjectFacts } from "../read";

/**
 * The project's tickets tab.
 *
 * There is one tickets surface in the product and this is where it mounts: the
 * rail's Tickets opens the project's own screen on this tab, so the tab is
 * local navigation inside one destination rather than a second way to reach the
 * same read. Everything the screen does — the list, the columns, raising one —
 * is `TicketsView`, which the plain list mounts too, so the two entry points
 * cannot drift into two different screens.
 *
 * Where a row goes is the caller's, because the two mount points write the
 * address differently.
 */
export function Tasks({
  project,
  document,
  onOpen,
}: {
  readonly project: ProjectFacts;
  /** The company record the people and project pickers are drawn from. */
  readonly document: CompanyBundleDocument;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  return <TicketsView projectKey={project.key} document={document} onOpen={onOpen} />;
}
