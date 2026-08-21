import Link from "next/link";
import type { ReactElement } from "react";
import { RAIL } from "./rail";

function Mark(): ReactElement {
  return (
    <span className="mark">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
        <rect x=".75" y=".75" width="18.5" height="18.5" rx="5.25" stroke="var(--line-2)" />
        <circle cx="10" cy="5.4" r="1.7" fill="var(--accent)" />
        <path d="M10 7.8v6.4" stroke="var(--ink)" strokeWidth="1.6" strokeLinecap="round" />
        <path
          d="M6.5 8.6a4.4 4.4 0 0 0 0 3.6M13.5 8.6a4.4 4.4 0 0 1 0 3.6"
          stroke="var(--ink-3)"
          strokeWidth="1.3"
          strokeLinecap="round"
        />
      </svg>
      <b>ctower</b>
    </span>
  );
}

function SetupIcon(): ReactElement {
  return (
    <span className="ic">
      <svg width="19" height="19" viewBox="0 0 16 16" fill="none" aria-hidden>
        <path
          d="M8 2.25v11.5M2.25 8h11.5"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
        <circle cx="8" cy="8" r="5.75" stroke="currentColor" strokeWidth="1.2" />
      </svg>
    </span>
  );
}

export function Sidebar(): ReactElement {
  return (
    <>
      <input className="drawer-toggle" type="checkbox" id="drawer" aria-label="Menu" />
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
        <nav className="side-nav">
          {RAIL.map((item) => (
            <Link className="sn on" href={item.href} aria-current="page" key={item.href}>
              <SetupIcon />
              <span className="lbl">{item.label}</span>
            </Link>
          ))}
        </nav>
      </aside>
    </>
  );
}
