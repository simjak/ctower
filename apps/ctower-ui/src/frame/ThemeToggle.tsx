"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

export const THEME_STORAGE_KEY = "ctower-theme";

/**
 * Light is the default. The choice is stored under `ctower-theme` and applied
 * by the inline head script before first paint, so a dark-theme reader never
 * gets a white flash on navigation or reload.
 */
export function ThemeToggle(): ReactElement {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("theme-dark"));
  }, []);

  const toggle = useCallback((): void => {
    const next = document.documentElement.classList.toggle("theme-dark");
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next ? "dark" : "light");
    } catch {
      /* a blocked storage partition must not break the toggle itself */
    }
    setDark(next);
  }, []);

  return (
    <button
      className="tt"
      type="button"
      data-theme-toggle
      aria-pressed={dark}
      aria-label="Switch between light and dark theme"
      onClick={toggle}
    >
      <svg className="i-moon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
        <path
          d="M14 9.3A6 6 0 0 1 6.7 2 6 6 0 1 0 14 9.3Z"
          stroke="currentColor"
          strokeWidth="1.3"
          strokeLinejoin="round"
        />
      </svg>
      <svg className="i-sun" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
        <circle cx="8" cy="8" r="3.1" stroke="currentColor" strokeWidth="1.3" />
        <path
          d="M8 1v1.6M8 13.4V15M15 8h-1.6M2.6 8H1M12.95 3.05l-1.13 1.13M4.18 11.82l-1.13 1.13M12.95 12.95l-1.13-1.13M4.18 4.18L3.05 3.05"
          stroke="currentColor"
          strokeWidth="1.3"
          strokeLinecap="round"
        />
      </svg>
    </button>
  );
}
