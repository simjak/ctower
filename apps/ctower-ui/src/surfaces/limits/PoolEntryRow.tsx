import type { ReactElement } from "react";
import { StateGlyph } from "@/frame/StateGlyph";
import { stampText } from "@/read/elapsed";
import type { PoolEntry } from "@/read/interface";

/**
 * One credential-pool account, drawn as the three axes the record answers with.
 *
 * The axes are deliberately three chips rather than one status, and deliberately
 * three rather than four. `auth`, `quota` and `reach` fail independently — a
 * healthy credential can be capped, and a capped one can still be reachable — so
 * collapsing them would invent a state the record never stated, while promoting
 * a fourth field beside them would invent an axis it never declared. `unknown`
 * gets its own neutral treatment on both axes that have one: an axis nobody
 * could observe is not an available axis, and it may never be drawn as one.
 *
 * The clock is per account for the same reason. A profile's accounts reset at
 * different times, and the record holds no reset time at all for an account
 * that is not capped — which is an answered absence and says so, rather than
 * rendering as a dash a reader would take for a missing read.
 */

type Tone = "v-pass" | "v-held" | "v-changes" | "v-filed";

/** How each axis value reads: proven, refused, attention, or simply unknown. */
const TONES: Readonly<Record<string, Tone>> = {
  healthy: "v-pass",
  "lineage-dead": "v-held",
  "chain-burned": "v-held",
  available: "v-pass",
  capped: "v-held",
  unfunded: "v-changes",
  ok: "v-pass",
  "edge-challenged": "v-changes",
  enrolled: "v-filed",
  discovered: "v-changes",
  unknown: "v-filed",
};

function Axis({ axis, state }: { readonly axis: string; readonly state: string }): ReactElement {
  return (
    <span className="limits-axis">
      <span className="limits-axis-name">{axis}</span>
      <span className={`verdict ${TONES[state] ?? "v-filed"}`}>{state}</span>
    </span>
  );
}

/** The account this row is about, named the way the record named it. */
function Account({ entry }: { readonly entry: PoolEntry }): ReactElement {
  if (entry.subscriptionIdentity !== null) {
    return (
      <>
        <span className="limits-identity">{entry.subscriptionIdentity}</span>
        {entry.entryLabel === null ? null : (
          <span className="limits-label">{entry.entryLabel}</span>
        )}
      </>
    );
  }
  return entry.entryLabel === null ? (
    <span className="limits-identity limits-unnamed">
      the record holds no account name for this entry
    </span>
  ) : (
    <span className="limits-identity">{entry.entryLabel}</span>
  );
}

/** What the record says about this account's spend, in its own units. */
function Credit({ entry }: { readonly entry: PoolEntry }): ReactElement {
  if (entry.creditState === "unmetered") {
    return <span className="limits-fact">unmetered</span>;
  }
  return entry.meteredMillicredits === null ? (
    <span className="limits-fact">metered · no balance recorded</span>
  ) : (
    <span className="limits-fact">{entry.meteredMillicredits.toString()} millicredits</span>
  );
}

export function PoolEntryRow({ entry }: { readonly entry: PoolEntry }): ReactElement {
  return (
    <article className="limits-row">
      <div className="limits-account">
        <StateGlyph name={entry.selectable ? "done" : "held"} />
        <span className="limits-provider">{entry.providerKey}</span>
        <Account entry={entry} />
      </div>
      <div className="limits-axes">
        <Axis axis="auth" state={entry.authState} />
        <Axis axis="quota" state={entry.quotaState} />
        <Axis axis="reach" state={entry.reachState} />
      </div>
      <div className="limits-facts">
        <span className="limits-clock">
          {entry.quotaResetAt === null
            ? "no reset time recorded"
            : `resets ${stampText(entry.quotaResetAt)}`}
        </span>
        {/* not a fourth axis: whether the authored topology knows this account
            at all, which is the same question drift answers from the other side */}
        <span className={`verdict ${TONES[entry.registrationState] ?? "v-filed"}`}>
          {entry.registrationState}
        </span>
        <span className="limits-fact">{entry.selectable ? "selectable" : "not selectable"}</span>
        <span className="limits-fact">{entry.requestCount.toString()} requests</span>
        <Credit entry={entry} />
        {entry.lastStatusObserved === null ? null : (
          <span className="limits-fact mono">{entry.lastStatusObserved}</span>
        )}
        <span className="limits-fact mono">observed {stampText(entry.observedAt)}</span>
      </div>
    </article>
  );
}
