/**
 * What the console typing affordance is allowed to say, and when.
 *
 * The security shape this renders is not this surface's to soften. A grant is
 * minted by the Access control plane, lasts at most 60 seconds, carries one
 * presentation of one exact action, and binds an Actor, role-binding revision,
 * project, session reference, assignment interval, runner epoch, policy
 * revision and nonce. None of that is observable from a browser, so every value
 * below arrives from the server and none of it is derived here.
 *
 * Two consequences run through this whole module:
 *
 * * **The countdown has no authority.** `secondsLeft` exists to tell an
 *   operator how much of a minute is left, not to decide anything. The server
 *   expires the grant on its own controlled clock, and a dispatch this clock
 *   still calls live can still refuse. So a lapsed countdown locks the control
 *   — offering an action that will certainly refuse is worse than saying so —
 *   while a running one never promises the dispatch will be admitted.
 * * **A grant covers one exact text.** The ceremony confirms bytes the server
 *   canonicalized and digested; changing them afterwards is the digest-confusion
 *   abuse class. This surface cannot recompute a digest, and would be wrong to
 *   try, so it compares the field against the words that were confirmed and
 *   says the grant no longer covers them.
 *
 * `docs/specs/crew-console.md` is the specification; the exact controls are
 * `docs/security/console-q3-typing-cso.md` CT-C01..CT-C08. The rendered states
 * are the approved compare board at `bc822f5`.
 */

/** The two actions the closed vocabulary admits. Nothing else is nameable. */
export type ConsoleAction = "paste_text" | "submit";

/**
 * A canonicalization the server performed and has not granted anything for.
 *
 * Every count and digest here is server-derived. `planned` exceeds `requested`
 * by the one ASCII space `bin/mux` prepends, which is a fact about the pinned
 * adapter revision rather than arithmetic this surface may do.
 */
export interface Ceremony {
  readonly action: ConsoleAction;
  /** The words as the operator wrote them, held by this browser, never echoed back. */
  readonly text: string;
  readonly requestedBytes: number;
  readonly plannedBytes: number;
  readonly digest: string;
  readonly into: SessionBinding;
  readonly reauthenticatedText: string;
}

/** The incarnation a grant would bind. A rename or a new epoch is a different one. */
export interface SessionBinding {
  readonly crew: string;
  readonly incarnation: number;
  readonly runnerEpoch: number;
  readonly assignmentSequence: number;
}

/** A minted grant, exactly as the control plane described it. */
export interface LiveGrant {
  readonly grantId: string;
  /** The server's own expiry stamp. This surface counts towards it and decides nothing. */
  readonly expiresAt: string;
  /** The whole life the control plane granted, so the bar has a denominator. */
  readonly grantedSeconds: number;
  readonly ceremony: Ceremony;
}

/** What the minute's server-side budget has left for this actor and session. */
export interface ActionBudget {
  readonly pasteUsed: number;
  readonly pasteLimit: number;
  readonly submitUsed: number;
  readonly submitLimit: number;
}

/** Who is asking, and how fresh the protected reauthentication behind them is. */
export interface TypingActor {
  readonly role: string;
  readonly roleBindingRevision: number;
  readonly reauthenticatedText: string;
  readonly freshnessText: string;
}

/** The revocation fact, its cause, and the two times that prove the five-second bound. */
export interface Revocation {
  readonly fact: string;
  readonly cause: string;
  readonly appendedAt: string;
  readonly streamsClosedAt: string;
}

/**
 * The nine states a dispatch can be in, exactly as the specification names them.
 *
 * `injected_unacknowledged` is where the audit chain stops today: a zero exit
 * status from `paste-buffer` or `send-keys` supports only that, and pane echo,
 * silence, a changed prompt or transcript text never upgrade it. `acknowledged`
 * needs a harness ACK the canonical runner protocol does not supply.
 *
 * `state_unknown` is the one this surface exists to tell the truth about. A
 * crash between admission and receipt means bytes may already have reached the
 * pane, so it is neither a success nor a failure and is never retried
 * automatically. Drawing it as either would be the worst thing this control
 * could do.
 */
export type DispatchState =
  | "unsent"
  | "durability_pending"
  | "accepted"
  | "dispatching"
  | "injected_unacknowledged"
  | "acknowledged"
  | "refused"
  | "expired"
  | "state_unknown";

/** One dispatch this session already made, as the record answered for it. */
export interface DispatchRecord {
  readonly commandId: string;
  readonly state: DispatchState;
}

/** Everything the affordance needs about one console-visible session. */
export interface ConsoleTyping {
  readonly session: SessionBinding;
  readonly actor: TypingActor;
  readonly budget: ActionBudget;
  readonly revocation: Revocation | null;
  readonly grant: LiveGrant | null;
  readonly lastDispatch: DispatchRecord | null;
}

/**
 * Which of the five rendered states one session and one draft are in.
 *
 * The order is not arbitrary. Revocation outranks a live grant because a
 * revoked incarnation refuses dispatch at both authorization and final
 * admission, so a countdown still ticking on a revoked session would be a lie
 * this surface told. Expiry outranks the grant it belongs to for the same
 * reason.
 */
export type TypingPhase = "read-only" | "ceremony" | "granted" | "expired" | "revoked";

/**
 * The grant and the confirmation are passed in rather than read off
 * `ConsoleTyping`, because the freshest of each is whatever the last command
 * answered with — the session read behind it was taken before either existed.
 */
export function phaseOf(standing: {
  readonly revocation: Revocation | null;
  readonly grant: LiveGrant | null;
  /** Whether a ceremony is open — being written, or written and canonicalized. */
  readonly confirming: boolean;
  readonly now: number;
}): TypingPhase {
  if (standing.revocation !== null) {
    return "revoked";
  }
  if (standing.grant !== null) {
    return secondsLeft(standing.grant, standing.now) === 0 ? "expired" : "granted";
  }
  return standing.confirming ? "ceremony" : "read-only";
}

/**
 * Whole seconds left of the grant, for display only.
 *
 * Every rounding choice here leans the same way: never claim time the grant may
 * not have.
 *
 * * Seconds are **floored**, so a grant with 0.9s left reads `0` and the
 *   control locks slightly before the server's clock does. The other rounding
 *   offers a press that is certain to refuse.
 * * The count is **clamped to the granted life**. A browser a second behind the
 *   server would otherwise read `1:01` on a sixty-second grant, and a countdown
 *   that shows more time than was ever granted is describing a grant nobody
 *   minted.
 * * An **unparseable stamp** is not zero and is not the full life: it is a
 *   grant this surface cannot describe, so it reports nothing left and the
 *   control locks rather than inventing a number. A stopped countdown that
 *   refuses is recoverable in one press; a countdown that guesses is not.
 */
export function secondsLeft(grant: LiveGrant, now: number): number {
  const expires = Date.parse(grant.expiresAt);
  if (Number.isNaN(expires)) {
    return 0;
  }
  return Math.max(0, Math.min(grant.grantedSeconds, Math.floor((expires - now) / 1000)));
}

/** `0:47` — the countdown as the approved ceremony prints it. */
export function countdownText(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes.toString()}:${(seconds % 60).toString().padStart(2, "0")}`;
}

/** How much of the granted life is left, as a width the bar can carry. */
export function countdownWidth(grant: LiveGrant, now: number): string {
  if (grant.grantedSeconds <= 0) {
    return "0%";
  }
  const share = Math.min(1, secondsLeft(grant, now) / grant.grantedSeconds);
  return `${(share * 100).toFixed(1)}%`;
}

/**
 * Whether the grant still covers what is in the field.
 *
 * The comparison is against the words this browser confirmed, not against a
 * digest, because a digest recomputed here would be a second canonicalization
 * with no authority — and agreeing with the server by accident is not the same
 * as being bound by it.
 */
export function grantCoversDraft(grant: LiveGrant, draft: string): boolean {
  return grant.ceremony.action === "submit" || grant.ceremony.text === draft;
}

/** `11 requested · 12 planned`, with the reason the two differ available beside it. */
export function bytesText(ceremony: Ceremony): string {
  return `${ceremony.requestedBytes.toString()} requested · ${ceremony.plannedBytes.toString()} planned`;
}

/** `1 paste · 0 submit`, the server-side budget this minute has already spent. */
export function budgetText(budget: ActionBudget): string {
  return `${budget.pasteUsed.toString()} paste · ${budget.submitUsed.toString()} submit`;
}

/** `4 paste · 6 submit`, the ceiling that budget is measured against. */
export function budgetLimitText(budget: ActionBudget): string {
  return `${budget.pasteLimit.toString()} paste · ${budget.submitLimit.toString()} submit`;
}

/** How each dispatch state reads on the audit chain, and which verdict class it carries. */
const CHAIN: Readonly<Record<DispatchState, { readonly label: string; readonly verdict: string }>> =
  {
    unsent: { label: "unsent", verdict: "v-filed" },
    durability_pending: { label: "durability pending", verdict: "v-changes" },
    accepted: { label: "accepted", verdict: "v-pass" },
    dispatching: { label: "dispatching", verdict: "v-flight" },
    injected_unacknowledged: { label: "injected (unacknowledged)", verdict: "v-flight" },
    acknowledged: { label: "acknowledged", verdict: "v-pass" },
    refused: { label: "refused", verdict: "v-held" },
    expired: { label: "expired", verdict: "v-held" },
    state_unknown: { label: "state unknown", verdict: "v-held" },
  };

export function chainOf(state: DispatchState): {
  readonly label: string;
  readonly verdict: string;
} {
  return CHAIN[state];
}

/**
 * The sentence the chain ends on, which is the only place this surface is
 * allowed to explain what it does not know.
 *
 * Every one of these is a claim about the record, not about the pane. The
 * `state_unknown` line is deliberately the longest: an operator reading it has
 * to decide whether to type the command again, and the one thing that would
 * make that decision badly is a short reassuring sentence.
 */
const CHAIN_NOTE: Readonly<Partial<Record<DispatchState, string>>> = {
  durability_pending:
    "The record has not promised to keep this command yet, so nothing has been dispatched.",
  injected_unacknowledged: "acknowledged needs a harness ACK this runner protocol does not supply",
  acknowledged: "the harness returned the acknowledgement this command was waiting for",
  refused: "nothing was injected",
  expired: "the grant ended before this command was admitted; nothing was injected",
  state_unknown:
    "the runner was admitted and never returned a receipt, so this command may or may not have " +
    "reached the pane. It will not be sent again on its own. Read the pane before deciding.",
};

export function chainNote(state: DispatchState): string | null {
  return CHAIN_NOTE[state] ?? null;
}

/**
 * The words on the screen, in one place, in the operator's language.
 *
 * A non-technical reader has to be able to act on every one of these without
 * knowing what a nonce, an epoch or an admission is, so no sentence here names
 * a schema path, a status code or an internal identifier. The ones quoting the
 * approved ceremony are quoted exactly: they were reviewed as the words an
 * operator would read, not as placeholder copy.
 */
export const COPY = {
  paneHeading: "Type into this pane",
  noGrant: "no type grant",
  chatContrast: "Chat is in the right rail. This box reaches the terminal.",
  lockedPlaceholder: "a type grant is required before this pane accepts text",
  requestGrant: "Request type grant",
  requestGrantHelp:
    "Mints a single-use ConsoleTypeGrant: you confirm the exact text, ctower checks your " +
    "reauthentication is under 10 minutes old, and the grant lasts at most 60 seconds for one action.",

  ceremonyHeading: "Confirm exactly this command",
  composePlaceholder: "the exact command this grant will carry",
  confirm: "Confirm this command",
  confirmHelp:
    "ctower canonicalizes exactly these bytes and shows you their digest and counts. Nothing is " +
    "granted and nothing is typed by confirming.",
  notMinted: "grant not minted yet",
  mint: "Mint 60-second grant",
  mintHelp: "One presentation, one action, at most 60 seconds.",
  cancel: "Cancel",
  notAuthority: "Confirming is not authority. The server mints the grant, or refuses.",
  plannedWhy: "the plan carries the one ASCII space bin/mux prepends",
  reauthWhy: "a grant refuses on anything older than 10 minutes",

  onePresentation: "One presentation of exactly this text. A change needs a new grant.",
  grantHelp:
    "This grant expires 60 seconds after it was minted, and carries exactly one presentation.",
  paste: "Paste text",
  pasteHelp: "Sends paste_text: the planned bytes, no Enter.",
  submit: "Submit ⏎",
  submitHelp:
    "Sends submit: one Enter, no text payload. It is a separate action with its own grant.",
  changed:
    "This is no longer the text the grant was minted for, so it cannot be sent under it. " +
    "Confirm the new text to mint a new grant.",

  expired: "type grant expired",
  expiredWhy:
    "Nothing was injected. The 60-second grant ended before the action was taken; your text is " +
    "kept so you can confirm it again.",
  requestAgain: "Request a new grant",
  requestAgainHelp: "Mints a new grant. The old one cannot be reused, extended or replayed.",

  revoked: "session revoked",
  revokedWhy:
    "This session incarnation was revoked, so no grant can be minted for it. When the crew is " +
    "re-assigned it comes back as a new incarnation with its own allowlist fact.",
} as const;

/**
 * Every refusal an operator can be handed by this control, in plain words.
 *
 * The server answers a validated problem document and its `detail` sentence is
 * the one this surface prints — a refusal explained by the authority that
 * refused beats one guessed at from a status code. These are what is said when
 * there is no such sentence to print: the transport never answered, the answer
 * was not a problem document, or the browser refused before asking at all.
 * None of them ever tells an operator to try again on a path that will refuse
 * again for the same reason.
 */
export const REFUSAL = {
  noContract:
    "This instance does not serve the console typing contract, so nothing can be typed into " +
    "this pane from here.",
  unreadable: "The server refused this command without an explanation this screen can print.",
  unreachable: "This command did not reach the server. Nothing was typed into the pane.",
  emptyText: "Write the command before asking for a grant.",
  budgetSpent:
    "This minute's typing budget for this session is already spent. It refills on the server's " +
    "own clock.",
  staleReauth:
    "Your last identity check is older than ten minutes, so no grant can be minted. Sign in " +
    "again and confirm the command.",
} as const;
