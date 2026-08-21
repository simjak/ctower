import type { ReactElement, ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { ThemeToggle } from "./ThemeToggle";

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
      <span className="sep">/</span>
      <span className="where">Setup</span>
    </span>
  );
}

export function Chrome({ children }: { readonly children: ReactNode }): ReactElement {
  return (
    <>
      <Sidebar />
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
          <Mark />
          <span className="grow" />
          <span className="shell-state">empty shell</span>
          <ThemeToggle />
        </div>
      </header>
      {children}
    </>
  );
}
