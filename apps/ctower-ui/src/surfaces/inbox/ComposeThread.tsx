"use client";

import { useActionState } from "react";
import type { ReactElement } from "react";
import type { InboxComposeState } from "@/mutate/types";
import type { InboxCorrespondents } from "@/read/interface";
import { ThreadMessage } from "./ThreadMessage";

const INITIAL_STATE: InboxComposeState = { kind: "idle" };
const JUST_SENT = "just sent";
const NOT_CONFIRMED = "not confirmed";
/** The record's own name for a principal that holds no seat row. */
const UNADDRESSABLE = "unaddressable";
const PICKER_HELP =
  "A seat is listed only where the record can deliver to it: registered, and not sharing its " +
  "address with another seat. Sending opens the conversation with that seat, or continues the " +
  "one you already have.";
const NO_SEATS = "The record lists no other seat this server can write to, so there is nobody yet.";
const NO_ADDRESS =
  "This server's principal holds no registered seat, so it has no address to write from. " +
  "Register one in the record to start conversations here.";
const RECORDED = "the server authorizes and records every message";

/** The words the box is still holding for the sender, if it is holding any. */
function held(state: InboxComposeState): string {
  return state.kind === "refused" || state.kind === "pending" ? state.text : "";
}

/** The seat the sender picked and has not sent to yet, if there is one. */
function chosen(state: InboxComposeState): string {
  return state.kind === "refused" || state.kind === "pending" ? state.to : "";
}

/** What pressing the box does next, said on the button itself. */
function submitLabel(state: InboxComposeState, submitting: boolean): string {
  if (submitting) {
    return "Sending…";
  }
  return state.kind === "pending" ? "Retry" : "Send";
}

/**
 * The addresses on offer: the record's own list, in the record's own order.
 *
 * Nothing is folded, dropped or added here, because the list already *is* the
 * set of addresses the command accepts: the record leaves out a key two seats
 * share, the reader's own seat, and everybody at all when this principal holds
 * no seat to write from. A picker that edited that list could only start
 * disagreeing with the command it exists to reach.
 */
function addresses(correspondents: InboxCorrespondents): readonly string[] {
  return correspondents.choices.map((choice) => choice.seatKey);
}

/** Who the record would file this message under, when it can file one at all. */
function provenance(sender: string): string {
  return sender === UNADDRESSABLE ? RECORDED : `as ${sender} · ${RECORDED}`;
}

/** Why the box is offering nobody: no address to write from, or nobody to write to. */
function emptyReason(sender: string): string {
  return sender === UNADDRESSABLE ? NO_ADDRESS : NO_SEATS;
}

/**
 * The compose box: start a conversation with a seat the record knows.
 *
 * It carries two fields, and neither is an identity claim. The message is the
 * operator's. The recipient is one of the seats *the server itself listed* —
 * and that list is the set of addresses the command accepts, not the wider set
 * of seats that exist — so this browser can name an address but never invent
 * one, every address it offers is one the record can deliver to, and the server
 * re-resolves the seat and derives the sender from the credential it holds on
 * every send. There is no sender field, because that was never this browser's
 * to choose.
 *
 * The thread is nobody's to choose. The server derives one per unordered seat
 * pair, so pressing Send twice on one seat continues one conversation rather
 * than starting two, and the thread the notification mirror already opened for
 * that pair is the thread this lands in.
 *
 * An accepted message is rendered here, once, from the command's own answer,
 * beside the link into the thread it opened. The list below is a projection
 * folded from events *after* the command commits, so for a moment it does not
 * carry a thread the record has already accepted — and an operator who has to
 * reload to see the conversation they just started is not chatting with anyone.
 *
 * When the record answers without accepting, this box draws no message at all:
 * the words stay in the field, the seat stays picked, the button offers to send
 * that same message again, and the line underneath says the server has not
 * confirmed it. A conversation the record has not promised to keep, shown as
 * one it has, is the one thing a chat surface must never do.
 */
export function ComposeThread({
  action,
  correspondents,
}: {
  readonly action: (state: InboxComposeState, formData: FormData) => Promise<InboxComposeState>;
  readonly correspondents: InboxCorrespondents;
}): ReactElement {
  const [state, formAction, submitting] = useActionState(action, INITIAL_STATE);
  const seats = addresses(correspondents);
  const words = held(state);
  const seat = chosen(state);
  const idle = seats.length === 0 || submitting;
  return (
    <section className="panel" style={{ marginTop: "16px" }} aria-labelledby="compose-heading">
      <header>
        <h2 id="compose-heading">New message</h2>
        <span className="sub">server-authorized</span>
      </header>
      {state.kind === "started" ? (
        <div aria-live="polite">
          <ThreadMessage
            href={`/inbox?thread=${encodeURIComponent(state.threadId)}`}
            message={state.message}
            note={JUST_SENT}
          />
        </div>
      ) : null}
      <form className="steer-box" action={formAction}>
        <div className="hd">
          <span className="k">To</span>
          <span className="note">{provenance(correspondents.sender)}</span>
        </div>
        <div className="hd" style={{ marginBottom: "9px" }}>
          <label style={{ flex: "1 1 240px", minWidth: 0 }} title={PICKER_HELP}>
            <select
              aria-label="Seat to write to"
              className="field"
              defaultValue={seat}
              disabled={idle}
              key={seat === "" ? "fresh" : "held"}
              name="to"
              required
              style={{ height: "36px", minHeight: "36px", padding: "0 11px", width: "100%" }}
            >
              <option value="">Pick a seat…</option>
              {seats.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="steer-row">
          <textarea
            aria-label="Message to a seat"
            className="field"
            // an accepted send clears the box; a refusal and an unconfirmed
            // send hand the words back, because retyping a message the server
            // never took — or never said it took — is the one cost this control
            // has no excuse for
            defaultValue={words}
            disabled={idle}
            key={words === "" ? "fresh" : "held"}
            name="text"
            placeholder="Start a conversation…"
            required
            rows={2}
          />
          <button className="btn" disabled={idle} type="submit">
            {submitLabel(state, submitting)}
          </button>
        </div>
        {seats.length === 0 ? <p className="note">{emptyReason(correspondents.sender)}</p> : null}
        {state.kind === "pending" ? (
          <p className="note" role="status">
            <span className="verdict v-changes">{NOT_CONFIRMED}</span> {state.message}
          </p>
        ) : null}
        {state.kind === "refused" ? (
          <p className="note" role="alert">
            {state.message}
          </p>
        ) : null}
      </form>
    </section>
  );
}
