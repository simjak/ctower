import { readJsonl } from "./jsonl";
import { noneOf, unreadOf, valueOf } from "./maybe";
import { escapesPath } from "./paths";
import { redacted } from "./redact";
import { asRecord, asString, asStringOrNull } from "../json";
import type { Accountability, LadderRung, LadderStep } from "../interface";

/**
 * Interim source: the escapes ledger, and the autonomy ladder it moves a seat
 * along.
 *
 * An **escape** is a defect the operator, a customer or production found *after*
 * a seat signed the thing. The fleet records one per line in
 * `state/escapes.jsonl`, charged to a seat.
 *
 * Nothing records a seat's current rung. `board/accountability.md` says tiers
 * are tracked per seat per project in `board/crew-kpis.md`, and that file
 * carries a model scoreboard, not a rung — so the rung on this surface is
 * **derived from the ledger against the ladder's own thresholds**, and the panel
 * says so. In particular a seat the ledger charges nothing is TRUSTED *by
 * default*, not by measurement: the ladder is entered by five consecutive
 * verified-clean ships, and no record on this fleet counts ships. Drawing that
 * default as a promotion would be the one number an operator would believe
 * without checking.
 *
 * The ledger line carries no project, so the count is the seat's across the
 * whole fleet even though the ladder is scoped per seat per project. That gap
 * is stated on the screen rather than closed by a guess.
 */

/** The ladder, quoted from `board/accountability.md`. */
const LADDER: readonly LadderStep[] = [
  {
    rung: "TRUSTED",
    label: "Trusted",
    what: "may sign alone; work merges on its own signature",
    entered: "5 consecutive verified-clean ships in that seat; left on 1 escape",
  },
  {
    rung: "WATCHED",
    label: "Watched",
    what: "every signature needs a co-sign from a different seat or model",
    entered: "1 escape; left on 3 consecutive clean verified ships",
  },
  {
    rung: "GROUNDED",
    label: "Grounded",
    what: "may not sign at all; its work is re-verified end to end by another seat",
    entered:
      "2 escapes inside 7 days, or 1 escape that reached a customer; left on 5 clean ships under co-sign",
  },
];

const RULE_SOURCE =
  "the ladder and its thresholds are board/accountability.md's own; no record on this fleet holds a seat's current rung, so the rung above is derived from the ledger against those thresholds";
const SCOPE_NOTE =
  "the ladder is tracked per seat per project; a ledger line names a seat and no project, so this count is the seat's across the whole fleet";
const GROUNDING_WINDOW_MS = 7 * 86_400_000;
const CHARGED_CAP = 6;
const DEFECT_CAP = 240;

interface EscapeRecord {
  readonly date: string;
  readonly seat: string;
  readonly defect: string;
  readonly foundBy: string | null;
}

function escapeShape(value: unknown): EscapeRecord | null {
  try {
    const row = asRecord(value, "escapes.line");
    return {
      date: asStringOrNull(row.date, "escapes.date") ?? "",
      seat: asString(row.seat, "escapes.seat"),
      defect: asStringOrNull(row.defect, "escapes.defect") ?? "",
      foundBy: asStringOrNull(row.found_by, "escapes.found_by"),
    };
  } catch {
    return null;
  }
}

function quoted(record: EscapeRecord): string {
  const defect =
    record.defect.length > DEFECT_CAP ? `${record.defect.slice(0, DEFECT_CAP)}…` : record.defect;
  const finder = record.foundBy === null ? "" : ` · found by ${record.foundBy}`;
  return redacted(`${record.date} — ${defect}${finder}`);
}

/**
 * Where the ladder puts a seat this ledger charges `count` escapes, `recent` of
 * them inside the grounding window. Only the *entry* thresholds are decidable
 * from the ledger; the exit thresholds count clean ships, which nothing records.
 */
function rungFor(count: number, recent: number): LadderRung {
  if (recent >= 2) {
    return "GROUNDED";
  }
  return count >= 1 ? "WATCHED" : "TRUSTED";
}

function unreadable(reason: string): Accountability {
  return {
    // an unread ledger is not a clean one; the rung stays the ladder's default
    // and the count says the read failed rather than printing a zero
    rung: "TRUSTED",
    steps: LADDER,
    escapes: unreadOf(reason),
    counted: false,
    defaultNote:
      "the ledger was not read, so nothing here is a count — the rung shown is the ladder's default and no escape has been ruled out",
    charged: [],
    ledgerSource: escapesPath(),
    ruleSource: RULE_SOURCE,
    scopeNote: SCOPE_NOTE,
  };
}

/**
 * Read the ladder state for one seat. A seat this surface could not name — a
 * crew whose name matches no declared persona — gets `none` rather than the
 * fleet-wide count, because a count against "no seat" is a number about nobody.
 */
export async function readAccountability(
  seat: string | null,
  nowMs: number
): Promise<Accountability> {
  if (seat === null) {
    return {
      rung: "TRUSTED",
      steps: LADDER,
      escapes: noneOf("this crew's name matches no declared seat, so no ledger row can be its own"),
      counted: false,
      defaultNote:
        "the ladder is a seat's state and this crew has no seat, so the rung below is the ladder's default and belongs to nobody",
      charged: [],
      ledgerSource: escapesPath(),
      ruleSource: RULE_SOURCE,
      scopeNote: SCOPE_NOTE,
    };
  }

  let records: readonly EscapeRecord[];
  try {
    const scan = await readJsonl(escapesPath(), escapeShape);
    records = scan.records;
  } catch (error: unknown) {
    return unreadable(
      error instanceof Error ? error.message : "the escapes ledger could not be read"
    );
  }

  const mine = records.filter((record) => record.seat === seat);
  const recent = mine.filter((record) => {
    const at = Date.parse(record.date);
    return !Number.isNaN(at) && nowMs - at <= GROUNDING_WINDOW_MS;
  }).length;
  const rung = rungFor(mine.length, recent);
  return {
    rung,
    steps: LADDER,
    escapes: valueOf(mine.length),
    counted: mine.length > 0,
    defaultNote:
      mine.length > 0
        ? null
        : `the ledger holds ${String(records.length)} escapes and charges none of them to this seat; the ladder is entered by 5 consecutive verified-clean ships, which no record on this fleet counts, so TRUSTED here is the ladder's default rather than a measured promotion`,
    charged: mine.slice(-CHARGED_CAP).reverse().map(quoted),
    ledgerSource: escapesPath(),
    ruleSource: RULE_SOURCE,
    scopeNote: SCOPE_NOTE,
  };
}
