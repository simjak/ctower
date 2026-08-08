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
  { href: "/portfolio", label: "Portfolio", group: null },
  { href: "/board", label: "Dashboard", group: null },
  { href: "/inbox", label: "Inbox", group: null },
  { href: "/ticket", label: "Latest ticket", group: "Work" },
  { href: "/heartbeats", label: "Heartbeats", group: "Work" },
  { href: "/metrics", label: "Metrics", group: "Work" },
  { href: "/feed", label: "Feed", group: "Session" },
  { href: "/workspace", label: "Workspace", group: "Session" },
  { href: "/explorer", label: "Explorer", group: "Session" },
  { href: "/files", label: "Files", group: "Session" },
  { href: "/team", label: "Org", group: "Company" },
];

/**
 * The one action that starts work, and why this surface cannot honour it.
 *
 * Read-only v1 holds no write authority. Round-3 QA (#240) found this rendered
 * as a styled `<span>` in the primary call-to-action slot — 219×34px, bordered,
 * filled, clickable-looking, doing nothing, with its only excuse in a native
 * `title` that is invisible on the screen, absent on touch and unreachable by
 * keyboard. The Feed composer and the Files Save/Revert controls already do this
 * correctly, so the fix is to stop breaking a pattern this app has right: a real
 * disabled control, the shared verdict chip, and the reason printed on screen.
 */
export const NEW_TICKET_INERT = {
  label: "New ticket",
  verdict: "read-only v1 · disabled",
  reason:
    "This surface holds no write authority, so it cannot capture a ticket. The ctower CLI does: ctowerctl ticket capture. A ticket captured there appears on this board on the next read.",
} as const;
