import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { ThemeToggle } from "./ThemeToggle";
import { recordAdapter } from "@/read/adapter";

/**
 * The page name a screen shows in the breadcrumb, and the rail item that name
 * lights. They differ where the approved IA renames a surface: the board is the
 * fleet dashboard, and a ticket screen lights the rail entry that reaches one.
 */
const RAIL_OF = {
  Board: "Dashboard",
  Ticket: "Latest ticket",
  Heartbeats: "Heartbeats",
  Inbox: "Inbox",
  Feed: "Feed",
  Files: "Files",
  Workspace: "Workspace",
  Explorer: "Explorer",
  Metrics: "Metrics",
  Org: "Org",
} as const;

export type SectionLabel = keyof typeof RAIL_OF;

function Mark({ where }: { readonly where: string | null }): ReactElement {
  return (
    <span className="mark">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
        <rect x=".75" y=".75" width="18.5" height="18.5" rx="5.25" stroke="var(--line-2)" />
        <circle cx="10" cy="5.4" r="1.7" fill="var(--accent)" />
        <path d="M10 7.8v6.4" stroke="var(--ink)" strokeWidth="1.6" strokeLinecap="round" />
        <path
          d="M6.5 8.6a4.4 4.4 0 0 0 0 3.6"
          stroke="var(--ink-3)"
          strokeWidth="1.3"
          strokeLinecap="round"
        />
        <path
          d="M13.5 8.6a4.4 4.4 0 0 1 0 3.6"
          stroke="var(--ink-3)"
          strokeWidth="1.3"
          strokeLinecap="round"
        />
      </svg>
      <b>ctower</b>
      {where === null ? null : (
        <>
          <span className="sep">/</span>
          <span className="where">{where}</span>
        </>
      )}
    </span>
  );
}

function Instance(): ReactElement {
  const revision = process.env.CTOWER_UI_INSTANCE_REVISION;
  return (
    <span className="instance">
      <span className="dot" />
      {recordAdapter.instance.label}
      {revision === undefined || revision === "" ? null : <span className="mono">{revision}</span>}
    </span>
  );
}

/**
 * The frame every screen shares: one identity, one navigation, one theme
 * switch. The navigation is the R2736 sidebar — a rail on the desk, a drawer on
 * the phone — and the horizontal section nav it replaced is gone, not kept
 * beside it.
 *
 * `Workflow` is deliberately absent from the rail: it is the R2707 surface and
 * is not built here, and a nav entry that leads nowhere is a dead control. The
 * rail's per-seat and per-project entries are absent for the same reason until
 * the seat and crew profiles exist; Org carries both as filters that work.
 */
export function Chrome({
  section,
  back = false,
  counters = null,
  headerExtra = null,
}: {
  readonly section: SectionLabel;
  readonly back?: boolean;
  readonly counters?: ReactNode;
  readonly headerExtra?: ReactNode;
}): ReactElement {
  return (
    <>
      <Sidebar here={RAIL_OF[section]} />
      <header className="top">
        <div className="top-row">
          <label className="burger" htmlFor="drawer" aria-label="Open the menu">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
              <path
                d="M2 4h12M2 8h12M2 12h12"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
          </label>
          <Mark where={back ? null : section} />
          {back ? (
            <Link className="back" href="/board">
              ← Board
            </Link>
          ) : null}
          <span className="grow" />
          {counters}
          <Instance />
          <ThemeToggle />
        </div>
        {headerExtra}
      </header>
    </>
  );
}
