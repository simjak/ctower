import Link from "next/link";
import { Fragment } from "react";
import type { ReactElement, ReactNode } from "react";
import { INERT_CONTROL } from "./inert";
import { NEW_TICKET_INERT, RAIL } from "./rail";
import type { RailItem } from "./rail";

/**
 * The frame's navigation, as the operator-approved R2736 information
 * architecture: a fixed rail on the desk, a drawer behind the menu button on
 * the phone, in place of the horizontal section nav rather than beside it. Two
 * navigations for one set of pages is the duplication the frame exists to
 * remove.
 *
 * The drawer is a CSS-only checkbox, so it opens with scripting off and needs
 * no client component. The vendored stylesheet keys on `#drawer`.
 *
 * **No badge is rendered here.** The mockup's live counts came from one read of
 * the whole fleet; putting that read behind every page would make ten screens
 * depend on a source none of them needs, and a badge that failed would have to
 * either lie or shout on a page about something else. The counts live on the
 * one screen that reads them — Org — where they are measured and sourced. A
 * missing badge claims nothing; a wrong one claims a number.
 */

interface Item extends RailItem {
  readonly icon: ReactNode;
}

const icon = (path: ReactNode): ReactElement => (
  <span className="ic">
    <svg width="19" height="19" viewBox="0 0 16 16" fill="none" aria-hidden>
      {path}
    </svg>
  </span>
);

/** One icon per destination, keyed by the href the rail contract declares. */
const ICONS: Readonly<Record<string, ReactNode>> = {
  "/board": icon(
    <path
      d="M2.5 3.5h5v9h-5zM10 3.5h5v4.5h-5zM10 10.5h5v2h-5z"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinejoin="round"
    />
  ),
  "/inbox": icon(
    <path
      d="M2 9.5 4 3.5h9l2 6M2 9.5v3h13v-3M2 9.5h3.5l1 1.5h4l1-1.5H15"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinejoin="round"
    />
  ),
  "/ticket": icon(
    <>
      <path
        d="M2.5 5.5h12v2a1.5 1.5 0 0 0 0 3v2h-12v-2a1.5 1.5 0 0 0 0-3z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path d="M8.5 5.5v7" stroke="currentColor" strokeWidth="1.2" strokeDasharray="1.6 1.6" />
    </>
  ),
  "/heartbeats": icon(
    <path
      d="M1.5 8.5h3l1.5-4 2.5 8 2-4h4"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
  "/metrics": icon(
    <path
      d="M2.5 13.5v-4M6.5 13.5v-8M10.5 13.5v-5M14.5 13.5v-10"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
    />
  ),
  "/feed": icon(
    <path
      d="M2.5 3.5h11v8h-6l-3 2.5v-2.5h-2z"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinejoin="round"
    />
  ),
  "/workspace": icon(
    <>
      <path
        d="M2.5 4.5h11v8h-11zM2.5 7h11"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <circle cx="4.6" cy="5.75" r=".6" fill="currentColor" />
    </>
  ),
  "/explorer": icon(
    <path
      d="M6 3.5 2.5 8 6 12.5M10 3.5 13.5 8 10 12.5"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  "/files": icon(
    <>
      <path d="M4 2.5h5l3 3v8H4z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M9 2.5v3h3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
    </>
  ),
  "/team": icon(
    <>
      <path
        d="M8 2.5v3M3.5 13.5v-3h9v3M8 5.5v5"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <rect x="6" y="1.5" width="4" height="2.5" rx=".6" stroke="currentColor" strokeWidth="1.2" />
      <rect x="1.5" y="11" width="4" height="3" rx=".6" stroke="currentColor" strokeWidth="1.2" />
      <rect x="10.5" y="11" width="4" height="3" rx=".6" stroke="currentColor" strokeWidth="1.2" />
    </>
  ),
};

/**
 * Every item the rail offers. The destinations and their labels come from
 * `rail.ts`, which a test reads directly; this file only dresses them.
 */
export const RAIL_ITEMS: readonly Item[] = RAIL.map((item) => ({
  ...item,
  icon: ICONS[item.href] ?? null,
}));

const inGroup = (group: string | null): readonly Item[] =>
  RAIL_ITEMS.filter((item) => item.group === group);

function Rail({ item, here }: { readonly item: Item; readonly here: string }): ReactElement {
  const on = item.label === here;
  return (
    <Link
      className={on ? "sn on" : "sn"}
      href={item.href}
      aria-current={on ? "page" : undefined}
      title={item.label}
    >
      {item.icon}
      <span className="lbl">{item.label}</span>
    </Link>
  );
}

function Mark(): ReactElement {
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
    </span>
  );
}

export function Sidebar({ here }: { readonly here: string }): ReactElement {
  return (
    <>
      <input className="drawer-toggle" type="checkbox" id="drawer" aria-label="Menu" />
      {/* the scrim closes the drawer by driving the same checkbox; it is
          hidden from assistive tech because the close button above is the
          labelled control */}
      <label className="scrim" htmlFor="drawer" aria-hidden />
      <aside className="side" aria-label="Sections">
        <div className="side-head">
          <Mark />
          <label className="side-x" htmlFor="drawer" aria-label="Close the menu">
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
              <path
                d="M4 4l8 8M12 4l-8 8"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
          </label>
        </div>

        {/* the one action that starts work, and the surface cannot honour it.
            A real disabled button, the same verdict chip the Feed composer
            carries, and the reason printed here rather than hidden in a hover
            (#240) — the operator sees it is unavailable before clicking, not
            after nothing happens */}
        <div className="side-act">
          <button
            className="sact"
            type="button"
            disabled
            style={INERT_CONTROL}
            aria-describedby="new-ticket-readonly"
          >
            <span className="plus" />
            {NEW_TICKET_INERT.label}
          </button>
          <span
            className="verdict v-held"
            style={{ display: "inline-flex", marginTop: "8px" }}
            aria-hidden
          >
            {NEW_TICKET_INERT.verdict}
          </span>
          <p
            id="new-ticket-readonly"
            style={{
              margin: "6px 0 0",
              fontSize: "11.5px",
              lineHeight: 1.45,
              color: "var(--ink-3)",
            }}
          >
            {NEW_TICKET_INERT.reason}
          </p>
        </div>

        <nav className="side-nav">
          {inGroup(null).map((item) => (
            <Rail key={item.href} item={item} here={here} />
          ))}

          {["Work", "Session", "Company"].map((group) => (
            <Fragment key={group}>
              <div className="sgrp">{group}</div>
              {inGroup(group).map((item) => (
                <Rail key={item.href} item={item} here={here} />
              ))}
            </Fragment>
          ))}
        </nav>
      </aside>
    </>
  );
}
