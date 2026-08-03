import type { ReactElement } from "react";
import { KnownValue } from "@/frame/Declared";
import { StateGlyph } from "@/frame/StateGlyph";
import type { CrewActivity } from "@/read/interface";
import type { Known } from "@/read/sources/maybe";

/**
 * The one place a crew's recorded status word becomes a mark.
 *
 * The roster and a crew profile show the same fact, so they draw it with the
 * same component: a second copy is how a status reads `held` on one screen and
 * `blocked` on another. The word printed beside the glyph is always the log's
 * own — this mark classifies, it does not rename.
 *
 * `unrecorded` carries no glyph at all. A crew the log holds no status for is
 * not a parked crew, and giving it the parked mark would be this surface
 * answering a question the record did not.
 */

const GLYPH = { "in-flight": "flight", parked: "parked", held: "held" } as const;

/**
 * The same classification for a mark that must always draw something — a panel
 * heading, say. `unrecorded` gets the open circle, which claims nothing about
 * the crew's state, rather than borrowing one of the three that would.
 */
export const CREW_GLYPH = { ...GLYPH, unrecorded: "open" } as const;

const TONE: Readonly<Record<CrewActivity, string>> = {
  "in-flight": "c-stat",
  parked: "c-stat idle",
  held: "c-stat blocked",
  unrecorded: "c-stat idle",
};

export function ActivityMark({
  activity,
  status,
}: {
  readonly activity: CrewActivity;
  readonly status: Known<string>;
}): ReactElement {
  return (
    <span className={TONE[activity]}>
      {activity === "unrecorded" ? null : <StateGlyph name={GLYPH[activity]} />}
      <KnownValue value={status} />
    </span>
  );
}

/** The same classification as a verdict chip, for a header rather than a row. */
export function ActivityVerdict({
  activity,
  status,
}: {
  readonly activity: CrewActivity;
  readonly status: Known<string>;
}): ReactElement {
  const tone =
    activity === "held"
      ? "verdict v-held"
      : activity === "in-flight"
        ? "verdict v-flight"
        : "verdict v-filed";
  return (
    <span className={tone}>
      <KnownValue value={status} />
    </span>
  );
}
