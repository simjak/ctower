import { useCallback, useState } from "react";
import { Columns3, LayoutList, Plus } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import type { BoardCard, CompanyBundleDocument } from "@ctower/client";
import { Button, Input } from "../ui/primitives";
import { cn } from "../ui/cn";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { RaiseTicket } from "./RaiseTicket";
import { useRaisings } from "./raised";
import { useBoard } from "./reads";
import { TicketBoard } from "./TicketBoard";
import { TicketList } from "./TicketList";
import { staffIn, whereIn } from "./who";

/**
 * A project's tickets, read once and drawn two ways.
 *
 * The list and the columns are one `getBoard` answer, so the two cannot
 * disagree about what is on this project — which is why the toggle sits beside
 * them rather than being a destination that asks again. Which of the two is
 * showing is a place inside this screen and not a screen of its own, so it
 * stays out of the address, the same rule the project tabs above it follow.
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
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  const [typed, setTyped] = useState("");
  const [columns, setColumns] = useState(false);
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
        <div className="flex items-center gap-0.5 rounded-md bg-raised p-0.5">
          <View
            here={!columns}
            label="List"
            onChoose={(): void => {
              setColumns(false);
            }}
          >
            <LayoutList />
          </View>
          <View
            here={columns}
            label="Board"
            onChoose={(): void => {
              setColumns(true);
            }}
          >
            <Columns3 />
          </View>
        </div>
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
          columns={columns}
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

function Answered({
  cards,
  total,
  searching,
  columns,
  raisings,
  now,
  empty,
  onOpen,
}: {
  readonly cards: readonly BoardCard[];
  readonly total: number;
  readonly searching: boolean;
  readonly columns: boolean;
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
  return columns ? (
    <TicketBoard cards={cards} onOpen={onOpen} />
  ) : (
    <TicketList cards={cards} raisings={raisings} now={now} onOpen={onOpen} />
  );
}

function View({
  here,
  label,
  onChoose,
  children,
}: {
  readonly here: boolean;
  readonly label: string;
  readonly onChoose: () => void;
  readonly children: ReactElement;
}): ReactElement {
  return (
    <Button
      variant="quiet"
      size="sm"
      aria-label={label}
      aria-pressed={here}
      onClick={onChoose}
      className={cn(here && "bg-card text-fg")}
    >
      {children}
    </Button>
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
