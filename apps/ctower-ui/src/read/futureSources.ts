import type { FutureSource } from "./interface";

/**
 * Every "nothing to show here" this surface declares, in one reviewable table.
 *
 * Round-3 QA (#241) found nine unrelated panels all reading *lands with #186*.
 * #186 is the operator-channel feed; it covers none of them. A pointer that
 * points everywhere points nowhere, and the panels' whole value is that they
 * refuse to invent data and say where the real thing is coming from — which is
 * worth nothing if the pointer is wrong.
 *
 * So a citation is a fact, checked like any other fact on this surface:
 *
 * * it is written **once**, here, and imported by the screens. No screen builds
 *   a `FutureSource` inline, so no citation can be minted without passing this
 *   table — `tests/repository/test_declared_sources.py` fails closed on one that
 *   does;
 * * each cited item carries the sentence saying how it covers *this exact fact*,
 *   and that sentence is rendered on the chip, so a wrong citation is visible to
 *   the operator rather than only to a reviewer;
 * * where no work item is filed, `lands` is `null` and the surface says
 *   *no work item is filed for this yet*. Silence about a roadmap is honest; a
 *   number that does not cover the panel is not.
 *
 * The second distinction this table draws is **capability** versus **silence**.
 * `ticket.comment_added`, `proof.changed`, `workflow.changed` and `work.changed`
 * are recorded kinds; a ticket with none of them is a record that answered and
 * holds none, not a capability ctower lacks. Those declare `silence` and cite
 * nothing, because nothing has to land for them to fill in.
 */

type Capability = Extract<FutureSource, { absence: "capability" }>;
type Silence = Extract<FutureSource, { absence: "silence" }>;

function capability(what: string, cited: readonly [string, string] | null): Capability {
  return {
    absence: "capability",
    what,
    lands: cited === null ? null : cited[0],
    why: cited === null ? null : cited[1],
  };
}

function silence(what: string): Silence {
  return { absence: "silence", what };
}

/**
 * How a citation reads on the surface. One wording, so the roadmap pointer says
 * the same thing in a panel, on a row and in a provenance foot.
 */
export function landsText(source: FutureSource): string {
  if (source.absence === "silence") {
    return "nothing has to land: the record carries this and holds none here";
  }
  return source.lands === null
    ? "no work item is filed for this yet"
    : `lands with ${source.lands}`;
}

/* ── capabilities ctower does not have yet ─────────────────────────────────
   Each cited item was read before it was written here. Where the search found
   nothing that covers the fact, the entry cites nothing rather than the nearest
   plausible number. */

/**
 * #200 — *"Every ticket work session records who, duration, tokens, and
 * outcome"* — is the work timeline, field for field. It is the item Mission
 * Control's ctower checkpoint calls G5.
 */
export const NO_WORK_SESSIONS = capability(
  "per-session work facts — seat, duration, tokens and outcome",
  [
    "#200",
    "#200 records a session event per ticket work session carrying actor, duration, tokens and outcome — the four columns this panel is shaped for",
  ]
);

/**
 * Applied labels are one of the five members of the Board card context set.
 * D29 §1/§3 grant it and name #115 as the contract issue that carries it;
 * SPEC AC-TM-07 is the acceptance criterion.
 */
export const NO_LABELS = capability(
  "the configured label vocabulary and this ticket's applied labels",
  [
    "#115 · D29",
    "applied labels are a member of the Board card context set that #115 adds to the shared contract, drawn from the versioned label vocabulary D29 §3 makes configured data",
  ]
);

/**
 * No work item covers a *principal's* display name. AC-TM-07's display fact is
 * the **tenant's**, and the seat catalog's display labels belong to seat keys,
 * not to the principal a ticket names as custodian. So this cites nothing: the
 * previous `#186 / AC-TM-07` was a criterion about a different subject.
 */
export const NO_SEAT_NAME = capability(
  "a display name for a principal — the record carries the identifier only",
  null
);

/**
 * The one citation this surface already had right, kept and moved here so it is
 * reviewed beside the rest. #185 — *"ctower serves three projects: manibo,
 * ctower, and BH.Loop share one delivery system"* — is what puts a project fact
 * on a ticket; until it lands, the board filters on `source.kind`, which the
 * record does carry.
 */
export const NO_PROJECT_SCOPE = capability("a project fact on a ticket to scope the board by", [
  "#185 · D29",
  "#185 gives ctower three projects sharing one delivery system, which is the fact a board column or filter would scope by; D29 fixes the card's context set at five members and project is not one of them, so the board filters on the recorded source kind instead",
]);

export const NO_TICKET_BRIEF = capability(
  "a ticket brief beyond the recorded title, priority and source",
  null
);

export const NO_ACCEPTANCE_CRITERIA = capability(
  "criterion text and per-criterion verdicts on a ticket read path",
  null
);

export const NO_DRAIN_SERIES = capability(
  "the drain ledger as a machine-readable series — it exists today only as prose in the migration status note, and reading a burn-down out of prose would be a guess with a chart around it",
  null
);

export const NO_SESSION_STATES = capability(
  "a session's recorded state transitions — dispatched, briefed, working, gated",
  null
);

export const NO_METRIC_DEFINITIONS = capability(
  "a metric definition file the kernel reads, and the deploy and per-session token records the proposed examples would join against",
  null
);

/* ── facts ctower records, of which this subject holds none ────────────────
   These cite nothing on purpose. The record answered; it simply holds none for
   this ticket, and there is no work item to wait for. */

export const NO_STAGES_HERE = silence("recorded workflow stage for this ticket");

export const NO_WORKFLOW_REF_HERE = silence("recorded workflow run for this ticket");

export const NO_EVIDENCE_HERE = silence("recorded proof event for this ticket");

export const NO_EVENTS_HERE = silence("appended event for this ticket");

export const NO_COMMENTS_HERE = silence("recorded comment on this ticket");

export const NO_RELATIONS_HERE = silence("recorded relation on this ticket");

export const NO_BOARD_ROW_HERE = silence("board projection row for this ticket");

export const NO_PROJECT_HISTORY = silence(
  "project trunk history this surface could measure — every repository it was pointed at answered with none"
);

export const NO_TICKET_ON_BOARD = silence("ticket on the board projection");

/** Every declared source, so a test can assert the table without scraping. */
export const DECLARED_SOURCES: Readonly<Record<string, FutureSource>> = {
  NO_WORK_SESSIONS,
  NO_LABELS,
  NO_SEAT_NAME,
  NO_PROJECT_SCOPE,
  NO_TICKET_BRIEF,
  NO_ACCEPTANCE_CRITERIA,
  NO_SESSION_STATES,
  NO_DRAIN_SERIES,
  NO_METRIC_DEFINITIONS,
  NO_STAGES_HERE,
  NO_WORKFLOW_REF_HERE,
  NO_EVIDENCE_HERE,
  NO_EVENTS_HERE,
  NO_COMMENTS_HERE,
  NO_RELATIONS_HERE,
  NO_BOARD_ROW_HERE,
  NO_PROJECT_HISTORY,
  NO_TICKET_ON_BOARD,
};
