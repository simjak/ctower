import type { ReactElement } from "react";
import { Configuration } from "./Configuration";
import { Frame } from "./Frame";
import { Today } from "./Today";

/**
 * The three T-030 screens, each on its own address so each can be shot alone:
 * `gallery.html?screen=configuration-today`, `…=configuration`,
 * `…=configuration-marked`.
 *
 * They are three answers to one question and they are meant to be read in that
 * order: what the tab can honestly be **now**, what it should be **once a
 * project can be described**, and **what each row is waiting on** to get from
 * the first to the second. Nothing is wired; no read runs.
 */
export type ScreenKey = "configuration-today" | "configuration" | "configuration-marked";

const SCREENS: readonly ScreenKey[] = [
  "configuration-today",
  "configuration",
  "configuration-marked",
];

export function screenFromSearch(search: string): ScreenKey {
  const asked = new URLSearchParams(search).get("screen");
  return SCREENS.includes(asked as ScreenKey) ? (asked as ScreenKey) : "configuration";
}

export function Screen({ which }: { readonly which: ScreenKey }): ReactElement {
  return (
    <Frame>
      {which === "configuration-today" ? (
        <Today />
      ) : (
        <Configuration marked={which === "configuration-marked"} />
      )}
    </Frame>
  );
}
