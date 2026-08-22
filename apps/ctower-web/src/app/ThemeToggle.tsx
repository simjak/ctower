import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

export const THEME_STORAGE_KEY = "ctower-theme";

/**
 * Light is the default. The choice is stored under `ctower-theme` and applied
 * by the inline script in `index.html` before first paint, so a dark-theme
 * reader never gets a white flash on reload. Same key, same class, and the same
 * behaviour as the phase-1 surface: a reader who has both open sets it once.
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
      className="rounded-md border border-line px-2 py-1 text-2xs text-muted hover:bg-raised"
      type="button"
      aria-pressed={dark}
      aria-label="Switch between light and dark theme"
      onClick={toggle}
    >
      <span aria-hidden>{dark ? "☾" : "☀"}</span>
    </button>
  );
}
