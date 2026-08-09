"use client";

import { useActionState } from "react";
import type { ReactElement } from "react";
import type { InboxSendState } from "@/mutate/types";
import type { InboxCorrespondent } from "@/read/interface";
import { ThreadMessage } from "./ThreadMessage";

const INITIAL_STATE: InboxSendState = { kind: "idle" };
const JUST_SENT = "just sent";
const NOT_CONFIRMED = "not confirmed";

/** The words the box is still holding for the sender, if it is holding any. */
function held(state: InboxSendState): string {
  return state.kind === "refused" || state.kind === "pending" ? state.text : "";
}

/** What pressing the box does next, said on the button itself. */
function submitLabel(state: InboxSendState, submitting: boolean): string {
  if (submitting) {
    return "Sending…";
  }
  return state.kind === "pending" ? "Retry" : "Send";
}

/**
 * The thread's send box, attached under the messages it appends to.
 *
 * It carries one field. There is no recipient picker and no sender field,
 * because neither is this browser's to choose: the thread is bound into the
 * action from the route, and the server resolves both seats from the
 * credential it holds.
 *
 * An accepted message is rendered here, once, from the command's own answer.
 * The list above is a projection folded from events *after* the command
 * commits, so for a moment it does not carry a message the record has already
 * accepted — and a sender who has to reload to see what they just typed is not
 * chatting with anybody. `settled` is that list's own message identities, so
 * the row disappears from here the moment the projection carries it: the same
 * message is never drawn twice, and nothing is drawn that the record did not
 * answer with.
 *
 * Only an accepted answer draws that row. When the record answers without
 * accepting, this box draws no message at all: the words stay in the field
 * where they were typed, the button offers to send that same message again,
 * and the line underneath says the server has not confirmed it. A message the
 * record has not promised to keep, shown as one it has, is the one thing a
 * chat surface must never do.
 */
export function SendMessage({
  action,
  correspondent,
  settled,
}: {
  readonly action: (state: InboxSendState, formData: FormData) => Promise<InboxSendState>;
  readonly correspondent: InboxCorrespondent;
  /** Message identities the thread read already carries. */
  readonly settled: readonly string[];
}): ReactElement {
  const [state, formAction, submitting] = useActionState(action, INITIAL_STATE);
  const accepted =
    state.kind === "sent" && !settled.includes(state.message.messageId) ? state.message : null;
  const words = held(state);
  return (
    <>
      {accepted === null ? null : (
        <div aria-live="polite">
          <ThreadMessage message={accepted} note={JUST_SENT} />
        </div>
      )}
      <form className="steer-box" action={formAction}>
        <div className="hd">
          <span className="k">Send to {correspondent.recipient}</span>
          <span className="note">
            as {correspondent.sender} · the server authorizes and records every message
          </span>
        </div>
        <div className="steer-row">
          <textarea
            aria-label={`Message ${correspondent.recipient}`}
            className="field"
            // an accepted send clears the box; a refusal and an unconfirmed
            // send hand the words back, because retyping a message the server
            // never took — or never said it took — is the one cost this control
            // has no excuse for
            defaultValue={words}
            disabled={submitting}
            key={words === "" ? "fresh" : "held"}
            name="text"
            placeholder={`Message ${correspondent.recipient}…`}
            required
            rows={2}
          />
          <button className="btn" disabled={submitting} type="submit">
            {submitLabel(state, submitting)}
          </button>
        </div>
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
    </>
  );
}
