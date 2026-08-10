"use client";

import { useActionState, useEffect, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import type { ConsoleTypingState } from "@/mutate/types";
import { clockText, shortId } from "@/read/elapsed";
import type { Ceremony, ConsoleTyping, DispatchRecord, LiveGrant, Revocation } from "./typing";
import {
  budgetLimitText,
  budgetText,
  bytesText,
  chainNote,
  chainOf,
  COPY,
  countdownText,
  countdownWidth,
  grantCoversDraft,
  phaseOf,
  secondsLeft,
} from "./typing";

/**
 * The typing affordance on a crew's terminal, in every state it has.
 *
 * The loudest fact on this surface is a contrast, and it is deliberate: the
 * chat composer beside this one sends without any grant at all, and this one
 * does not. An operator who confuses the two types a command into a live crew
 * terminal believing they wrote a message, so the difference is stated on the
 * control rather than left to be learned.
 *
 * Nothing here decides anything. The server mints, admits and expires; this
 * renders what it answered and locks controls that would certainly refuse. The
 * countdown is the clearest case — it is a description of a server-side clock,
 * never a permission — and the audit chain is the second: it stops at
 * `injected (unacknowledged)` because that is where the record's own evidence
 * stops, and it says `state unknown` when the record does not know either.
 *
 * `placement` is the one seam the operator's open A/B pick moves. The board's
 * variant A confirms in place under the pane; variant B confirms in a modal
 * over the frame. Every word, row, count and state below is identical between
 * them — that is the mockup's own finding, not an assumption — so the pick
 * changes this prop and nothing else.
 */

const INITIAL: ConsoleTypingState = { kind: "idle" };
const TICK_MS = 1000;

export type CeremonyPlacement = "inline" | "modal";

/** One mono line of bounds under a control, as the board prints them. */
function Meta({ children }: { readonly children: ReactNode }): ReactElement {
  return <p className="cc-meta">{children}</p>;
}

/**
 * The previous command's audit chain.
 *
 * It is drawn above the composer rather than inside it because it describes a
 * command that is already over: putting it in the box an operator is about to
 * use again invites reading a finished state as this one's.
 */
function Chain({ dispatch }: { readonly dispatch: DispatchRecord }): ReactElement {
  const { label, verdict } = chainOf(dispatch.state);
  const note = chainNote(dispatch.state);
  return (
    <div className="cc-chain" role="status">
      <span>cmd {shortId(dispatch.commandId)}</span>
      <span className="arrow">·</span>
      <span className={`verdict ${verdict}`}>{label}</span>
      {note === null ? null : <span className="why">{note}</span>}
    </div>
  );
}

/** The six rows an operator confirms, every number of them server-derived. */
function CeremonyRows({ ceremony }: { readonly ceremony: Ceremony }): ReactElement {
  return (
    <ul className="kv">
      <li>
        <span className="k">Action</span>
        <span className="v">{ceremony.action}</span>
      </li>
      <li>
        <span className="k">Exact text</span>
        <span className="v" style={{ flex: "1 1 100%" }}>
          {/* `submit` has no text payload at all, and an empty box would read
              as a command whose text failed to load rather than as one that
              never had any */}
          {ceremony.action === "submit" ? (
            <span className="sub">no text payload — one Enter</span>
          ) : (
            <pre className="cc-bytes">{ceremony.text}</pre>
          )}
        </span>
      </li>
      <li>
        <span className="k">Bytes</span>
        <span className="v">
          {bytesText(ceremony)}
          <span className="sub">{COPY.plannedWhy}</span>
        </span>
      </li>
      <li>
        <span className="k">Digest</span>
        <span className="v">{ceremony.digest}</span>
      </li>
      <li>
        <span className="k">Into</span>
        <span className="v">
          {ceremony.into.crew}
          <span className="sub">
            incarnation {ceremony.into.incarnation} · runner epoch {ceremony.into.runnerEpoch} ·
            assignment seq {ceremony.into.assignmentSequence}
          </span>
        </span>
      </li>
      <li>
        <span className="k">Reauth</span>
        <span className="v">
          {ceremony.reauthenticatedText}
          <span className="sub">{COPY.reauthWhy}</span>
        </span>
      </li>
    </ul>
  );
}

/**
 * The composer with no grant behind it.
 *
 * The field is inert and says what would unlock it. It is not merely styled as
 * disabled: an enabled field on a pane that cannot accept text would invite an
 * operator to write a command and then discover the control never had the
 * authority to send it.
 */
function ReadOnlyBox({
  typing,
  submitting,
}: {
  readonly typing: ConsoleTyping;
  readonly submitting: boolean;
}): ReactElement {
  return (
    <div className="steer-box">
      <div className="hd">
        <span className="k">{COPY.paneHeading}</span>
        <span className="verdict v-filed">{COPY.noGrant}</span>
        <span className="note">{COPY.chatContrast}</span>
      </div>
      <div className="steer-row">
        <textarea
          aria-describedby="console-typing-standing"
          className="field"
          disabled
          placeholder={COPY.lockedPlaceholder}
          rows={2}
        />
        <button
          className="btn"
          disabled={submitting}
          name="intent"
          title={COPY.requestGrantHelp}
          type="submit"
          value="open"
        >
          {COPY.requestGrant}
        </button>
      </div>
      <p className="cc-meta" id="console-typing-standing">
        <span>
          you: <b>{typing.actor.role}</b> · role binding rev {typing.actor.roleBindingRevision}
        </span>
        <span>
          reauthenticated <b>{typing.actor.reauthenticatedText}</b> · {typing.actor.freshnessText}
        </span>
        <span>
          limit <b>{budgetLimitText(typing.budget)}</b> per minute
        </span>
      </p>
    </div>
  );
}

/**
 * Writing the exact command, before anything has been granted for it.
 *
 * The board drew this step at the moment it is confirmed, with the digest and
 * the counts already on screen. Those come from the server's canonicalization,
 * so there is an earlier moment the board did not need to draw and a build
 * cannot skip: the words have to be written before there is anything to
 * canonicalize. Both halves live in this one box under the same heading, and
 * the confirmed half is exactly the approved frame.
 */
function CeremonyBox({
  ceremony,
  draft,
  onEdit,
  submitting,
}: {
  readonly ceremony: Ceremony | null;
  readonly draft: string;
  readonly onEdit: (value: string) => void;
  readonly submitting: boolean;
}): ReactElement {
  return (
    <div className="steer-box cc-open">
      <div className="hd">
        <span className="k">{COPY.ceremonyHeading}</span>
        <span className="verdict v-flight">{COPY.notMinted}</span>
      </div>
      {ceremony === null ? (
        <div className="steer-row">
          <textarea
            aria-label="The exact command to type into this pane"
            className="field"
            name="text"
            onChange={(event) => {
              onEdit(event.target.value);
            }}
            placeholder={COPY.composePlaceholder}
            rows={2}
            value={draft}
          />
          <button
            className="btn"
            disabled={submitting}
            name="intent"
            title={COPY.confirmHelp}
            type="submit"
            value="confirm"
          >
            {COPY.confirm}
          </button>
          <button className="btn ghost" name="intent" type="submit" value="cancel">
            {COPY.cancel}
          </button>
        </div>
      ) : (
        <>
          <CeremonyRows ceremony={ceremony} />
          <div className="steer-row" style={{ marginTop: "12px" }}>
            <button
              className="btn"
              disabled={submitting}
              name="intent"
              title={COPY.mintHelp}
              type="submit"
              value="mint"
            >
              {COPY.mint}
            </button>
            <button className="btn ghost" name="intent" type="submit" value="cancel">
              {COPY.cancel}
            </button>
            <span className="note" style={{ alignSelf: "center" }}>
              {COPY.notAuthority}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * The 60 seconds, with the countdown as the loudest element in the box.
 *
 * The field stays editable, because the board's own note says a change needs a
 * new grant and a field that silently refuses edits does not say that. What it
 * cannot do is send different bytes than the ones the grant bound: editing
 * withdraws the two actions and offers the ceremony again, which is the
 * digest-confusion class refused at the only place a browser can refuse it —
 * before asking.
 */
function GrantedBox({
  grant,
  budget,
  draft,
  onEdit,
  now,
  submitting,
}: {
  readonly grant: LiveGrant;
  readonly budget: ConsoleTyping["budget"];
  readonly draft: string;
  readonly onEdit: (value: string) => void;
  readonly now: number;
  readonly submitting: boolean;
}): ReactElement {
  const left = secondsLeft(grant, now);
  const unchanged = grantCoversDraft(grant, draft);
  // one grant, one action: the other button is not a second presentation of
  // this grant, it is the start of another ceremony, and its own tooltip has
  // said so since the approved board
  const pasting = grant.ceremony.action === "paste_text";
  return (
    <div className="steer-box cc-live">
      <div className="hd">
        <span className="k">{COPY.paneHeading}</span>
        <span className="ctr c-attn" title={COPY.grantHelp}>
          type grant {countdownText(left)}
        </span>
        <span className="note">{COPY.onePresentation}</span>
      </div>
      <div
        aria-label={`${left.toString()} of the grant's ${grant.grantedSeconds.toString()} seconds remain`}
        className="cc-tick"
        role="img"
      >
        <i style={{ width: countdownWidth(grant, now) }} />
      </div>
      <div className="steer-row" style={{ marginTop: "11px" }}>
        <textarea
          aria-label="Text to paste into the pane"
          className="field"
          disabled={!pasting}
          name="text"
          onChange={(event) => {
            onEdit(event.target.value);
          }}
          rows={2}
          value={draft}
        />
        <button
          className="btn"
          disabled={submitting || !pasting || !unchanged}
          name="intent"
          title={COPY.pasteHelp}
          type="submit"
          value={pasting ? "present" : "confirm"}
        >
          {COPY.paste}
        </button>
        <button
          className="btn ghost"
          disabled={submitting || (pasting && !unchanged)}
          name="intent"
          title={COPY.submitHelp}
          type="submit"
          value={pasting ? "confirm_submit" : "present"}
        >
          {COPY.submit}
        </button>
      </div>
      {unchanged ? null : (
        <p className="card-note held" role="alert" style={{ marginTop: "11px" }}>
          {COPY.changed}
        </p>
      )}
      <Meta>
        <span>
          digest <b>{grant.ceremony.digest}</b>
        </span>
        <span>{bytesText(grant.ceremony)}</span>
        <span>
          used this minute <b>{budgetText(budget)}</b>
        </span>
      </Meta>
    </div>
  );
}

/** The minute ran out. The words stay; the recovery is a new grant, not a retry. */
function ExpiredBox({
  draft,
  submitting,
}: {
  readonly draft: string;
  readonly submitting: boolean;
}): ReactElement {
  return (
    <div className="steer-box cc-shut">
      <div className="hd">
        <span className="k">{COPY.paneHeading}</span>
        <span className="ctr c-held">{COPY.expired}</span>
      </div>
      <div className="steer-row">
        <textarea
          aria-describedby="console-typing-expired"
          aria-label="Text to paste into the pane"
          className="field"
          disabled
          readOnly
          rows={2}
          value={draft}
        />
        <button
          className="btn"
          disabled={submitting}
          name="intent"
          title={COPY.requestAgainHelp}
          type="submit"
          value="open"
        >
          {COPY.requestAgain}
        </button>
      </div>
      <p className="card-note held" id="console-typing-expired" style={{ marginTop: "11px" }}>
        {COPY.expiredWhy}
      </p>
    </div>
  );
}

/**
 * The incarnation is gone, so there is nothing to mint against.
 *
 * The two times are both printed because together they are the evidence for
 * the five-second closure bound; one of them alone is an assertion.
 */
function RevokedBox({ revocation }: { readonly revocation: Revocation }): ReactElement {
  return (
    <div className="steer-box cc-shut">
      <div className="hd">
        <span className="k">{COPY.paneHeading}</span>
        <span className="ctr c-held">{COPY.revoked}</span>
      </div>
      <p className="card-note held" style={{ marginTop: 0 }}>
        {COPY.revokedWhy}
      </p>
      <Meta>
        <span>
          fact <b>{revocation.fact}</b>
        </span>
        <span>
          cause <b>{revocation.cause}</b>
        </span>
        <span>
          appended <b>{clockText(revocation.appendedAt)}</b> · streams closed{" "}
          <b>{clockText(revocation.streamsClosedAt)}</b>
        </span>
      </Meta>
    </div>
  );
}

export function ConsoleTypingCeremony({
  typing,
  action,
  placement,
  serverNow,
}: {
  readonly typing: ConsoleTyping;
  readonly action: (state: ConsoleTypingState, formData: FormData) => Promise<ConsoleTypingState>;
  readonly placement: CeremonyPlacement;
  /** The read's own clock, so the first paint does not depend on the browser's. */
  readonly serverNow: number;
}): ReactElement {
  const [state, formAction, submitting] = useActionState(action, INITIAL);
  const [now, setNow] = useState(serverNow);
  // the countdown is the loudest element of the granted state, so it has to
  // actually move; the first paint uses the server's clock and every tick
  // after mount uses this browser's, which describes the grant and decides
  // nothing about it
  useEffect((): (() => void) => {
    const timer = setInterval((): void => {
      setNow(Date.now());
    }, TICK_MS);
    return (): void => {
      clearInterval(timer);
    };
  }, []);

  // the last answer is fresher than the read behind it, so the grant it carries
  // wins; only an untouched control still stands on the session read's own
  const grant =
    state.kind === "granted" ? state.grant : state.kind === "idle" ? typing.grant : null;
  const ceremony = state.kind === "confirmed" ? state.ceremony : null;
  // a refusal leaves the ceremony open rather than closing back to the inert
  // box: the words are still the operator's, and a control that refuses and
  // then makes them retype the command is one they stop trusting with the
  // commands that matter. Recovery is confirming again, which is what is on
  // screen when they finish reading why it was refused.
  const confirming = state.kind === "opened" || state.kind === "refused" || ceremony !== null;
  const phase = phaseOf({ revocation: typing.revocation, grant, confirming, now });

  // the words the last answer left standing, and the operator's edits since —
  // derived rather than synchronised, so a new answer replaces the field
  // without an effect racing the render that drew it
  const answered =
    state.kind === "refused"
      ? state.text
      : ceremony !== null
        ? ceremony.text
        : grant !== null
          ? grant.ceremony.text
          : "";
  const [edit, setEdit] = useState<{ readonly from: string; readonly value: string } | null>(null);
  const draft = edit !== null && edit.from === answered ? edit.value : answered;
  const onEdit = (value: string): void => {
    setEdit({ from: answered, value });
  };

  const dispatch = state.kind === "dispatched" ? state.dispatch : typing.lastDispatch;
  const ceremonyBox = (
    <CeremonyBox ceremony={ceremony} draft={draft} onEdit={onEdit} submitting={submitting} />
  );
  const body =
    phase === "revoked" && typing.revocation !== null ? (
      <RevokedBox revocation={typing.revocation} />
    ) : phase === "expired" ? (
      <ExpiredBox draft={draft} submitting={submitting} />
    ) : phase === "granted" && grant !== null ? (
      <GrantedBox
        budget={typing.budget}
        draft={draft}
        grant={grant}
        now={now}
        onEdit={onEdit}
        submitting={submitting}
      />
    ) : phase === "ceremony" ? (
      ceremonyBox
    ) : (
      <ReadOnlyBox submitting={submitting} typing={typing} />
    );

  return (
    <form action={formAction} data-console-phase={phase}>
      {dispatch === null ? null : <Chain dispatch={dispatch} />}
      {state.kind === "refused" ? (
        <p className="card-note held" role="alert" style={{ margin: "0 16px" }}>
          {state.message}
        </p>
      ) : null}
      {/* variant B keeps the pane's own composer visible and lifts the same
          ceremony over the frame; variant A confirms in place. The body is one
          value either way, so the pick never forks the states. */}
      {placement === "modal" && phase === "ceremony" ? (
        <>
          <ReadOnlyBox submitting={submitting} typing={typing} />
          <div
            aria-labelledby="console-ceremony-heading"
            aria-modal
            className="cc-modal"
            role="dialog"
          >
            <section className="panel">
              <header>
                <h2 id="console-ceremony-heading">{COPY.ceremonyHeading}</h2>
                <span className="sub">one presentation · 60 seconds</span>
              </header>
              {ceremonyBox}
            </section>
          </div>
        </>
      ) : (
        body
      )}
    </form>
  );
}
