import type { ReactElement, ReactNode } from "react";
import { Resolved } from "@/frame/Declared";
import { clockText, spanText } from "@/read/elapsed";
import { initialsOf } from "@/read/sources/crewNaming";
import type { Reading, WorkSession } from "@/read/interface";

/**
 * The work timeline: who worked, for how long, at what token cost, with what
 * outcome.
 *
 * This panel spent its whole life saying it had nothing. `GET
 * /v1/tickets/{id}/sessions` answers now, and it answers with exactly the four
 * columns the approved layout was drawn for — so the panel renders the record,
 * and a ticket the record holds no session for says that instead of naming work
 * that would land a capability ctower already has.
 *
 * Nothing here is computed from a session that is still open. An unfinished
 * session contributes no duration and no outcome, because the record wrote
 * neither, and the totals say how many sessions they were counted over.
 */

const CHART_TONES = ["s-xhigh", "s-max", "s-opus"] as const;

/** `1.73M` / `24k` / `860` — the approved token spelling. */
function tokenText(total: number): ReactNode {
  if (total >= 1_000_000) {
    return (
      <>
        {(total / 1_000_000).toFixed(2)}
        <small>M</small>
      </>
    );
  }
  if (total >= 1_000) {
    return (
      <>
        {Math.round(total / 1_000).toString()}
        <small>k</small>
      </>
    );
  }
  return total.toString();
}

function tokenLabel(total: number): string {
  if (total >= 1_000_000) {
    return `${(total / 1_000_000).toFixed(2)}M`;
  }
  return total >= 1_000 ? `${Math.round(total / 1_000).toString()}k` : total.toString();
}

interface Family {
  readonly model: string;
  readonly tokens: number;
}

/** Tokens by model, largest first — the record's own model strings, unnormalised. */
function familiesOf(sessions: readonly WorkSession[]): readonly Family[] {
  const totals = new Map<string, number>();
  for (const session of sessions) {
    totals.set(session.modelRef, (totals.get(session.modelRef) ?? 0) + session.totalTokens);
  }
  return [...totals]
    .map(([model, tokens]) => ({ model, tokens }))
    .filter((family) => family.tokens > 0)
    .sort((left, right) => right.tokens - left.tokens);
}

/**
 * The token split.
 *
 * The vendored stylesheet carries three chart tones and the record carries as
 * many model strings as the fleet ran, so the tones cycle. That is safe here
 * only because the legend repeats every model *and* its number — the design
 * reference's own rule that no two series are told apart by hue alone.
 */
function TokenSplit({ families }: { readonly families: readonly Family[] }): ReactElement | null {
  const total = families.reduce((sum, family) => sum + family.tokens, 0);
  if (total === 0) {
    return null;
  }
  return (
    <div className="split">
      <div className="lbl">
        <span>tokens by model</span>
        <span>
          {families.length} {families.length === 1 ? "model" : "models"}
        </span>
      </div>
      <div className="bar-split">
        {families.map((family, index) => (
          <span
            className={CHART_TONES[index % CHART_TONES.length]}
            key={family.model}
            style={{ width: `${((family.tokens / total) * 100).toFixed(1)}%` }}
          />
        ))}
      </div>
      <div className="legend">
        {families.map((family, index) => (
          <span key={family.model}>
            <i className={CHART_TONES[index % CHART_TONES.length]} />
            {family.model} {tokenLabel(family.tokens)}
          </span>
        ))}
      </div>
    </div>
  );
}

function Totals({ sessions }: { readonly sessions: readonly WorkSession[] }): ReactElement {
  const timed = sessions.filter((session) => session.durationSeconds !== null);
  const seconds = timed.reduce((sum, session) => sum + (session.durationSeconds ?? 0), 0);
  const tokens = sessions.reduce((sum, session) => sum + session.totalTokens, 0);
  const seats = new Set(sessions.map((session) => session.seatKey)).size;
  const open = sessions.length - timed.length;
  return (
    <div className="totals">
      <div className="tgrid">
        <div>
          <div className="k">Sessions</div>
          <div className="v">{sessions.length}</div>
        </div>
        <div>
          <div className="k">Work time</div>
          <div
            className="v"
            title={
              open === 0
                ? undefined
                : `counted over ${timed.length.toString()} closed of ${sessions.length.toString()} sessions; ${open.toString()} is still open and the record wrote it no duration`
            }
          >
            {timed.length === 0 ? "—" : spanText(seconds * 1000)}
            {open === 0 ? null : <small>+{open}</small>}
          </div>
        </div>
        <div>
          <div className="k">Tokens</div>
          <div className="v">{tokenText(tokens)}</div>
        </div>
        <div>
          <div className="k">Seats</div>
          <div className="v">{seats}</div>
        </div>
      </div>
      <TokenSplit families={familiesOf(sessions)} />
    </div>
  );
}

/**
 * How an outcome reads as a chip. An open session has no outcome to draw, so it
 * draws its recorded `state` instead — the two are different facts and are
 * never spelled as each other.
 */
const OUTCOME_TONE: Readonly<Record<string, string>> = {
  delivered: "verdict v-pass",
  blocked: "verdict v-held",
  abandoned: "verdict v-filed",
  failed: "verdict v-changes",
};

function SessionRow({ session }: { readonly session: WorkSession }): ReactElement {
  const span = session.durationSeconds === null ? null : spanText(session.durationSeconds * 1000);
  return (
    <li>
      <span className="who">
        <i className="av">{initialsOf(session.seatKey)}</i>
      </span>
      <div className="e">
        <div className="hdr">
          <span className="seat">{session.seatKey}</span>
          <span className="crew">{session.crewName}</span>
          <span className="when">
            {clockText(session.startedAt)}
            {span === null ? null : ` · ${span}`}
          </span>
        </div>
        <div className="row">
          <span className="cost">
            <span className="m">{session.modelRef}</span>
            <i className="dot" />
            {tokenLabel(session.totalTokens)} tok
          </span>
          <span className={OUTCOME_TONE[session.outcome ?? ""] ?? "verdict v-filed"}>
            {session.outcome ?? session.state}
          </span>
          <span className="chip">{session.harnessRef}</span>
        </div>
        <div className="arts">
          <span className="art">{session.branchRef}</span>
          <span className="art">{session.worktreeRef}</span>
          {session.evidenceRef === null ? null : <span className="art">{session.evidenceRef}</span>}
        </div>
      </div>
    </li>
  );
}

export function WorkTimeline({
  sessions,
}: {
  readonly sessions: Reading<readonly WorkSession[]>;
}): ReactElement {
  return (
    <section className="panel">
      <header>
        <h2>Work timeline</h2>
      </header>
      <Resolved reading={sessions} brief subject="this ticket's work sessions">
        {(recorded) =>
          recorded.length === 0 ? (
            <div className="empty">no work session recorded on this ticket</div>
          ) : (
            <>
              <Totals sessions={recorded} />
              <ul className="tl">
                {recorded.map((session) => (
                  <SessionRow key={session.sessionId} session={session} />
                ))}
              </ul>
            </>
          )
        }
      </Resolved>
    </section>
  );
}
