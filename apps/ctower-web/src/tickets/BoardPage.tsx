import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { Button } from "../ui/primitives";
import type { DestinationKey } from "../shell/destinations";
import { workProjectsIn } from "./projects";
import { TicketsView } from "./TicketsView";

/**
 * The Board: this project's tickets, read as columns.
 *
 * It is the same screen as the list and not a second one. `TicketsView` holds
 * the read, the search, the one primary act and the toggle, and this
 * destination is that view asked for its other shape — so the columns and the
 * list cannot drift into two consoles, and the operator's toggle between them
 * moves the rail rather than hiding a shape inside a screen the rail says is
 * something else.
 *
 * Read-only. Every column and every card fact comes from `getBoard`, the feed
 * `ctowerctl board query` serves; nothing on this screen moves a ticket. Where
 * a ticket goes next is its own page, which is where the record explains what
 * a move means before one is made, and a card is the way there.
 *
 * Which project it shows is not this screen's question: the rail's switcher
 * governs the project workspace and the address carries the answer, so the
 * board is handed one project and shows it.
 */
export function BoardPage({
  projectKey,
  document,
  onGo,
}: {
  /** The project the rail is pointed at; null only when the company has none. */
  readonly projectKey: string | null;
  /** The company record the raise pop-up draws its people and projects from. */
  readonly document: CompanyBundleDocument;
  readonly onGo: (key: DestinationKey, place?: Readonly<Record<string, string>>) => void;
}): ReactElement {
  if (projectKey === null) {
    return <Unopened onGo={onGo} />;
  }
  return (
    <TicketsView
      projectKey={projectKey}
      document={document}
      recorded={workProjectsIn(document).includes(projectKey)}
      shape="board"
      onShape={(shape): void => {
        if (shape === "list") {
          onGo("tickets");
        }
      }}
      onOpen={(ticket): void => {
        onGo("tickets", { ticket });
      }}
    />
  );
}

/**
 * No project in the rail, so no board to read. This company records none yet,
 * and the one act that fixes it sits next to the sentence that says so.
 */
function Unopened({ onGo }: { readonly onGo: (key: DestinationKey) => void }): ReactElement {
  return (
    <div className="py-6">
      <h1 className="m-0 text-xl leading-tight font-bold tracking-[-0.02em]">Board</h1>
      <p className="mt-2 mb-0 text-sm text-muted">
        This company has no project yet, so there is no board to read.
      </p>
      <Button
        variant="primary"
        className="mt-3"
        onClick={(): void => {
          onGo("projects");
        }}
      >
        Open Projects
      </Button>
    </div>
  );
}
