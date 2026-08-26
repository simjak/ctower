import { useCallback, useState } from "react";
import { Plus } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import type { BoardCard, BoardView, CompanyBundleDocument } from "@ctower/client";
import { Button, Chip, Input } from "../ui/primitives";
import { projectsIn } from "../projects/read";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { RaiseTicket } from "./RaiseTicket";
import { useRaisings } from "./raised";
import { useBoard } from "./reads";
import { catchingUpWords, standingWords } from "./standing";
import { TicketBoard } from "./TicketBoard";
import { TicketList } from "./TicketList";
import { ViewToggle } from "./ViewToggle";
import type { TicketShape } from "./ViewToggle";
import { staffIn, whereIn } from "./who";

/**
 * A project's tickets, read once and drawn two ways.
 *
 * The list and the columns are one `getBoard` answer — the same feed
 * `ctowerctl board query` serves — so the two shapes cannot disagree about what
 * is on this project, and the toggle between them is a switch rather than a
 * second read. Which shape is showing is the rail's own question, because the
 * rail carries a row for each: the caller says which, and moving between them
 * moves the address and the rail together.
 *
 * The search narrows what already arrived. The authored contract declares no
 * ticket search, so filtering here never pretends to have asked ctower a
 * question it has no operation for, and it never reorders: the projection
 * serves its cards in the record's own position.
 */
export function TicketsView({
  projectKey,
  document,
  recorded,
  shape,
  onShape,
  onOpen,
}: {
  readonly projectKey: string;
  /** The company record the people and project pickers are drawn from. */
  readonly document: CompanyBundleDocument;
  /**
   * Whether this company records anything scoped to this project.
   *
   * `getBoard` answers 200 with no cards for a key the work plane never heard
   * of, exactly as it does for a project that simply has no ticket, and no
   * declared operation tells the two apart. So a key nothing here records gets
   * no way to raise one: a write into an address this console cannot show
   * exists is a write on a guess.
   */
  readonly recorded: boolean;
  /** Which of the two shapes this mount draws; the rail says which it is. */
  readonly shape: TicketShape;
  readonly onShape: (shape: TicketShape) => void;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  const [typed, setTyped] = useState("");
  const [raising, setRaising] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const board = useBoard(projectKey, reloadKey);
  const raisings = useRaisings(projectKey, reloadKey);
  const reread = useCallback((): void => {
    setReloadKey((count) => count + 1);
  }, []);

  const cards = board.kind === "answered" ? board.value.cards : [];
  const kept = matching(cards, typed);
  // One instant for the whole render, so two rows raised a second apart never
  // read as though they were raised in different bands.
  const now = Date.now();

  return (
    <>
      {shape === "board" ? (
        <Whose projectKey={projectKey} document={document} board={board} />
      ) : null}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {recorded ? (
          <Button
            variant="primary"
            onClick={(): void => {
              setRaising(true);
            }}
          >
            <Plus /> New ticket
          </Button>
        ) : null}
        <Input
          value={typed}
          placeholder="Search these tickets"
          aria-label="Search these tickets"
          className="w-64"
          onChange={(event): void => {
            setTyped(event.target.value);
          }}
        />
        <span className="flex-1" />
        <ViewToggle shape={shape} onShape={onShape} />
      </div>

      {board.kind === "asking" ? <Asking what="Reading this project's tickets" /> : null}
      {board.kind === "refused" ? (
        <Refused problem={board.problem} action="No ticket was read. Reload to ask again." />
      ) : null}
      {board.kind === "unreachable" ? (
        <Unreachable
          detail={board.detail}
          action="This is not an empty project; it is a project that was not read. Reload to ask again."
        />
      ) : null}
      {board.kind === "malformed" ? <Malformed detail={board.detail} /> : null}
      {board.kind === "answered" ? (
        <Answered
          cards={kept}
          total={cards.length}
          searching={typed.trim() !== ""}
          shape={shape}
          raisings={raisings}
          now={now}
          empty={
            recorded ? (
              "No ticket has been raised here yet."
            ) : (
              <>
                This board answered with no ticket, and nothing in this company is scoped to{" "}
                {projectKey}. No declared read tells an unknown project from an empty one, so this
                screen offers no way to raise one here.
              </>
            )
          }
          onOpen={onOpen}
        />
      ) : null}

      {raising ? (
        <RaiseTicket
          projectKey={projectKey}
          staff={staffIn(document)}
          projects={whereIn(document, projectKey)}
          onClose={(): void => {
            setRaising(false);
            reread();
          }}
          onRaised={(ticket): void => {
            setRaising(false);
            reread();
            onOpen(ticket);
          }}
        />
      ) : null}
    </>
  );
}

/**
 * Whose board this is, and how it stands.
 *
 * Only the columns draw it. The Board is a destination of its own, so it has to
 * say which project it is about; the list is a tab inside that project's own
 * screen, which has already said so above it, and a second title there would be
 * the console answering one question twice.
 */
function Whose({
  projectKey,
  document,
  board,
}: {
  readonly projectKey: string;
  readonly document: CompanyBundleDocument;
  readonly board: ReturnType<typeof useBoard>;
}): ReactElement {
  const facts = projectsIn(document).find((held) => held.key === projectKey);
  const view: BoardView | null = board.kind === "answered" ? board.value : null;
  const behind = view === null ? null : catchingUpWords(view);
  return (
    <header className="mb-4 flex flex-wrap items-center gap-3">
      <h1 className="m-0 min-w-0 truncate text-xl leading-tight font-bold tracking-[-0.02em]">
        {facts?.name ?? projectKey}
      </h1>
      {facts?.prefix === undefined || facts.prefix === null ? null : <Chip>{facts.prefix}</Chip>}
      {view === null ? null : (
        <span className="text-sm text-muted">{standingWords(view.cards)}</span>
      )}
      {behind === null ? null : <span className="text-sm text-muted">{behind}</span>}
    </header>
  );
}

function Answered({
  cards,
  total,
  searching,
  shape,
  raisings,
  now,
  empty,
  onOpen,
}: {
  readonly cards: readonly BoardCard[];
  readonly total: number;
  readonly searching: boolean;
  readonly shape: TicketShape;
  readonly raisings: ReturnType<typeof useRaisings>;
  readonly now: number;
  /** What a board with no card is, which is two different facts. */
  readonly empty: ReactNode;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  // An empty project and a search that keeps nothing are different facts, and
  // are never drawn as one.
  if (total === 0) {
    return <p className="m-0 max-w-[60ch] py-6 text-sm text-muted">{empty}</p>;
  }
  if (cards.length === 0 && searching) {
    return <p className="m-0 py-6 text-sm text-muted">No ticket here matches that.</p>;
  }
  return shape === "board" ? (
    <TicketBoard cards={cards} onOpen={onOpen} />
  ) : (
    <TicketList cards={cards} raisings={raisings} now={now} onOpen={onOpen} />
  );
}

/** The cards whose number or title carry what was typed, in the board's order. */
function matching(cards: readonly BoardCard[], typed: string): readonly BoardCard[] {
  const wanted = typed.trim().toLowerCase();
  if (wanted === "") {
    return cards;
  }
  return cards.filter(
    (card) =>
      card.title.toLowerCase().includes(wanted) ||
      (card.display_key ?? "").toLowerCase().includes(wanted)
  );
}
