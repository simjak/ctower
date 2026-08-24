import { ChevronLeft } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Chip,
  Mono,
  Textarea,
} from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import { cn } from "../../ui/cn";
import { Fact, Instant, laneWord } from "../../tickets/facts";
import { ageOf, TICKETS } from "./fixtures";
import { Custody, Happened, Unbuilt } from "./TicketHomeParts";

/** The ticket the bench opens. The first one, so the shot is reproducible. */
const ONE = TICKETS[0];

/**
 * One ticket, as a page — the operator's factory card, drawn to the record.
 *
 * His mock has nine sections. Four of them are answers the record already
 * gives: the stages this ticket has walked, who has held it and for how long,
 * what has happened to it, and the changes recorded against it. Those are
 * drawn as facts. The rest — acceptance criteria, evidence slots, assets,
 * metrics — have no read behind them, so they are drawn as what they are and
 * take nothing: an empty frame that looks like a section is a promise this
 * console cannot keep.
 */
export function TicketHome({ onBack }: { readonly onBack: () => void }): ReactElement {
  if (ONE === undefined) {
    throw new Error("the bench has no ticket to draw");
  }
  return (
    <>
      <nav aria-label="Trail" className="mb-3 flex items-center gap-1.5 text-2xs text-muted">
        <Button variant="quiet" size="sm" className="-ml-2.5" onClick={onBack}>
          <ChevronLeft /> Tickets
        </Button>
        <span aria-hidden>›</span>
        <Mono className="text-fg">{ONE.key}</Mono>
      </nav>

      <header className="mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Mono className="text-fg">{ONE.key}</Mono>
          <Chip>{laneWord(ONE.lane)}</Chip>
          <Chip>{ONE.priority}</Chip>
          {ONE.waiting ? (
            <span className="flex items-center gap-1 text-2xs text-amber-ink">
              <Mark name="warn" /> a person is waited on
            </span>
          ) : null}
          <span className="flex-1" />
          <span className="text-2xs text-muted">raised {ageOf(ONE.raisedAt)} ago</span>
        </div>
        <h1 className="mt-1.5 mb-0 text-xl leading-tight font-bold tracking-[-0.02em]">
          {ONE.title}
        </h1>
      </header>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4">
          <Stages />
          <Happened />
          <Note />
          <Unbuilt />
        </div>
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>This ticket</CardTitle>
            </CardHeader>
            <CardBody className="py-1">
              <Fact label="Raised">
                <Instant at={ONE.raisedAt} />
              </Fact>
              <Fact label="Priority">{ONE.priority}</Fact>
              <Fact label="Standing">{laneWord(ONE.lane)}</Fact>
              <Fact label="Stage">{ONE.stage ?? "—"}</Fact>
            </CardBody>
          </Card>
          <Custody />
          <Changes />
        </div>
      </div>
    </>
  );
}

/**
 * The stages this ticket has entered, in the order it entered them.
 *
 * Every cell is a stage the record put it in. The stages ahead are not drawn:
 * no read answers with a workflow's definition, so a row of empty cells to the
 * right would be a plan this console invented for the factory.
 */
function Stages(): ReactElement {
  const walked = [
    { stage: "Think", at: "2026-08-24T19:12:00Z" },
    { stage: "Plan", at: "2026-08-24T19:20:00Z" },
    { stage: "Design", at: "2026-08-24T19:31:00Z" },
  ];
  return (
    <section aria-label="Stages">
      <div className="mb-2 text-2xs text-muted">STAGES</div>
      <ol className="m-0 flex list-none flex-wrap gap-1.5 p-0">
        {walked.map((entry, index) => (
          <li key={entry.stage} className="min-w-0">
            <Cell stage={entry.stage} at={entry.at} here={index === walked.length - 1} />
          </li>
        ))}
      </ol>
    </section>
  );
}

function Cell({
  stage,
  at,
  here,
}: {
  readonly stage: string;
  readonly at: string;
  readonly here: boolean;
}): ReactElement {
  return (
    <div
      className={cn(
        "rounded-sm border px-3 py-1.5",
        here ? "border-amber bg-amber/10" : "border-line"
      )}
    >
      <span className={cn("text-sm", here ? "font-semibold text-fg" : "text-muted")}>{stage}</span>
      <div className="mt-0.5 flex items-baseline gap-2">
        {here ? <span className="text-2xs text-amber-ink">here</span> : null}
        <Instant at={at} />
      </div>
    </div>
  );
}

/** A note on the ticket. The record keeps these, so the box is a real one. */
function Note(): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Add a note</CardTitle>
      </CardHeader>
      <CardBody className="space-y-2">
        <Textarea rows={2} defaultValue="" placeholder="What should whoever picks this up know?" />
        <div className="flex">
          <span className="flex-1" />
          <Button size="sm">Add it</Button>
        </div>
      </CardBody>
    </Card>
  );
}

/**
 * The changes recorded against this ticket. The repository is the one the
 * operator typed, at the length a person reads one; the reference beside it is
 * the change's own number, which is also a thing he says out loud.
 */
function Changes(): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Changes</CardTitle>
      </CardHeader>
      <CardBody className="py-1">
        <Line label="github/simjak/ctower">#582</Line>
        <Line label="github/simjak/ctower">#581</Line>
      </CardBody>
    </Card>
  );
}

function Line({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="flex items-baseline gap-3 border-b border-line py-1.5 last:border-b-0">
      <span className="min-w-0 flex-1 truncate text-sm">{label}</span>
      <span className="shrink-0 text-2xs text-muted">{children}</span>
    </div>
  );
}
