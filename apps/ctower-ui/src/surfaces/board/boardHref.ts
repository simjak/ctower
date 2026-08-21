import { ALL_LANES, ALL_SOURCES } from "./lanes";

/** Everything this screen holds in the URL, in one place. */
export interface BoardSelection {
  readonly project: string;
  readonly source: string;
  readonly lane: string;
}

/**
 * The board's address, built once.
 *
 * Three controls narrow this screen and each of them used to write the URL
 * itself, which is how choosing a source silently threw the reader back to the
 * default project: a control that writes the address alone can only carry the
 * choice it owns. Every selection is server-rendered from these parameters, so
 * dropping one does not merely lose a filter — it re-reads the record for a
 * project the reader did not ask for and shows the answer under their old tabs.
 *
 * The project is always written, default included. The board is read scoped and
 * the foot names the scope; an address that omits it is one copy-paste away
 * from meaning a different board tomorrow.
 */
export function boardHref(selection: BoardSelection): string {
  const query = new URLSearchParams({ project: selection.project });
  if (selection.source !== ALL_SOURCES) {
    query.set("source", selection.source);
  }
  if (selection.lane !== ALL_LANES) {
    query.set("lane", selection.lane);
  }
  return `/board?${query.toString()}`;
}
