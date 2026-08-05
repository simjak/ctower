import { NO_BOARD_ROW_HERE } from "./futureSources";
import { mapReading } from "./reading";
import type {
  BoardCard,
  BoardEntry,
  BoardSnapshot,
  Reading,
  TenantDisplayIdentity,
} from "./interface";

/**
 * Projections over the board's per-card ticket readings.
 *
 * These live in the read layer, not in a surface, because they are the only
 * place outside `frame/Declared.tsx` that inspects a reading's state — and they
 * turn it into a typed summary a screen can render without ever seeing a
 * `Reading` it might flatten.
 */

/**
 * The three things a scoped board answer can be, decided once here so the
 * surface and the repository's `surface_fixtures.ts` driver agree on the same
 * values. A 0-of-0 answer is never "normal": it is either a restarting/fresh
 * instance or a genuinely not-yet-imported project, and the two are told apart
 * by the portfolio's watermark in the same render.
 */
export type BoardEmptyKind = "normal" | "restart-fresh" | "true-empty-project";

/**
 * The values the empty-board decision inspects. A `BoardSnapshot` satisfies the
 * first two fields directly; `portfolioWatermark` is the unscoped board's
 * projection watermark read in the same render, or `null` when that read did
 * not answer.
 */
export interface BoardEmptyProbe {
  readonly projectionWatermark: number;
  readonly entries: readonly unknown[];
  readonly portfolioWatermark: number | null;
}

/**
 * Which of the three kinds a scoped board answer is.
 *
 * The case the P0 this guard prevents: a record-read path answered `watermark
 * 0 of 0` with zero cards and the served board rendered that empty answer as an
 * empty board while cards sat safe at a high watermark. An empty answer
 * rendered as truth is the honesty defect this surface already guards, one
 * level deeper, so a board that answers zero cards *at watermark 0* is never
 * rendered as a normal empty board.
 *
 * The two ways a board answers watermark 0 with zero cards are told apart by
 * the portfolio's watermark in the same render:
 *
 * * portfolio ALSO 0 (or the portfolio read did not answer) — the instance has
 *   nothing accumulated anywhere the surface can see: restarting, rebuilding,
 *   or genuinely fresh. This is the refusal block.
 * * portfolio > 0 — the instance plainly holds records, so THIS project simply
 *   has not been imported yet: a true-empty project, rendered as its own named
 *   block pointing at the portfolio view.
 *
 * NO other answer changes: any watermark > 0 (a genuinely empty PROJECT under a
 * nonzero watermark included), and any board with cards, is "normal".
 */
export function boardEmptyKind(probe: BoardEmptyProbe): BoardEmptyKind {
  if (probe.projectionWatermark > 0 || probe.entries.length > 0) {
    return "normal";
  }
  // portfolio == 0 OR unreadable (null): never claim the portfolio holds
  // records without an answer to the contrary, so both fold to the refusal.
  return probe.portfolioWatermark === null || probe.portfolioWatermark === 0
    ? "restart-fresh"
    : "true-empty-project";
}

/**
 * The portfolio watermark to hand the empty-board decision, read only when it
 * is needed.
 *
 * Lives in the read layer because it inspects the readings' states (the one
 * place outside `frame/Declared.tsx` that may): a present scoped board that is
 * NOT a 0-of-0 answer returns `null` without ever performing the portfolio
 * read, so a normal board never pays for a second network request. Only a
 * present 0-of-0 scoped answer triggers the lazy portfolio read that tells a
 * true-empty project (portfolio nonzero) from a restarting/fresh instance
 * (portfolio 0 or unreadable).
 */
export async function portfolioWatermarkFor(
  scoped: Reading<BoardSnapshot>,
  readPortfolio: () => Promise<Reading<BoardSnapshot> | null>
): Promise<number | null> {
  if (scoped.state !== "present") {
    // not a value to decide on; `Resolved` renders the declared state instead
    return null;
  }
  const snapshot = scoped.value;
  if (snapshot.projectionWatermark !== 0 || snapshot.entries.length !== 0) {
    // a normal board — render it; the portfolio watermark is irrelevant
    return null;
  }
  const portfolio = await readPortfolio();
  return portfolio?.state !== "present" ? null : portfolio.value.projectionWatermark;
}

/**
 * The portfolio's own entries, for the true-empty-project case's cross-project
 * view (gh#319 direction-a). Gated on `portfolioWatermarkFor`'s own verdict
 * rather than re-deciding when to read: a `null` watermark means either a
 * normal board (no portfolio read happened) or the restart-fresh refusal
 * (portfolio unreadable or 0), and neither needs entries. `readPortfolio`
 * should be the same memoized thunk passed to `portfolioWatermarkFor`, so a
 * true-empty-project answer never pays for the portfolio board twice.
 */
export async function portfolioEntriesFor(
  readPortfolio: () => Promise<Reading<BoardSnapshot> | null>,
  portfolioWatermark: number | null
): Promise<readonly BoardEntry[]> {
  if (portfolioWatermark === null) {
    return [];
  }
  const portfolio = await readPortfolio();
  return portfolio?.state === "present" ? portfolio.value.entries : [];
}

/**
 * The recorded source kind, or `null` when this card's ticket read did not
 * produce one. `null` means "not resolvable", never "no source recorded".
 */
export function sourceKindOf(entry: BoardEntry): string | null {
  return entry.ticket.state === "present" ? entry.ticket.value.source.kind : null;
}

/** Cards whose source could not be resolved, with the first reason observed. */
export interface UnresolvedSources {
  readonly count: number;
  readonly unreached: number;
  readonly reason: string | null;
}

export function unresolvedSources(entries: readonly BoardEntry[]): UnresolvedSources {
  const unresolved = entries.filter((entry) => entry.ticket.state !== "present");
  const reasons = entries.flatMap((entry) =>
    entry.ticket.state === "unavailable" ? [entry.ticket.failure.reason] : []
  );
  return {
    count: unresolved.length,
    unreached: reasons.length,
    reason: reasons[0] ?? null,
  };
}

/** The tenant chip's already-decided text, so a surface never narrows the union itself. */
export interface TenantChipFacts {
  readonly label: string;
  /** Why the tenant is unrecorded, for a `title` attribute; `undefined` when known. */
  readonly title: string | undefined;
}

/**
 * `tenantDisplayIdentity`'s `known`/`unknown` states, resolved to the text a
 * card renders. Lives here, not in the surface, for the same reason
 * `boardEmptyKind` does: this module is the one place outside
 * `frame/Declared.tsx` that may inspect a `.state` discriminant.
 */
export function tenantChipFor(identity: TenantDisplayIdentity): TenantChipFacts {
  return identity.state === "known"
    ? { label: identity.displayName, title: undefined }
    : { label: "tenant unrecorded", title: identity.missingSource };
}

/**
 * This ticket's board row, as a reading.
 *
 * A board read that did not answer stays unavailable rather than becoming "no
 * lane recorded": the ticket screen must not imply the projection holds nothing
 * for this ticket when the truth is that the projection was not reached.
 */
export function cardFor(board: Reading<BoardSnapshot>, ticketId: string): Reading<BoardCard> {
  return mapReading(board, (snapshot): Reading<BoardCard> => {
    const found = snapshot.entries.find((entry) => entry.card.ticketId === ticketId);
    return found === undefined
      ? { state: "absent", source: NO_BOARD_ROW_HERE }
      : { state: "present", value: found.card };
  });
}
