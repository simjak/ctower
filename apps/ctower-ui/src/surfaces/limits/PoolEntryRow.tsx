import type { ReactElement } from "react";
import { AXES, AxisChip, blockingOf, statedAxes, toneOf } from "./axes";
import { StateGlyph } from "@/frame/StateGlyph";
import { stampText } from "@/read/elapsed";
import type { PoolEntry } from "@/read/interface";

/**
 * One credential-pool account: the record's verdict on it, its three axes, and
 * its own clock.
 *
 * **The leading mark is the record's `selectable`, and nothing derived.** It is
 * tempting to mark the row by whichever axis is blocking — a capped account and
 * a dead one would then be told apart at a glance. They are told apart, but by
 * the axis chips, because a mark composed here can contradict the record: this
 * pool answers `selectable` for an entry whose quota it never observed, and a
 * browser-side classification would draw that row as blocked while the record
 * calls it usable. The record composes; the screen reports.
 *
 * What the accepted design does insist on is that `capped` and `dead · auth`
 * never look alike — *"collapsing any pair of them costs the operator the next
 * action"*. So the difference lands where it can be carried honestly: the
 * blocking axis takes its own hue, keeps the record's own word, and the row
 * says in one line which axis is blocking and what closes it.
 *
 * The clock is per account for the same reason as the axes. A profile's
 * accounts reset at different times, and the record holds no reset time at all
 * for an account that is not capped — an answered absence, which says so rather
 * than rendering as a dash a reader would take for a missing read.
 */

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

/**
 * The one line a blocked account is owed: which axis, and what closes it.
 *
 * It renders only where the record itself said the account is not selectable,
 * so the line can never argue with the verdict beside it. Where the record
 * refuses an account without leaving an unclear axis, that is what it says —
 * borrowing an axis to explain the refusal would be inventing the reason.
 */
function Blocked({ entry }: { readonly entry: PoolEntry }): ReactElement | null {
  if (entry.selectable) {
    return null;
  }
  const { axes, close } = blockingOf(entry);
  return (
    <span className="limits-blocked">
      {axes.length === 0 ? (
        "not ready — the record names no blocking axis"
      ) : (
        <>
          not ready — <b>{axes.join(" · ")}</b> blocking
        </>
      )}
      {close === null ? null : <span className="limits-close">{close}</span>}
    </span>
  );
}

export function PoolEntryRow({ entry }: { readonly entry: PoolEntry }): ReactElement {
  const stated = statedAxes(entry);
  return (
    <article className="limits-row">
      <div className="limits-account">
        <StateGlyph name={entry.selectable ? "done" : "held"} />
        {/* the mark carries this for the eye; the word carries it for a reader
            who has no eye on it */}
        <span className="sr">{entry.selectable ? "selectable" : "not selectable"}</span>
        <span className="limits-provider">{entry.providerKey}</span>
        <Account entry={entry} />
        <span className="limits-gap" />
        {/* not a fourth axis: whether the authored topology knows this account
            at all, which is the same question drift answers from the other side */}
        <span className={`verdict ${toneOf(entry.registrationState)}`}>
          {entry.registrationState}
        </span>
      </div>
      <div className="limits-axes">
        {AXES.map((axis) => (
          <AxisChip axis={axis} key={axis} state={stated[axis]} />
        ))}
        <Blocked entry={entry} />
      </div>
      <div className="limits-facts">
        <span className="limits-clock">
          {entry.quotaResetAt === null
            ? "no reset time recorded"
            : `resets ${stampText(entry.quotaResetAt)}`}
        </span>
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
