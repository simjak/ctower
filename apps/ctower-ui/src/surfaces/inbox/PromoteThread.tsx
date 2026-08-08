"use client";

import Link from "next/link";
import { useActionState } from "react";
import type { ReactElement } from "react";
import type { InboxPromotionState, InboxPromotionTicketChoice } from "@/mutate/types";

const INITIAL_STATE: InboxPromotionState = { kind: "idle" };

function ticketHref(ticketId: string): string {
  return `/ticket/${encodeURIComponent(ticketId)}`;
}

export function PromoteThread({
  action,
  choices,
  pickerNotice,
}: {
  readonly action: (state: InboxPromotionState, formData: FormData) => Promise<InboxPromotionState>;
  readonly choices: readonly InboxPromotionTicketChoice[];
  readonly pickerNotice: string | null;
}): ReactElement {
  const [state, formAction, pending] = useActionState(action, INITIAL_STATE);
  if (state.kind === "promoted") {
    return (
      <section className="panel" style={{ marginTop: "16px" }} aria-live="polite">
        <header>
          <h2>Ticket linked</h2>
          <span className="sub">server-authorized</span>
        </header>
        <div className="body">
          <p>
            <Link className="name" href={ticketHref(state.ticketId)}>
              ticket {state.ticketId.slice(0, 8)}
            </Link>
          </p>
          <p>
            {state.outcome === "ticket_created"
              ? "Created from this thread and linked in both directions."
              : "Linked to this thread in both directions."}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section
      className="panel"
      style={{ marginTop: "16px" }}
      aria-labelledby="promote-thread-heading"
    >
      <header>
        <h2 id="promote-thread-heading">Promote</h2>
        <span className="sub">server-authorized</span>
      </header>
      <form className="steer-box" action={formAction}>
        <div className="hd">
          <span className="k">Ticket</span>
          <span className="note">Create from this thread, or link one existing ticket.</span>
        </div>
        <div className="hd" style={{ marginBottom: 0 }}>
          <label style={{ flex: "1 1 240px", minWidth: 0 }}>
            <span className="note">Ticket to link</span>
            <select
              className="field"
              defaultValue=""
              disabled={pending}
              name="ticket_id"
              style={{ height: "36px", minHeight: "36px", padding: "0 11px", width: "100%" }}
            >
              <option value="">Create a new ticket from this thread</option>
              {choices.length === 0 ? null : (
                <optgroup label="Link an existing ticket">
                  {choices.map((choice) => (
                    <option key={choice.ticketId} value={choice.ticketId}>
                      {choice.projectKey}: {choice.title} ({choice.ticketId.slice(0, 8)})
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </label>
          <button className="btn" disabled={pending} type="submit">
            {pending ? "Promoting…" : "Promote thread"}
          </button>
        </div>
        {pickerNotice === null ? null : <p className="note">{pickerNotice}</p>}
        {state.kind === "refused" ? (
          <p className="note" role="alert">
            {state.message}
          </p>
        ) : null}
      </form>
    </section>
  );
}
