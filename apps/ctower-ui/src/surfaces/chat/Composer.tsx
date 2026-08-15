"use client";

import { useActionState } from "react";
import type { ReactElement } from "react";
import { clockText } from "@/read/elapsed";
import { SendGlyph } from "./glyphs";
import type { InboxSendState } from "@/mutate/types";
import type { InboxAcceptedMessage, InboxSendState as SendState } from "@/mutate/types";
import type { InboxCorrespondent } from "@/read/interface";

const INITIAL_STATE: InboxSendState = { kind: "idle" };

/** The words the box is still holding for the sender, if it is holding any. */
function held(state: SendState): string {
  return state.kind === "refused" || state.kind === "pending" ? state.text : "";
}

/**
 * The message the record accepted but the projection has not folded yet.
 *
 * The thread read is built from events *after* a command commits, so for a
 * moment it does not carry a message the record has already taken — and a
 * sender who has to reload to see what they just typed is not chatting with
 * anybody. `settled` is the projection's own message identities, so this turn
 * disappears the instant the thread carries it: the same message is never drawn
 * twice, and nothing is drawn that the record did not answer with.
 */
function AcceptedTurn({ message }: { readonly message: InboxAcceptedMessage }): ReactElement {
  return (
    <div aria-live="polite" className="cw-fresh">
      <div className="cw-turn mine">
        <div className="by">
          <span className="nm">{message.from}</span>
          <span className="at" title={`message ${message.position.toString()} on this thread`}>
            {clockText(message.sentAt)}
          </span>
        </div>
        <div className="said">{message.text}</div>
      </div>
    </div>
  );
}

/**
 * The composer: this surface's one write control on a conversation, and a real
 * one — it asks `POST /v1/inbox/messages` through a server action that holds
 * the bearer.
 *
 * It carries a single field. There is no recipient picker and no sender field,
 * because neither is this browser's to choose: the thread is bound into the
 * action from the route, and the server resolves both seats from the credential
 * it holds. What the operator sees is who the message goes out as, and that is
 * a chip rather than a sentence about authorization.
 *
 * Only an *accepted* answer draws a turn. A `202` means the durable
 * acknowledgement acceptance requires has not committed, so nothing is drawn —
 * the words stay in the field, the line under the box says the server has not
 * confirmed them, and pressing again retries that same message under the
 * identity the first attempt minted. A message the record has not promised to
 * keep, shown as one it has, is the one thing a chat surface must never do.
 */
export function ChatComposer({
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
  const words = held(state);
  const accepted =
    state.kind === "sent" && !settled.includes(state.message.messageId) ? state.message : null;
  return (
    <>
      {accepted === null ? null : <AcceptedTurn message={accepted} />}
      <div className="cw-composer">
        <form action={formAction} className="cw-box">
          <textarea
            aria-label={`Message ${correspondent.recipient}`}
            // a refusal and an unconfirmed send hand the words back; retyping a
            // message the server never took is the one cost this control has no
            // excuse for
            defaultValue={words}
            disabled={submitting}
            key={words === "" ? "fresh" : "held"}
            name="text"
            placeholder={`Message ${correspondent.recipient}…`}
            required
            rows={2}
          />
          <div className="cw-bar">
            <span className="cw-as" title="the server authorizes and records every message">
              as <b>{correspondent.sender}</b>
            </span>
            <span className="grow" />
            <button
              aria-label={state.kind === "pending" ? "Send again" : "Send"}
              className="cw-send"
              disabled={submitting}
              title={state.kind === "pending" ? "Send again" : "Send"}
              type="submit"
            >
              <SendGlyph />
            </button>
          </div>
        </form>
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
    </>
  );
}
