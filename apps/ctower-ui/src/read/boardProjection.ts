import { NO_BOARD_ROW_HERE, NO_STAGES_HERE } from "./futureSources";
import { mapReading } from "./reading";
import type { BoardCard, BoardEntry, BoardSnapshot, Reading } from "./interface";

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

/** One already-decided value for the Board-card context renderer. */
export interface BoardContextValue {
  readonly value: string;
  readonly detail?: string | undefined;
}

/**
 * The five-member Board-card context set, projected into display facts.
 *
 * This is the only browser module that narrows the contract discriminants. A
 * component receives strings that are ready to render and cannot accidentally
 * flatten `unknown`, `not_waiting`, declared absence, or
 * `no_qualifying_checkpoint` into an omitted row.
 */
export interface BoardCardContext {
  readonly tenant: BoardContextValue;
  readonly changes: readonly BoardContextValue[];
  readonly labels: readonly BoardContextValue[];
  readonly humanWaiting: BoardContextValue & { readonly attention: boolean };
  readonly deliverySurface: BoardContextValue & { readonly details?: readonly string[] };
}

function contextValue(value: string, detail?: string): BoardContextValue {
  return detail === undefined ? { value } : { value, detail };
}

function changeIdentity(identity: string): string {
  return /^\d+$/.test(identity) ? `#${identity}` : identity;
}

function identitySurface(
  name: string,
  field: {
    readonly state: "declared_present" | "declared_absent" | "undeclared";
    readonly identity: string | null;
  }
): string {
  if (field.state === "undeclared") {
    return `${name} · STATE_UNKNOWN (undeclared)`;
  }
  if (field.state === "declared_absent") {
    return `${name} · declared absent`;
  }
  return `${name} · ${field.identity ?? "STATE_UNKNOWN (identity missing)"}`;
}

function environmentSurface(field: {
  readonly state: "declared_present" | "declared_absent" | "undeclared";
  readonly environments: readonly string[];
}): string {
  if (field.state === "undeclared") {
    return "non-production environments · STATE_UNKNOWN (undeclared)";
  }
  if (field.state === "declared_absent") {
    return "non-production environments · declared absent";
  }
  return `non-production environments · ${field.environments.join(", ")}`;
}

export function boardCardContextFor(card: BoardCard): BoardCardContext {
  const tenant =
    card.tenantDisplayIdentity.state === "known"
      ? contextValue(card.tenantDisplayIdentity.displayName)
      : contextValue(`STATE_UNKNOWN · ${card.tenantDisplayIdentity.missingSource}`);
  const changes =
    card.changeReferences.length === 0
      ? [contextValue("none recorded")]
      : card.changeReferences.map((change) =>
          contextValue(
            `${change.repository} ${changeIdentity(change.change_identity)} · ${change.reference}`,
            `recorded ${change.recorded_at}`
          )
        );
  const labels =
    card.appliedLabels.length === 0
      ? [contextValue("none applied")]
      : card.appliedLabels.map((label) =>
          contextValue(
            label.label,
            `${label.label_key} · vocabulary ${label.vocabulary_revision.toString()} · applied ${label.applied_at}`
          )
        );
  const humanWaiting =
    card.humanWaiting.state === "waiting"
      ? {
          value: `${card.humanWaiting.kind_key} · ${card.humanWaiting.reason_code}`,
          detail: `finding ${card.humanWaiting.finding_id}`,
          attention: true,
        }
      : { value: "not waiting", attention: false };
  const availability = card.deliverySurfaceAvailability;
  const deliverySurface =
    availability.state === "no_qualifying_checkpoint"
      ? { value: "no qualifying checkpoint" }
      : {
          value: `checkpoint ${availability.checkpoint_key}`,
          details: [
            identitySurface("landing boundary", availability.landing_boundary),
            environmentSurface(availability.non_production_environments),
            identitySurface(
              "externally effective outcome",
              availability.externally_effective_outcome
            ),
          ],
        };
  return { tenant, changes, labels, humanWaiting, deliverySurface };
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

/**
 * The stage a workflow has this ticket in, as its own reading.
 *
 * The board projection folds `workflow.changed` server-side and serves the
 * result as the card's `stage_key`, so a ticket's *current* stage is a served
 * fact — it is the ordered stage list its `workflow_ref` declares that no read
 * carries, and that is what stops the surface drawing a position rather than a
 * name.
 *
 * A card that carries no stage is the record answering and holding none; a
 * board read that did not land is not an answer at all. Deriving a reading
 * rather than a nullable keeps those two apart all the way to the screen.
 */
export function stageOf(card: Reading<BoardCard>): Reading<string> {
  return mapReading(card, (row) =>
    row.stageLabel === null
      ? ({ state: "absent", source: NO_STAGES_HERE } as const)
      : ({ state: "present", value: row.stageLabel } as const)
  );
}
