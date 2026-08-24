import type { ReactElement } from "react";
import type { RequestRow } from "@ctower/client";
import { useLedger } from "../../requests/useLedger";
import { whenWords } from "../words";
import { Absent, Answered, Section } from "./parts";

/**
 * Why this ticket exists, in the words somebody actually said.
 *
 * The request ledger keeps what was asked for and which tickets were raised to
 * answer it, so the join is the record's own: a request names this ticket in
 * `required_ticket_ids` or `optional_ticket_ids`. Nothing here is summarised —
 * the request's text is quoted as it was captured, because a request restated
 * by a console is no longer the thing that was asked for.
 *
 * A ticket nobody raised from a request is the ordinary case, not a gap, and
 * the section says so in one line rather than drawing an empty quotation.
 */
export function Why({
  projectKey,
  ticketId,
  now,
}: {
  readonly projectKey: string;
  readonly ticketId: string;
  readonly now: number;
}): ReactElement {
  const ledger = useLedger(projectKey, 0);
  const asked =
    ledger.kind === "answered"
      ? (ledger.value.rows.find((row) => answers(row, ticketId)) ?? null)
      : null;

  return (
    <Section
      title="Why it exists"
      note={asked === null ? null : `Asked ${whenWords(asked.created_at, now)}`}
    >
      <Answered answer={ledger} asking="Reading what was asked for">
        {asked === null ? (
          <Absent>No request in this project's ledger names this ticket.</Absent>
        ) : (
          <blockquote className="m-0 max-w-[46ch] text-lg leading-relaxed">
            “{asked.content}”
          </blockquote>
        )}
      </Answered>
    </Section>
  );
}

function answers(row: RequestRow, ticketId: string): boolean {
  return row.required_ticket_ids.includes(ticketId) || row.optional_ticket_ids.includes(ticketId);
}
