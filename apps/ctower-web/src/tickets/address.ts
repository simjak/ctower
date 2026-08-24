import { useCallback, useEffect, useState } from "react";

/**
 * Where the operator is on this page, kept in the address.
 *
 * A screen is a link. `?at=tickets&project=ctower` is the list and `&ticket=…`
 * is one ticket. Keeping it here rather than in component state is what makes
 * the browser's own Back button mean "back", and what makes a screenshot
 * reproducible from its URL alone.
 *
 * Raising one is deliberately absent. It is a pop-up over the list — a moment,
 * not a place — the same idiom the Projects screen uses to make a project, and
 * an address that reopened a half-typed ticket would be describing a draft the
 * record never held.
 */
export interface Place {
  /** The work-plane project whose tickets are being read. */
  readonly project: string | null;
  /** The one ticket being read, when one is. */
  readonly ticket: string | null;
}

const AT = "tickets";

export function placeFrom(search: string): Place {
  const asked = new URLSearchParams(search);
  return { project: asked.get("project"), ticket: asked.get("ticket") };
}

/** The address this place is written as, path unchanged. */
export function searchFor(place: Place): string {
  const asked = new URLSearchParams({ at: AT });
  if (place.project !== null) {
    asked.set("project", place.project);
  }
  if (place.ticket !== null) {
    asked.set("ticket", place.ticket);
  }
  return `?${asked.toString()}`;
}

/**
 * The current place, and the one way to change it.
 *
 * `popstate` is listened for so the browser's Back button moves the page
 * instead of leaving a stale screen under a changed address.
 */
export function usePlace(): readonly [Place, (next: Place) => void] {
  const [place, setPlace] = useState<Place>(() => placeFrom(window.location.search));

  useEffect((): (() => void) => {
    const walked = (): void => {
      setPlace(placeFrom(window.location.search));
    };
    window.addEventListener("popstate", walked);
    return (): void => {
      window.removeEventListener("popstate", walked);
    };
  }, []);

  const go = useCallback((next: Place): void => {
    window.history.pushState(null, "", searchFor(next));
    setPlace(next);
  }, []);

  return [place, go];
}
