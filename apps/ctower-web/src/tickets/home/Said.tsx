import type { ReactElement } from "react";
import type { AuditEvent } from "@ctower/client";
import { Button, Textarea } from "../../ui/primitives";
import { Sent } from "../Sent";
import { useComment } from "../useComment";
import { clockWords, whenWords } from "../words";
import { Absent, Section } from "./parts";

type Said = Extract<AuditEvent, { readonly kind: "ticket.comment_added" }>;

/**
 * What has been said on this ticket, and the way to say something.
 *
 * A note is a recorded act like any other, so the notes are the record's own
 * `ticket.comment_added` events read back rather than a second store this
 * screen keeps. They are quoted as they were written; a console that trimmed or
 * summarised somebody's words would be editing the record on the way out.
 *
 * Who wrote one is not drawn. The event answers with an `actor_principal_id`
 * and no declared read turns one into a name — the same absence the custody
 * section names, and it is said once on the page rather than on every note.
 */
export function Notes({
  ticketId,
  events,
  now,
  onSaid,
}: {
  readonly ticketId: string;
  readonly events: readonly AuditEvent[];
  readonly now: number;
  /** Re-read the record once it has taken the note, so the list is the record's. */
  readonly onSaid: () => void;
}): ReactElement {
  const comment = useComment(ticketId, onSaid);
  const notes = events.filter(isSaid);

  return (
    <Section title="Said on it" note={notes.length === 0 ? null : `${String(notes.length)} so far`}>
      {notes.length === 0 ? (
        <Absent>Nothing has been said on this ticket yet.</Absent>
      ) : (
        notes.map((note) => (
          <div key={note.event_id} className="mb-4">
            <p className="m-0 text-xs text-muted">
              {clockWords(note.occurred_at)} · {whenWords(note.occurred_at, now)}
            </p>
            <p className="mt-0.5 mb-0 text-sm">{note.payload.body}</p>
          </div>
        ))
      )}

      <Textarea
        rows={2}
        value={comment.typed}
        placeholder="Add a note…"
        aria-label="Add a note"
        onChange={(event): void => {
          comment.setTyped(event.target.value);
        }}
      />
      <div className="mt-2 flex items-center gap-2">
        <Button size="sm" disabled={!comment.armed} onClick={comment.send}>
          Say it
        </Button>
      </div>
      {comment.sent === null ? null : (
        <Sent
          sent={comment.sent}
          doing="Recording this note"
          nothingHappened="Nothing was recorded."
          onRetry={comment.retry}
          receipt={
            comment.sent.kind === "answered" ? (
              <p className="m-0 text-sm text-muted">
                {comment.sent.value.durability_state === "accepted"
                  ? "Recorded."
                  : "ctower took the note and has not confirmed it is durable."}
              </p>
            ) : null
          }
        />
      )}
    </Section>
  );
}

function isSaid(event: AuditEvent): event is Said {
  return event.kind === "ticket.comment_added";
}
