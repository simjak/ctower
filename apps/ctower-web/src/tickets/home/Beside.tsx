import type { ReactElement } from "react";
import type { BoardCard, ChangeReference, TicketResource } from "@ctower/client";
import { Chip } from "../../ui/primitives";
import { ageWords, spanWords, stageWord, whenWords } from "../words";
import type { StandingWorkflow } from "../workflow";
import { Absent, Aside, Fact } from "./parts";

/**
 * The facts that sit beside a ticket rather than inside its story: what was
 * changed for it, how far that change travelled, and how the work has gone.
 *
 * Every one is the board card's own answer or a subtraction of two recorded
 * instants. Nothing here is estimated, and the one thing a ticket genuinely
 * cannot keep — a file — is said once, in a line, rather than drawn as an empty
 * frame somebody would try to drop something into.
 */
export function Beside({
  ticket,
  card,
  standing,
  now,
}: {
  readonly ticket: TicketResource;
  readonly card: BoardCard | null;
  readonly standing: StandingWorkflow | null;
  readonly now: number;
}): ReactElement {
  return (
    <>
      {card === null || card.change_references.length === 0 ? null : (
        <Aside title="The work">
          {card.change_references.map((change) => (
            <Fact key={change.change_identity} label={changeWord(change)}>
              <Change change={change} now={now} />
            </Fact>
          ))}
        </Aside>
      )}

      {card === null ? null : <Reached card={card} />}

      <Aside title="How it is going">
        <Fact label="Age">{ageWords(ticket.created_at, now)}</Fact>
        {standing === null ? null : (
          <Fact label="Steps walked">
            {String(standing.walked.length)}, now at {stageWord(standing.stage)}
          </Fact>
        )}
        {standing === null ? null : <Steps standing={standing} now={now} />}
      </Aside>

      <Absent>Pictures and files cannot be kept on a ticket yet.</Absent>
    </>
  );
}

/** The number a person says out loud for a change, when the record kept one. */
function changeWord(change: ChangeReference): string {
  return /^\d+$/.test(change.change_identity) ? `Change ${change.change_identity}` : "A change";
}

/**
 * A change, as the link it is when this console can address it honestly.
 *
 * The record keeps a web address for the change; that is the operator's own
 * data, and `DESIGN.md` draws his repository as a link he can follow. A
 * reference that is not a web address is not turned into one — the row still
 * says the change exists and when it was recorded.
 */
function Change({
  change,
  now,
}: {
  readonly change: ChangeReference;
  readonly now: number;
}): ReactElement {
  const recorded = whenWords(change.recorded_at, now);
  if (!/^https?:\/\//.test(change.reference)) {
    return <span className="text-muted">Recorded {recorded.toLowerCase()}</span>;
  }
  return (
    <a href={change.reference} target="_blank" rel="noreferrer" className="text-fg underline">
      Open it
    </a>
  );
}

/**
 * How far the work travelled, from the closed set of facts the board keeps.
 *
 * `delivery_facts` is an enum of five in the authored board schema, so each row
 * is one of them said in the operator's words and nothing is inferred from a
 * neighbour: staging is not "yes" because production is.
 */
function Reached({ card }: { readonly card: BoardCard }): ReactElement {
  const facts = new Set(card.delivery_facts);
  return (
    <Aside title="Where it reached">
      <Fact label="Merged">
        {facts.has("change_merged") ? <Chip tone="ok">yes</Chip> : "not yet"}
      </Fact>
      <Fact label="Staging">
        {facts.has("staging_verified") ? <Chip tone="ok">checked</Chip> : "not yet"}
      </Fact>
      <Fact label="Live">
        {facts.has("production_verified") ? <Chip tone="ok">checked</Chip> : "not yet"}
      </Fact>
      {facts.has("rolled_back") ? (
        <Fact label="Rolled back">
          <Chip tone="amber">yes</Chip>
        </Fact>
      ) : null}
      {facts.has("incident_open") ? (
        <Fact label="Incident">
          <Chip tone="amber">open</Chip>
        </Fact>
      ) : null}
    </Aside>
  );
}

/**
 * How long each step took, as bars in proportion to one another.
 *
 * Each span is the gap between two recorded entries, and the last one runs to
 * now because the ticket is still standing in it. There is no axis and no
 * number per bar: it is the shape of the walk, and the exact spans are on each
 * bar's own title for anyone who wants them.
 */
function Steps({
  standing,
  now,
}: {
  readonly standing: StandingWorkflow;
  readonly now: number;
}): ReactElement {
  const spans = standing.walked.map((entry, index) => {
    const from = Date.parse(entry.enteredAt);
    const next = standing.walked[index + 1];
    const to = next === undefined ? now : Date.parse(next.enteredAt);
    return {
      stage: entry.stage,
      seconds: Number.isFinite(from) && Number.isFinite(to) ? Math.max(0, (to - from) / 1000) : 0,
    };
  });
  const longest = Math.max(...spans.map((span) => span.seconds), 1);
  return (
    <Fact label="Time per step">
      <span className="inline-flex h-4 items-end gap-[3px]">
        {spans.map((span) => (
          <span
            key={span.stage}
            title={`${stageWord(span.stage)} — ${spanWords(span.seconds)}`}
            className="block w-1.5 rounded-xs bg-amber/40"
            style={{ height: `${String(Math.max(3, (span.seconds / longest) * 16))}px` }}
          />
        ))}
      </span>
    </Fact>
  );
}
