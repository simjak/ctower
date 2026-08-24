import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import type { BoardCard, CompanyBundleDocument } from "@ctower/client";
import type { Answer } from "../api/client";
import { Hint } from "../ui/form";
import { Button, Card, CardBody, Mono, PageHead } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { usePlace } from "./address";
import type { Place } from "./address";
import { NewTicket } from "./NewTicket";
import { ProjectChoice } from "./ProjectChoice";
import { useBoard, useTicket } from "./reads";
import { Standing } from "./Standing";
import { TicketDetail } from "./TicketDetail";
import { TicketTable } from "./TicketTable";
import { workProjectsIn } from "./projects";
import { ProjectHome } from "../projects/ProjectHome";
import { projectsIn } from "../projects/read";

/**
 * An empty board and an unknown project are the same answer.
 *
 * `getBoard` returns 200 with no cards for a project key the work plane never
 * heard of, exactly as it does for one that simply has no ticket, and no
 * declared operation tells the two apart. So this page never reports one as
 * the other, and it never offers a write into an address it cannot show exists.
 */
const NO_CARDS =
  "The board answers 200 with no cards for a project the work plane does not know, exactly as it does for one that has no ticket raised on it. No declared read tells the two apart.";

/**
 * The Tickets page: the list, one ticket, and raising one.
 *
 * Where the operator is lives in the address, so every screen here is a link
 * and the browser's own Back button works. The list read is held at this level
 * because the ticket page borrows the card the board folded — that is where a
 * ticket's lane, labels and blocker are recorded, and reading it twice would
 * let the two screens disagree.
 */
export function TicketsPage({
  document,
  onGoBoard,
}: {
  readonly document: CompanyBundleDocument;
  /** The board is a destination of its own; this screen points at it. */
  readonly onGoBoard: () => void;
}): ReactElement {
  const [place, go] = usePlace();
  const [reloadKey, setReloadKey] = useState(0);
  const board = useBoard(place.project, reloadKey);
  const scopes = workProjectsIn(document);
  const reread = useCallback((): void => {
    setReloadKey((count) => count + 1);
  }, []);

  if (place.project === null) {
    return (
      <ProjectChoice
        projects={scopes}
        onChoose={(project): void => {
          go({ project, ticket: null, raising: false });
        }}
      />
    );
  }

  const cards = board.kind === "answered" ? board.value.cards : [];
  // A ticket on the board, or a component scoped to this key, is a recorded
  // fact that the project exists. Neither is an answer's absence of cards.
  const exists = cards.length > 0 || scopes.includes(place.project);

  if (place.raising) {
    return (
      <NewTicket
        projectKey={place.project}
        custodians={custodiansIn(cards)}
        onBack={(): void => {
          go({ ...place, raising: false });
          reread();
        }}
        onRaised={(ticket): void => {
          go({ project: place.project, ticket, raising: false });
          reread();
        }}
      />
    );
  }

  if (place.ticket !== null) {
    return (
      <OneTicketScreen
        place={place}
        projectKey={place.project}
        card={cards.find((card) => card.ticket_id === place.ticket) ?? null}
        onBack={(): void => {
          go({ project: place.project, ticket: null, raising: false });
        }}
        onMoved={reread}
      />
    );
  }

  // One tickets surface in the product. The rail's Tickets opens the project's
  // own screen on its Tasks tab; the tab bar there is that screen's local
  // navigation, not a second way to reach this read. A key the company records
  // no project document for cannot open that screen — it has no name, no prefix
  // and no repository — so it keeps the plain list, which is also the only place
  // that can tell an empty project from a project nothing here records.
  const project = projectsIn(document).find((held) => held.key === place.project);
  if (project !== undefined) {
    return (
      <ProjectHome
        project={project}
        onBack={(): void => {
          go({ project: null, ticket: null, raising: false });
        }}
        onOpenTicket={(ticket): void => {
          go({ project: place.project, ticket, raising: false });
        }}
        onRaiseTicket={(): void => {
          go({ ...place, raising: true });
        }}
        onBoard={onGoBoard}
      />
    );
  }

  return (
    <>
      <PageHead
        title="Tickets"
        subtitle={
          <>
            <Mono>{place.project}</Mono>
            {board.kind === "answered" ? (
              <>
                <span>
                  {cards.length} {cards.length === 1 ? "ticket" : "tickets"}
                </span>
                <Standing board={board.value} />
              </>
            ) : null}
          </>
        }
      >
        {/* A board that would not answer is not a board a ticket can be raised
            on, and an action that can only refuse is worse than no action.
            Neither is a project nothing here records: raising a ticket into an
            address this console cannot show exists is a write on a guess. */}
        {board.kind === "answered" && exists ? (
          <Button
            variant="primary"
            onClick={(): void => {
              go({ ...place, raising: true });
            }}
          >
            New ticket
          </Button>
        ) : null}
      </PageHead>
      <List
        board={board}
        cards={cards}
        projectKey={place.project}
        recorded={scopes.includes(place.project)}
        onOpen={(ticket): void => {
          go({ project: place.project, ticket, raising: false });
        }}
        onChoose={(): void => {
          go({ project: null, ticket: null, raising: false });
        }}
      />
    </>
  );
}

function List({
  board,
  cards,
  projectKey,
  recorded,
  onOpen,
  onChoose,
}: {
  readonly board: Answer<unknown>;
  readonly cards: readonly BoardCard[];
  readonly projectKey: string;
  /** Whether a component in this company declares itself scoped to this key. */
  readonly recorded: boolean;
  readonly onOpen: (ticketId: string) => void;
  readonly onChoose: () => void;
}): ReactElement {
  switch (board.kind) {
    case "asking":
      return <Asking what="Reading this project's tickets" />;
    case "refused":
      return <Refused problem={board.problem} action="Nothing was read. Reload to ask again." />;
    case "unreachable":
      return (
        <Unreachable
          detail={board.detail}
          action="This is not an empty project; it is a project that was not read. Reload to ask again."
        />
      );
    case "malformed":
      return <Malformed detail={board.detail} />;
    case "answered":
      return cards.length === 0 ? (
        <Empty projectKey={projectKey} recorded={recorded} onChoose={onChoose} />
      ) : (
        <TicketTable cards={cards} onOpen={onOpen} />
      );
  }
}

/**
 * A board that answered with nothing, said as the two different facts it can
 * be. A key this company records is a project with no ticket yet; a key nothing
 * here records is a project this console cannot show exists at all, and the
 * only honest next move is to choose one it can.
 */
function Empty({
  projectKey,
  recorded,
  onChoose,
}: {
  readonly projectKey: string;
  readonly recorded: boolean;
  readonly onChoose: () => void;
}): ReactElement {
  return (
    <Card>
      <CardBody>
        {recorded ? (
          <p className="m-0 flex items-center gap-1.5 text-sm text-muted">
            No ticket has been raised on this project yet.
            <Hint text={NO_CARDS} />
          </p>
        ) : (
          <>
            <p className="m-0 flex items-center gap-1.5 text-sm text-fg">
              <span>
                This board answered with no ticket, and nothing in this company is scoped to{" "}
                <Mono>{projectKey}</Mono>.
              </span>
              <Hint text={NO_CARDS} />
            </p>
            <Button className="mt-3" onClick={onChoose}>
              Choose a project
            </Button>
          </>
        )}
      </CardBody>
    </Card>
  );
}

function OneTicketScreen({
  place,
  projectKey,
  card,
  onBack,
  onMoved,
}: {
  readonly place: Place;
  readonly projectKey: string;
  readonly card: BoardCard | null;
  readonly onBack: () => void;
  readonly onMoved: () => void;
}): ReactElement {
  const [reloadKey, setReloadKey] = useState(0);
  const one = useTicket(projectKey, place.ticket ?? "", reloadKey);
  const moved = (): void => {
    setReloadKey((count) => count + 1);
    onMoved();
  };

  switch (one.kind) {
    case "asking":
      return <Asking what="Reading this ticket" />;
    case "refused":
      return <Refused problem={one.problem} action="Nothing was read. Go back to the list." />;
    case "unreachable":
      return <Unreachable detail={one.detail} action="Reload to ask again." />;
    case "malformed":
      return <Malformed detail={one.detail} />;
    case "answered":
      return (
        <TicketDetail
          one={one.value}
          card={card}
          project={projectKey}
          onBack={onBack}
          onMoved={moved}
        />
      );
  }
}

/** The custodians this board has actually recorded, offered when raising one. */
function custodiansIn(cards: readonly BoardCard[]): readonly string[] {
  return [...new Set(cards.map((card) => card.custodian_id))].sort((left, right) =>
    left.localeCompare(right)
  );
}
