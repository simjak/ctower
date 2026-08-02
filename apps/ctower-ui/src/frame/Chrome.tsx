import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { ThemeToggle } from "./ThemeToggle";
import { recordAdapter } from "@/read/adapter";

export const SECTIONS = [
  { href: "/board", label: "Board" },
  { href: "/ticket", label: "Ticket" },
  { href: "/heartbeats", label: "Heartbeats" },
  { href: "/inbox", label: "Inbox" },
  { href: "/feed", label: "Feed" },
  { href: "/files", label: "Files" },
  { href: "/workspace", label: "Workspace" },
  { href: "/explorer", label: "Explorer" },
] as const;

export type SectionLabel = (typeof SECTIONS)[number]["label"];

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
 * The frame every screen shares: one identity, one nav, one theme switch.
 * `Workflow` is deliberately absent from the section list — it is the R2707
 * surface and is not built in this phase, and a nav entry that leads nowhere
 * would be a dead control.
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
    <header className="top">
      <div className="top-row">
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
      <nav className="nav" aria-label="Sections">
        {SECTIONS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={item.label === section ? "on" : undefined}
            aria-current={item.label === section ? "page" : undefined}
          >
            {item.label}
          </Link>
        ))}
      </nav>
      {headerExtra}
    </header>
  );
}
