"use client";

import Link from "next/link";
import { useActionState } from "react";
import type { ReactElement } from "react";
import { LinkThreadGlyph, TicketGlyph } from "./glyphs";
import type { InboxPromotionState, InboxPromotionTicketChoice } from "@/mutate/types";

const INITIAL_STATE: InboxPromotionState = { kind: "idle" };

/**
 * Give this conversation a ticket, so the pane above it has work to show.
 *
 * One select and one button. The default choice creates a ticket from the
 * thread; the rest are the tickets the server-side Board read actually
 * returned, so the picker can name no ticket the command would refuse. The
 * link is immutable in the record and in both directions, which is why this
 * control disappears the moment it succeeds rather than offering to do it
 * again.
 */
export function LinkTicket({
  action,
  choices,
  notice,
}: {
  readonly action: (state: InboxPromotionState, formData: FormData) => Promise<InboxPromotionState>;
  readonly choices: readonly InboxPromotionTicketChoice[];
  /** Why the list is short, when a Board read did not answer. */
  readonly notice: string | null;
}): ReactElement {
  const [state, formAction, pending] = useActionState(action, INITIAL_STATE);
  if (state.kind === "promoted") {
    return (
      <div aria-live="polite" className="cw-composer">
        <p className="cw-said">
          <span className="verdict v-pass">linked</span>
          <Link className="cw-art" href={`/ticket/${encodeURIComponent(state.ticketId)}`}>
            <TicketGlyph />
            {state.ticketId.slice(0, 8)}
          </Link>
        </p>
      </div>
    );
  }
  return (
    <div className="cw-composer">
      <form action={formAction} className="cw-box">
        <div className="cw-bar">
          <span className="cw-as" title={notice ?? "the tickets this project's board returned"}>
            <LinkThreadGlyph />
          </span>
          <select
            aria-label="Ticket to link to this conversation"
            className="field"
            defaultValue=""
            disabled={pending}
            name="ticket_id"
            style={{ height: "28px", minHeight: "28px", padding: "0 9px", flex: "1 1 auto" }}
          >
            <option value="">new ticket from this conversation</option>
            {choices.length === 0 ? null : (
              <optgroup label="link an existing ticket">
                {choices.map((choice) => (
                  <option key={choice.ticketId} value={choice.ticketId}>
                    {choice.projectKey}: {choice.title}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
          <button className="btn" disabled={pending} type="submit">
            {pending ? "Linking…" : "Link"}
          </button>
        </div>
      </form>
      {state.kind === "refused" ? (
        <p className="cw-said" role="alert">
          <span className="verdict v-held">refused</span> {state.message}
        </p>
      ) : null}
    </div>
  );
}
