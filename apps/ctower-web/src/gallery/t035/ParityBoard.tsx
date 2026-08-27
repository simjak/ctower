import type { ReactElement, ReactNode } from "react";
import { Chip } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import { cn } from "../../ui/cn";
import { clockWords, priorityWord, stageWord } from "../../tickets/words";
import {
  changesOf,
  damOf,
  freshnessOf,
  modelWord,
  overdueInStage,
  pilesOf,
  shortAge,
  started,
  statusOf,
  statusWord,
  whyOf,
  WAITING,
} from "./board";
import type { Change, Freshness, Pile, Standing, Status, Why } from "./board";

/**
 * The operator's own board, in the browser.
 *
 * His terminal groups every open ticket under the stage it stands in, in his
 * project's own order, and gives each one a row of thirteen columns saying who
 * is on it, how it is going, what changed for it and how long it has been that
 * way. This is that board, drawn from what ctower's record actually answers.
 *
 * Three departures from the terminal are the design system's law rather than
 * omissions, and each is named where it happens: the stage labels carry no hue
 * (this palette has no per-stage colour and inventing six would be inventing a
 * vocabulary), the alarm is amber rather than red (red here means dead or
 * refused, and a ticket nobody has touched is neither), and a priority renders
 * only where the record treats it as authority.
 *
 * Nothing on it moves a ticket. It is `getBoard` read as the operator reads it,
 * and where a ticket goes next is the ticket's own page.
 */
export type Draw = "today" | "attributed" | "reference";

export function ParityBoard({
  rows,
  ladder,
  draw,
  now,
  onOpen,
}: {
  readonly rows: readonly Standing[];
  /** This project's own stages, in the order work moves through them. */
  readonly ladder: readonly string[];
  readonly draw: Draw;
  readonly now: number;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  const piles = pilesOf(rows, ladder);
  const dam = damOf(piles);
  const columns = columnsFor(draw);
  return (
    <div>
      <Strip piles={piles} ladder={ladder} dam={dam} />
      <table className="w-full table-fixed border-collapse text-sm">
        <colgroup>
          {columns.map((column) => (
            <col key={column} style={widthOf(column)} />
          ))}
        </colgroup>
        <thead>
          <tr className="border-b border-line">
            {columns.map((column) => (
              <th
                key={column}
                scope="col"
                className={cn(
                  "pb-1.5 text-2xs font-medium tracking-[0.08em] text-muted uppercase",
                  alignOf(column),
                  column === "what" ? "pr-4" : "px-1"
                )}
              >
                {headOf(column, draw)}
              </th>
            ))}
          </tr>
        </thead>
        {piles.map((pile) => (
          <Group
            key={pile.stage}
            pile={pile}
            columns={columns}
            draw={draw}
            now={now}
            onOpen={onOpen}
          />
        ))}
      </table>
      {draw === "today" ? <Missing /> : null}
    </div>
  );
}

/**
 * The flow strip: every stage of this project's ladder, and the pile in each.
 *
 * The operator calls the fullest one the dam, and it is the only thing on this
 * row that earns a mark — a pipeline moves at the speed of its deepest stage,
 * and no other cell tells him where to send somebody. His terminal prints each
 * ticket's number inside the strip because the table under it is one long list;
 * here the groups beneath *are* the strip in the same order, so the strip keeps
 * the shape and the groups keep the names.
 */
function Strip({
  piles,
  ladder,
  dam,
}: {
  readonly piles: readonly Pile[];
  readonly ladder: readonly string[];
  readonly dam: string | null;
}): ReactElement {
  const held = new Map(piles.map((pile) => [pile.stage, pile.rows.length]));
  const waiting = held.get(WAITING) ?? 0;
  return (
    <div className="mb-5">
      <div className="flex items-end gap-1 border-b border-line pb-2">
        {ladder.map((stage) => (
          <Cell
            key={stage}
            word={stageWord(stage)}
            count={held.get(stage) ?? 0}
            dam={stage === dam}
          />
        ))}
      </div>
      {waiting === 0 ? null : (
        <p className="mt-2 mb-0 text-2xs text-muted">
          {waiting} more {waiting === 1 ? "ticket is" : "tickets are"} waiting to start.
        </p>
      )}
    </div>
  );
}

function Cell({
  word,
  count,
  dam,
}: {
  readonly word: string;
  readonly count: number;
  readonly dam: boolean;
}): ReactElement {
  return (
    <div className="min-w-0 flex-1">
      <div
        className={cn(
          "truncate text-2xs tracking-[0.04em] uppercase",
          count === 0 ? "text-muted opacity-55" : "text-muted",
          dam && "text-amber-ink opacity-100"
        )}
      >
        {word}
      </div>
      <div className={cn("text-sm", dam ? "font-semibold text-amber-ink" : "text-fg")}>
        {count === 0 ? <span className="text-muted opacity-40">·</span> : count}
        {dam ? <Mark name="warn" className="ml-1" /> : null}
      </div>
    </div>
  );
}

/**
 * One stage's pile.
 *
 * A whitespace gap and a small label, which is what the operator asked for in
 * place of the coloured rules an earlier draft drew — the gap is the separator
 * and the eye needs nothing else. The label is muted rather than tinted because
 * this product has one accent and spends it on states, not on categories.
 */
function Group({
  pile,
  columns,
  draw,
  now,
  onOpen,
}: {
  readonly pile: Pile;
  readonly columns: readonly Column[];
  readonly draw: Draw;
  readonly now: number;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  return (
    <tbody>
      <tr>
        <th colSpan={columns.length} scope="colgroup" className="pt-5 pb-1 text-left">
          <span className="text-2xs tracking-[0.08em] text-muted uppercase">
            {pile.stage === WAITING ? "Waiting to start" : stageWord(pile.stage)}
          </span>
          <span className="ml-2 text-2xs text-muted opacity-70">{pile.rows.length}</span>
        </th>
      </tr>
      {pile.rows.map((row) => (
        <Row
          key={row.card.ticket_id}
          standing={row}
          columns={columns}
          draw={draw}
          now={now}
          onOpen={onOpen}
        />
      ))}
    </tbody>
  );
}

function Row({
  standing,
  columns,
  draw,
  now,
  onOpen,
}: {
  readonly standing: Standing;
  readonly columns: readonly Column[];
  readonly draw: Draw;
  readonly now: number;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  const status = statusOf(standing, now);
  return (
    <tr className="border-b border-line align-top last:border-b-0 hover:bg-raised">
      {columns.map((column) => (
        <td
          key={column}
          className={cn(
            "py-2.5 align-top",
            alignOf(column),
            column === "what" ? "pr-4" : "px-1",
            // A fixed table lets an over-long cell paint across its neighbour.
            // Only the priority cell is exempt: its chip is a rounded pill wider
            // than the word inside it, and clipping one is worse than the gap.
            column === "priority" ? null : "overflow-hidden"
          )}
        >
          {cellOf(column, standing, status, draw, now, onOpen)}
        </td>
      ))}
    </tr>
  );
}

function cellOf(
  column: Column,
  standing: Standing,
  status: Status,
  draw: Draw,
  now: number,
  onOpen: (ticketId: string) => void
): ReactNode {
  const card = standing.card;
  switch (column) {
    case "ticket":
      return <span className="text-xs text-muted">{card.display_key ?? "not numbered"}</span>;
    case "priority":
      return <Priority standing={standing} draw={draw} />;
    case "what":
      return <What standing={standing} status={status} onOpen={onOpen} />;
    case "crew":
      return <Crew standing={standing} />;
    case "rate":
      return <Rate standing={standing} />;
    case "model":
      return <Model standing={standing} />;
    case "status":
      return <StatusCell standing={standing} status={status} />;
    case "rounds":
      return <Rounds standing={standing} />;
    case "change":
      return <Changes changes={changesOf(card)} />;
    case "raised":
      return <When at={standing.raisedAt} now={now} />;
    case "updated":
      return <When at={standing.updatedAt} now={now} decays />;
    case "instage":
      return <InStage standing={standing} now={now} />;
    case "age":
      return <Age at={standing.raisedAt} now={now} />;
  }
}

/**
 * Urgent, and nothing else.
 *
 * The record treats `P0` as authority — raising one is the operator's own power
 * — and treats the other two as an opinion, so his board's three-colour column
 * renders here as one word or as nothing. The reference frame draws all three,
 * so the difference is visible rather than argued about.
 */
function Priority({
  standing,
  draw,
}: {
  readonly standing: Standing;
  readonly draw: Draw;
}): ReactElement | null {
  const priority = standing.card.priority;
  if (draw === "reference") {
    return (
      <span className={cn("text-xs", priority === "P0" ? "text-amber-ink" : "text-muted")}>
        {priorityWord(priority)}
      </span>
    );
  }
  return priority === "P0" ? <Chip tone="amber">{priorityWord("P0")}</Chip> : null;
}

/**
 * What it is, whole.
 *
 * The operator's one rule for this column: never truncate. A title clipped
 * mid-word is a ticket he has to open to identify, and the whole point of the
 * board is that he does not have to. So it wraps, and everything that explains
 * the row — who it is waiting on, and why it is not moving — wraps under it
 * inside this column rather than spilling across the table.
 */
function What({
  standing,
  status,
  onOpen,
}: {
  readonly standing: Standing;
  readonly status: Status;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  const why = whyOf(standing, status);
  return (
    <>
      <button
        type="button"
        onClick={(): void => {
          onOpen(standing.card.ticket_id);
        }}
        className="m-0 block cursor-pointer border-0 bg-transparent p-0 text-left text-sm leading-snug text-fg"
      >
        {standing.card.title}
      </button>
      {standing.card.human_waiting.state === "waiting" ? (
        <span className="mt-1 inline-flex items-center text-2xs text-amber-ink">
          <Mark name="warn" />
          Needs you
        </span>
      ) : null}
      {why === null ? null : <WhyLine why={why} />}
    </>
  );
}

/**
 * Why it is stopped.
 *
 * A named blocker is drawn in the words somebody wrote, quietly: the sentence
 * is the whole fact and the row has already said Stuck. An hour in a stage with
 * nobody saying why is the alarm — his board shouts it in red, and this one
 * shouts it in amber, because red here is reserved for what the record calls
 * dead or refused and a ticket nobody has touched is neither.
 */
function WhyLine({ why }: { readonly why: Why }): ReactElement {
  if (why.kind === "named") {
    return <p className="mt-1.5 mb-0 text-2xs leading-snug text-muted">{why.said}</p>;
  }
  return (
    <p className="mt-1.5 mb-0 text-2xs leading-snug font-medium text-amber-ink">
      Nobody has said why this is stopped.
    </p>
  );
}

/**
 * Who is on it — the column this board cannot fill.
 *
 * A recorded session names its crew with a string its own caller authored, and
 * the company's roster names crews with the persona each seat is bound to. No
 * declared read joins the two, and the authored rule forbids inferring a seat
 * from a name, so the day this column is drawn is the day the assignment's seat
 * reaches the contract. The `today` frame does not draw it at all rather than
 * drawing it empty.
 */
function Crew({ standing }: { readonly standing: Standing }): ReactElement | null {
  const attributed = standing.ifAttributed;
  if (attributed === null || standing.session === null) {
    return null;
  }
  return (
    <span className="inline-flex min-w-0 items-center text-sm">
      <Mark name={standing.session.state === "working" ? "working" : "idle"} />
      <span className="truncate">{attributed.crew}</span>
    </span>
  );
}

/** Tokens a minute, which no read answers and this frame only imagines. */
function Rate({ standing }: { readonly standing: Standing }): ReactElement | null {
  const rate = standing.ifAttributed?.rate ?? null;
  return rate === null ? null : <span className="text-sm">{rate}</span>;
}

/**
 * What is at work, which the record does answer.
 *
 * A session names its model, and a model's name is a product name a person says
 * out loud rather than a reference — so on a board that cannot say *who* is
 * working, this is the column that says *what* is. A ticket with no open session
 * draws nothing here, and that absence is the operator's own no-crew alarm.
 */
function Model({ standing }: { readonly standing: Standing }): ReactElement | null {
  const session = standing.session;
  if (session === null) {
    return null;
  }
  return (
    <span className="inline-flex min-w-0 items-center text-sm">
      <Mark name={session.state === "working" ? "working" : "idle"} />
      <span className="truncate">{modelWord(session.model_ref)}</span>
    </span>
  );
}

/**
 * How it is going, computed from the record and never stamped.
 *
 * One of the five is loud. `Stalled` means an hour in a stage with no blocker
 * named and nothing at work, which is the state the operator built this column
 * to catch; the other four are quiet because they are all explicable.
 */
function StatusCell({
  standing,
  status,
}: {
  readonly standing: Standing;
  readonly status: Status;
}): ReactElement | null {
  if (!started(standing) && status === "idle") {
    return null;
  }
  return (
    <span
      className={cn(
        "text-sm",
        status === "stalled" ? "font-semibold text-amber-ink" : "text-muted"
      )}
    >
      {statusWord(status)}
    </span>
  );
}

/** How many times it has come back from review. Nothing reads this today. */
function Rounds({ standing }: { readonly standing: Standing }): ReactElement | null {
  const rounds = standing.ifAttributed?.rounds ?? 0;
  if (rounds === 0) {
    return null;
  }
  return (
    <span className={cn("text-sm", rounds >= 2 ? "text-amber-ink" : "text-muted")}>{rounds}</span>
  );
}

/**
 * What was changed for it, as the link the record already keeps.
 *
 * The change's own identity is the number a person says out loud; the address
 * beside it is where the change lives, and a change the record kept without a
 * web address is still drawn, because it still happened. A change the ticket's
 * delivery facts say landed carries the one mark this product spends on proof.
 */
function Changes({ changes }: { readonly changes: readonly Change[] }): ReactElement | null {
  if (changes.length === 0) {
    return null;
  }
  return (
    <span className="inline-flex items-center gap-1 text-sm">
      {changes.map((change) => (
        <span key={change.said} className="inline-flex items-center">
          {change.landed ? <Mark name="done" /> : null}
          {change.href === null ? (
            <span className="text-muted">{change.said}</span>
          ) : (
            <a href={change.href} target="_blank" rel="noreferrer" className="text-fg underline">
              {change.said}
            </a>
          )}
        </span>
      ))}
    </span>
  );
}

/**
 * A recorded instant, and how stale it is.
 *
 * Today's clock, because a time inside the working day is read as a time; older
 * than that and the clock stops helping, so it is said as an age. Half a day
 * with no recorded fact turns the cell amber, which is the whole of his
 * freshness decay that this palette can carry honestly.
 */
function When({
  at,
  now,
  decays = false,
}: {
  readonly at: string | null;
  readonly now: number;
  readonly decays?: boolean;
}): ReactElement | null {
  if (at === null) {
    return null;
  }
  const fresh: Freshness = decays ? freshnessOf(at, now) : "quiet";
  const said = now - Date.parse(at) < 24 * 3_600_000 ? clockWords(at) : (shortAge(at, now) ?? "");
  return <span className={cn("text-xs", TONE[fresh])}>{said}</span>;
}

const TONE: Readonly<Record<Freshness, string>> = {
  fresh: "text-fg",
  quiet: "text-muted",
  stale: "text-amber-ink",
  unknown: "text-muted",
};

/**
 * How long it has stood where it stands.
 *
 * The operator's law is one hour: past that, a ticket is either moving or
 * somebody has said why it is not. So the cell turns at the hour rather than at
 * some gentler threshold — the number is the same fact either way, and the
 * colour is the law.
 */
function InStage({
  standing,
  now,
}: {
  readonly standing: Standing;
  readonly now: number;
}): ReactElement | null {
  const said = shortAge(standing.enteredStageAt, now);
  if (said === null) {
    return null;
  }
  return (
    <span
      className={cn("text-xs", overdueInStage(standing, now) ? "text-amber-ink" : "text-muted")}
    >
      {said}
    </span>
  );
}

/** How old the ticket is, in the largest unit that stays true. */
function Age({ at, now }: { readonly at: string | null; readonly now: number }): ReactElement {
  const said = shortAge(at, now);
  return <span className="text-xs text-muted">{said ?? ""}</span>;
}

/**
 * The two columns his board has and this one does not, said once, quietly,
 * under the table.
 *
 * `DESIGN.md`'s rule of 2026-08-26: a surface whose rows come from a record that
 * holds none of them draws them **absent** rather than dimmed, and collapses
 * what is missing into one muted line. Two dimmed columns of dashes down a
 * board of forty tickets would read as a broken screen; one line reads as the
 * truth, which is that the record has not been asked to carry this yet.
 */
function Missing(): ReactElement {
  return (
    <p className="mt-4 mb-0 max-w-[80ch] text-2xs text-muted">
      Two of the operator&rsquo;s columns are not drawn: which crew is on a ticket, and how fast it
      is going. A recorded run names its model but not the crew this company calls by name, and
      nothing in the record keeps a rate.
    </p>
  );
}

/* ── The columns, and how wide each one is ─────────────────────────────────── */

type Column =
  | "ticket"
  | "priority"
  | "what"
  | "crew"
  | "rate"
  | "model"
  | "status"
  | "rounds"
  | "change"
  | "raised"
  | "updated"
  | "instage"
  | "age";

/**
 * What each column is called.
 *
 * The priority column has no name on the two frames that draw only Urgent:
 * a heading over a column that is empty on every ordinary row reads as a fact
 * somebody forgot to fill in. The reference frame, which draws all three
 * priorities the way his terminal does, names it.
 */
function headOf(column: Column, draw: Draw): string {
  if (column === "priority") {
    return draw === "reference" ? "Priority" : "";
  }
  return HEAD[column];
}

const HEAD: Readonly<Record<Column, string>> = {
  ticket: "Ticket",
  priority: "",
  what: "What",
  crew: "Crew",
  rate: "Rate",
  model: "Model",
  status: "Status",
  rounds: "Rounds",
  change: "Change",
  raised: "Raised",
  updated: "Updated",
  instage: "In stage",
  age: "Age",
};

const WIDTH: Readonly<Record<Column, number | null>> = {
  ticket: 76,
  priority: 70,
  what: null,
  crew: 100,
  rate: 56,
  model: 106,
  status: 74,
  rounds: 58,
  change: 74,
  raised: 68,
  updated: 76,
  instage: 80,
  age: 46,
};

function widthOf(column: Column): { readonly width?: string } {
  const width = WIDTH[column];
  return width === null ? {} : { width: `${String(width)}px` };
}

function alignOf(column: Column): string {
  return column === "age" || column === "rate" || column === "rounds" ? "text-right" : "text-left";
}

/**
 * Which columns each frame draws.
 *
 * The shell caps a page at 1200, and his terminal's thirteen columns want half
 * again as much — so the browser has to drop, exactly as his board does on a
 * narrow window, and in his board's own order: what it was raised goes first
 * because Age says the same thing shorter, then the review rounds, then the
 * stage clock. `today` drops the two nothing can fill as well.
 */
function columnsFor(draw: Draw): readonly Column[] {
  if (draw === "reference") {
    return [
      "ticket",
      "priority",
      "what",
      "crew",
      "rate",
      "model",
      "status",
      "rounds",
      "change",
      "raised",
      "updated",
      "instage",
      "age",
    ];
  }
  if (draw === "attributed") {
    return [
      "ticket",
      "priority",
      "what",
      "crew",
      "rate",
      "model",
      "status",
      "change",
      "updated",
      "instage",
      "age",
    ];
  }
  return ["ticket", "priority", "what", "model", "status", "change", "updated", "instage", "age"];
}
