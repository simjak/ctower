import { useState } from "react";
import { Folder } from "lucide-react";
import type { ReactElement } from "react";
import { cn } from "../../ui/cn";
import { Chip } from "../../ui/primitives";
import { HERE } from "./fixtures";
import { Frame } from "./Frame";
import { BoardScreen } from "./BoardScreen";
import { RaiseTicket } from "./RaiseTicket";
import { TicketHome } from "./TicketHome";
import { TicketList } from "./TicketList";

/**
 * The four screens T-027 puts on the bench, each reachable on its own address
 * so it can be screenshotted alone: `gallery.html?screen=list`, `…=raise`,
 * `…=board`, `…=ticket`. Nothing is wired; every screen draws fixtures.
 */
export type ScreenKey = "list" | "raise" | "raise-who" | "board" | "ticket";

export function screenFromSearch(search: string): ScreenKey {
  const asked = new URLSearchParams(search).get("screen");
  return SCREENS.includes(asked as ScreenKey) ? (asked as ScreenKey) : "list";
}

const SCREENS: readonly ScreenKey[] = ["list", "raise", "raise-who", "board", "ticket"];

export function Screen({ which }: { readonly which: ScreenKey }): ReactElement {
  const [here, setHere] = useState<ScreenKey>(which);

  if (here === "ticket") {
    return (
      <Frame here="tickets">
        <TicketHome
          onBack={(): void => {
            setHere("list");
          }}
        />
      </Frame>
    );
  }

  const raising = here === "raise" || here === "raise-who";
  return (
    <Frame here="tickets">
      <ProjectHead />
      {here === "board" ? (
        <BoardScreen
          onOpen={(): void => {
            setHere("raise");
          }}
        />
      ) : (
        <TicketList
          onOpen={(): void => {
            setHere("ticket");
          }}
        />
      )}
      {raising ? (
        <RaiseTicket
          openMenu={here === "raise-who" ? "who" : null}
          typed={here === "raise" ? "Morning digest lands before the first stand-up" : ""}
          onClose={(): void => {
            setHere("list");
          }}
        />
      ) : null}
    </Frame>
  );
}

/**
 * The project's own head, and the one word that changed.
 *
 * The tab said `Tasks` when this screen landed. T-027 fixes the product on one
 * noun — a ticket — so the tab, the button and the page all say the same thing
 * a person says out loud when they raise one.
 */
function ProjectHead(): ReactElement {
  return (
    <>
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <Folder aria-hidden className="size-5 shrink-0 text-muted" />
        <h1 className="m-0 min-w-0 flex-1 truncate text-xl leading-tight font-bold tracking-[-0.02em]">
          {HERE.name}
        </h1>
        <Chip>{HERE.prefix}</Chip>
      </header>
      <div role="tablist" aria-label="Project" className="mb-3 flex gap-1 border-b border-line">
        {TABS.map((tab, index) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={index === 0}
            className={cn(
              "-mb-px cursor-pointer border-b-2 px-3 py-2 text-sm",
              index === 0
                ? "border-amber font-semibold text-fg"
                : "border-transparent text-muted hover:bg-raised hover:text-fg"
            )}
          >
            {tab}
          </button>
        ))}
      </div>
    </>
  );
}

const TABS: readonly string[] = ["Tickets", "Overview", "Configuration", "Budget"];
