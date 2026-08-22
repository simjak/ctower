import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import type { BoardCard, CompanyBundleDocument } from "@ctower/client";
import type { Answer } from "../api/client";
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
}: {
  readonly document: CompanyBundleDocument;
}): ReactElement {
  const [place, go] = usePlace();
  const [reloadKey, setReloadKey] = useState(0);
  const board = useBoard(place.project, reloadKey);
  const reread = useCallback((): void => {
    setReloadKey((count) => count + 1);
  }, []);

  if (place.project === null) {
    return (
      <ProjectChoice
        projects={workProjectsIn(document)}
        onChoose={(project): void => {
          go({ project, ticket: null, raising: false });
        }}
      />
    );
  }

  const cards = board.kind === "answered" ? board.value.cards : [];

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
            on, and an action that can only refuse is worse than no action. */}
        {board.kind === "answered" ? (
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
        onOpen={(ticket): void => {
          go({ project: place.project, ticket, raising: false });
        }}
      />
    </>
  );
}

function List({
  board,
  cards,
  onOpen,
}: {
  readonly board: Answer<unknown>;
  readonly cards: readonly BoardCard[];
  readonly onOpen: (ticketId: string) => void;
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
      return cards.length === 0 ? <Empty /> : <TicketTable cards={cards} onOpen={onOpen} />;
  }
}

function Empty(): ReactElement {
  return (
    <Card>
      <CardBody>
        <p className="m-0 text-sm text-muted">No ticket has been raised on this project yet.</p>
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
      return <TicketDetail one={one.value} card={card} onBack={onBack} onMoved={moved} />;
  }
}

/** The custodians this board has actually recorded, offered when raising one. */
function custodiansIn(cards: readonly BoardCard[]): readonly string[] {
  return [...new Set(cards.map((card) => card.custodian_id))].sort((left, right) =>
    left.localeCompare(right)
  );
}
