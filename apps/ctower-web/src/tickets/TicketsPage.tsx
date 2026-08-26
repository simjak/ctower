import { useState } from "react";
import type { ReactElement } from "react";
import type { BoardCard, CompanyBundleDocument } from "@ctower/client";
import { PageHead } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import type { DestinationKey } from "../shell/destinations";
import { usePlace } from "./address";
import { ProjectChoice } from "./ProjectChoice";
import { useBoard, useTicket } from "./reads";
import { TicketHome } from "./home/TicketHome";
import { TicketsView } from "./TicketsView";
import { workProjectsIn } from "./projects";
import { ProjectHome } from "../projects/ProjectHome";
import { projectsIn } from "../projects/read";

/**
 * The Tickets destination: the project's tickets, and one ticket.
 *
 * Where the operator is lives in the address, so every screen here is a link
 * and the browser's own Back button works. Raising one is deliberately *not* in
 * the address: it is a pop-up over the list, a moment rather than a place, the
 * same idiom the Projects screen uses to make a project.
 *
 * A ticket's own page borrows the card the board folded — that is where a
 * ticket's lane, blocker, changes and delivery are recorded — so the list read
 * is held here and handed down, rather than being made twice and letting the
 * two screens disagree.
 */
export function TicketsPage({
  document,
  onGo,
}: {
  readonly document: CompanyBundleDocument;
  /**
   * Where the shell goes when this screen names another destination. The
   * columns are one — `Board` is a rail row, so asking for that shape is asking
   * to be somewhere else, and only the shell can move the rail with it.
   */
  readonly onGo: (key: DestinationKey, place?: Readonly<Record<string, string>>) => void;
}): ReactElement {
  const [place, go] = usePlace();
  const scopes = workProjectsIn(document);
  // The columns are the Board destination on *this* screen's project, which is
  // not always the switcher's: the chooser here offers the keys the switcher
  // cannot, so the project travels with the request rather than being inherited.
  const showColumns = (): void => {
    onGo("board", place.project === null ? {} : { project: place.project });
  };

  if (place.project === null) {
    return (
      <ProjectChoice
        projects={scopes}
        onChoose={(project): void => {
          go({ project, ticket: null });
        }}
      />
    );
  }

  if (place.ticket !== null) {
    return (
      <OneTicket
        projectKey={place.project}
        ticketId={place.ticket}
        document={document}
        onBack={(): void => {
          go({ project: place.project, ticket: null });
        }}
      />
    );
  }

  // One tickets surface in the product. The rail's Tickets opens the project's
  // own screen on its Tickets tab; the tab bar there is that screen's local
  // navigation, not a second way to reach this read. A key the company records
  // no project document for cannot open that screen — it has no name and no
  // prefix — so it keeps the plain list, which is also the only place that can
  // tell an empty project from a project nothing here records.
  const project = projectsIn(document).find((held) => held.key === place.project);
  if (project !== undefined) {
    return (
      <ProjectHome
        project={project}
        document={document}
        onBack={(): void => {
          go({ project: null, ticket: null });
        }}
        onShowColumns={showColumns}
        onOpenTicket={(ticket): void => {
          go({ project: place.project, ticket });
        }}
      />
    );
  }

  return (
    <>
      <PageHead title="Tickets" subtitle="A project this company records no document for." />
      <TicketsView
        projectKey={place.project}
        document={document}
        recorded={scopes.includes(place.project)}
        shape="list"
        onShape={showColumns}
        onOpen={(ticket): void => {
          go({ project: place.project, ticket });
        }}
      />
    </>
  );
}

/**
 * One ticket, and the two reads it stands on.
 *
 * The board is asked again here rather than threaded down from the list,
 * because a ticket reached by its own address was never in a list this session
 * — a reload, or a link somebody was sent, opens straight onto this page.
 */
function OneTicket({
  projectKey,
  ticketId,
  document,
  onBack,
}: {
  readonly projectKey: string;
  readonly ticketId: string;
  readonly document: CompanyBundleDocument;
  readonly onBack: () => void;
}): ReactElement {
  const [reloadKey, setReloadKey] = useState(0);
  const one = useTicket(projectKey, ticketId, reloadKey);
  const board = useBoard(projectKey, reloadKey);
  const card = cardIn(board.kind === "answered" ? board.value.cards : [], ticketId);

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
        <TicketHome
          one={one.value}
          card={card}
          project={projectKey}
          document={document}
          onBack={onBack}
          onMoved={(): void => {
            setReloadKey((count) => count + 1);
          }}
        />
      );
  }
}

function cardIn(cards: readonly BoardCard[], ticketId: string): BoardCard | null {
  return cards.find((card) => card.ticket_id === ticketId) ?? null;
}
