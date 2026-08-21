/**
 * What the navigation offers, as data.
 *
 * The rail's icons are JSX and live in `Sidebar.tsx`; its *contract* — which
 * destinations exist, what each is called, and what a reader is promised when
 * they click — is here, so a test can read it without a renderer.
 *
 * The labels are load-bearing. Round-3 QA (#243) found an item called **Tickets**
 * that opened the detail page of whichever ticket had been captured most
 * recently: plural label, single arbitrary record, no way back to a list, and
 * the sentence explaining the behaviour rendered only when the behaviour did not
 * happen. A nav item is a promise about where a click lands, so this one now
 * says what it does — *Latest ticket* — and the screen behind it repeats the
 * rule and carries the ticket's own stable link.
 */

export interface RailItem {
  readonly href: string;
  readonly label: string;
  /** The group the rail files it under; `null` for the ungrouped head. */
  readonly group: string | null;
}

export const RAIL: readonly RailItem[] = [
  // What is running right now, and who is on it. Distinct from Org, which is the
  // durable roster: this one answers "what is the fleet doing this minute" and
  // sorts by what needs the operator rather than by name. Added under the
  // operator's direct authorization (2026-08-21) and the commander's ruling on
  // the same date; the locked-five model treats it as a contextual view of the
  // fleet, not a sixth primary destination.
  { href: "/live", label: "Live", group: null },
  { href: "/portfolio", label: "Portfolio", group: null },
  { href: "/requests", label: "Requests", group: null },
  { href: "/board", label: "Dashboard", group: null },
  { href: "/inbox", label: "Inbox", group: null },
  { href: "/ticket", label: "Latest ticket", group: "Work" },
  { href: "/metrics", label: "Metrics", group: "Work" },
  { href: "/feed", label: "Feed", group: "Session" },
  { href: "/workspace", label: "Workspace", group: "Session" },
  { href: "/explorer", label: "Explorer", group: "Session" },
  { href: "/files", label: "Files", group: "Session" },
  { href: "/team", label: "Org", group: "Company" },
  // the credential pools the fleet draws on. A shadow read of a shipped API,
  // filed under the company that owns the accounts — never a primary product
  // surface: the locked five are Home, Board, Ticket detail, Fleet, Analytics,
  // and this boundary is not the browser product that carries them.
  { href: "/limits", label: "Limits", group: "Company" },
];

/**
 * The one action that starts work, and how it is actually done.
 *
 * Round-3 QA (#240) found this rendered as a styled `<span>` in the primary
 * call-to-action slot — bordered, filled, clickable-looking, doing nothing,
 * with its only excuse in a native `title` that is invisible on screen, absent
 * on touch and unreachable by keyboard. The fix then was a real disabled
 * control, a verdict chip and the reason printed under it.
 *
 * The reason was three lines of prose on every screen in the app. The operator's
 * de-texting amendment retires it: the disabled control says it cannot be
 * pressed, the verdict chip says why in two words, and `command` is the thing
 * that *does* work — shown as the command itself rather than described in a
 * sentence about it. `reason` survives as the control's hover, which is where
 * the craft rules put a caveat.
 */
export const NEW_TICKET_INERT = {
  label: "New ticket",
  verdict: "cli only",
  /** What captures a ticket, printed as the command rather than narrated. */
  command: "ctowerctl ticket capture",
  reason: "capture it with the CLI; the board shows it on the next read",
} as const;
