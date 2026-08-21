"use client";

import Link from "next/link";
import { useActionState } from "react";
import type { ReactElement } from "react";
import { SendGlyph } from "./glyphs";
import { addresslessReason, PLANE_WHY, SEAT_COMMAND, UNADDRESSABLE } from "./plane";
import type { InboxComposeState } from "@/mutate/types";
import type { InboxCorrespondentChoice, InboxCorrespondents } from "@/read/interface";

const INITIAL_STATE: InboxComposeState = { kind: "idle" };

function held(state: InboxComposeState): string {
  return state.kind === "refused" || state.kind === "pending" ? state.text : "";
}

function chosen(state: InboxComposeState): string {
  return state.kind === "refused" || state.kind === "pending" ? state.to : "";
}

/**
 * The listed seats, filed under the project each one belongs to.
 *
 * The correspondents read carries a `projectKey` per seat and this picker used
 * to drop it, which left the reader no way to see the one thing about this
 * surface that can catch them out: the address book is the *tenant's*, not the
 * project they arrived from. Grouping restores that fact structurally, so the
 * line above the list stays a line rather than becoming the paragraph D9
 * forbids. The order inside a group is the record's own.
 */
function byProject(
  choices: readonly InboxCorrespondentChoice[]
): readonly (readonly [string, readonly string[]])[] {
  const filed = new Map<string, string[]>();
  for (const choice of choices) {
    const seats = filed.get(choice.projectKey);
    if (seats === undefined) {
      filed.set(choice.projectKey, [choice.seatKey]);
    } else {
      seats.push(choice.seatKey);
    }
  }
  return [...filed];
}

/**
 * Start a conversation with a seat the record knows.
 *
 * Two fields, and neither is an identity claim. The message is the operator's.
 * The recipient is one of the seats *the server itself listed* — and that list
 * is the set of addresses the command accepts, not the wider set of seats that
 * exist — so this browser can name an address but never invent one, and the
 * server re-resolves the seat and derives the sender from the credential it
 * holds on every send. There is no sender field, because that was never this
 * browser's to choose.
 *
 * The thread is nobody's to choose either: the server derives one per unordered
 * seat pair, so pressing send twice on one seat continues one conversation
 * rather than starting two.
 *
 * An accepted compose draws the way in to the conversation it opened, because
 * the list beside it is a projection folded from events *after* the command
 * commits and does not carry the new thread yet. A `202` draws nothing at all —
 * the words and the seat stay where they were and the button offers to send
 * that same message again.
 */
export function NewThread({
  action,
  correspondents,
}: {
  readonly action: (state: InboxComposeState, formData: FormData) => Promise<InboxComposeState>;
  readonly correspondents: InboxCorrespondents;
}): ReactElement {
  const [state, formAction, submitting] = useActionState(action, INITIAL_STATE);
  const projects = byProject(correspondents.choices);
  const empty = correspondents.choices.length === 0;
  const words = held(state);
  const seat = chosen(state);
  const idle = empty || submitting;
  return (
    <div className="cw-main" aria-labelledby="compose-heading">
      <div className="cw-head">
        <h2 id="compose-heading">New conversation</h2>
        <span className="grow" />
        <Link className="cw-act" href="/inbox" title="Close">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
            <path
              d="M4 4l8 8M12 4l-8 8"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
        </Link>
      </div>
      {/* the scroll region exists only once there is a turn in it; an empty one
          grew to fill the pane and pushed the box a screen's height down */}
      {state.kind === "started" ? (
        <div className="cw-scroll">
          <div aria-live="polite" className="cw-turn mine">
            <div className="by">
              <span className="nm">{state.message.from}</span>
              <Link className="cw-art" href={`/inbox?thread=${encodeURIComponent(state.threadId)}`}>
                open the conversation
              </Link>
            </div>
            <div className="said">{state.message.text}</div>
          </div>
        </div>
      ) : null}
      <div className="cw-composer">
        <form action={formAction} className="cw-box">
          <div className="cw-bar" style={{ paddingBottom: 0 }}>
            <span className="cw-as">to</span>
            <select
              aria-label="Seat to write to"
              className="field"
              defaultValue={seat}
              disabled={idle}
              key={seat === "" ? "fresh" : "held"}
              name="to"
              required
              style={{ height: "28px", minHeight: "28px", padding: "0 9px", flex: "1 1 auto" }}
              title={empty ? addresslessReason(correspondents.sender) : PLANE_WHY}
            >
              <option value="">seat…</option>
              {projects.map(([project, seats]) => (
                <optgroup key={project} label={project}>
                  {seats.map((key) => (
                    <option key={key} value={key}>
                      {key}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <textarea
            aria-label="Message to a seat"
            defaultValue={words}
            disabled={idle}
            key={words === "" ? "fresh" : "held"}
            name="text"
            placeholder="Start a conversation…"
            required
            rows={3}
          />
          <div className="cw-bar">
            <span className="cw-as">
              as <b>{correspondents.sender}</b>
            </span>
            <span className="grow" />
            <button
              aria-label={state.kind === "pending" ? "Send again" : "Send"}
              className="cw-send"
              disabled={idle}
              title={state.kind === "pending" ? "Send again" : "Send"}
              type="submit"
            >
              <SendGlyph />
            </button>
          </div>
        </form>
        {/* an empty state is one sentence and one action, and the action here is
            the command that mints the seat row an address is */}
        {empty ? (
          <p className="cw-said">
            <span className="verdict v-held">no address</span>{" "}
            {addresslessReason(correspondents.sender)}
            {correspondents.sender === UNADDRESSABLE ? (
              <code className="mono">{SEAT_COMMAND}</code>
            ) : null}
          </p>
        ) : null}
        {state.kind === "pending" ? (
          <p className="cw-said" role="status">
            <span className="verdict v-changes">not confirmed</span> {state.message}
          </p>
        ) : null}
        {state.kind === "refused" ? (
          <p className="cw-said" role="alert">
            <span className="verdict v-held">refused</span> {state.message}
          </p>
        ) : null}
      </div>
    </div>
  );
}
