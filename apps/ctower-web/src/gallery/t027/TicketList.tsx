import { Columns3, Filter, Group, LayoutList, ListTree, Plus, SortAsc } from "lucide-react";
import type { ReactElement } from "react";
import { Button, Chip, Input, Mono } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import { cn } from "../../ui/cn";
import { Inert } from "../../projects/Inert";
import { laneWord } from "../../tickets/facts";
import { ageOf, groupOf, TICKETS } from "./fixtures";
import type { MockTicket } from "./fixtures";

/**
 * The tickets on this project, as the list you walk down.
 *
 * The reference's row is a status icon, a number, a title, who it is for and
 * how long ago. Three of those five are drawn here exactly; the other two are
 * where the record and the reference part company, and each parts on purpose.
 *
 * **The status icon is a word.** The reference draws a small circle per state.
 * ctower already spends circles: six glyphs shared with `ctowerctl`, and
 * `DESIGN.md` forbids borrowing one to mean something else. So the lane says
 * its own name, and the leading column is kept for the two marks a ticket can
 * genuinely earn — a blocker the record opened, and a person being waited on.
 *
 * **Who it is for is absent.** Every read answers with an identifier for a
 * person and nothing turns one into a name, so a face on every row would be
 * decoration over a fact this console does not have.
 */
export function TicketList({ onOpen }: { readonly onOpen: () => void }): ReactElement {
  return (
    <>
      <Toolbar onRaise={onOpen} />
      <table className="w-full border-collapse text-sm">
        <tbody>
          {TICKETS.map((ticket, index) => (
            <Rows
              key={ticket.key ?? ticket.title}
              ticket={ticket}
              first={index === 0 ? null : (TICKETS[index - 1] ?? null)}
              onOpen={onOpen}
            />
          ))}
        </tbody>
      </table>
    </>
  );
}

/** A group heading when this ticket starts one, and then the ticket's row. */
function Rows({
  ticket,
  first,
  onOpen,
}: {
  readonly ticket: MockTicket;
  /** The ticket above this one, so a group heading is drawn once. */
  readonly first: MockTicket | null;
  readonly onOpen: () => void;
}): ReactElement {
  const group = groupOf(ticket.raisedAt);
  const opens = first === null || groupOf(first.raisedAt) !== group;
  return (
    <>
      {opens ? (
        <tr>
          <th
            scope="colgroup"
            colSpan={6}
            className="pt-5 pb-1 text-left text-[10.5px] font-normal tracking-[0.1em] text-muted"
          >
            {group}
          </th>
        </tr>
      ) : null}
      <Row ticket={ticket} onOpen={onOpen} />
    </>
  );
}

function Row({
  ticket,
  onOpen,
}: {
  readonly ticket: MockTicket;
  readonly onOpen: () => void;
}): ReactElement {
  return (
    <tr className="cursor-pointer border-b border-line hover:bg-raised" onClick={onOpen}>
      <td className="w-9 py-2 align-middle whitespace-nowrap">
        {ticket.blocked === null ? null : <Mark name="parked" />}
        {ticket.waiting ? <Mark name="warn" /> : null}
      </td>
      <td className="w-9 py-2 align-middle whitespace-nowrap">
        <span
          className={cn("text-2xs", ticket.priority === "P0" ? "text-amber-ink" : "text-muted")}
        >
          {ticket.priority}
        </span>
      </td>
      <td className="w-20 py-2 align-middle whitespace-nowrap">
        <button type="button" className="cursor-pointer text-left" onClick={onOpen}>
          {/* The number a person says out loud. A ticket the record has not
              numbered yet says so rather than showing the identifier behind it. */}
          {ticket.key === null ? (
            <span className="text-2xs text-muted">Unnumbered</span>
          ) : (
            <Mono className="text-fg">{ticket.key}</Mono>
          )}
        </button>
      </td>
      <td className="py-2 pr-3 align-middle">{ticket.title}</td>
      <td className="py-2 pr-3 text-right align-middle whitespace-nowrap">
        {ticket.stage === null ? null : (
          <span className="mr-2 text-2xs text-muted">{ticket.stage}</span>
        )}
        <Chip>{laneWord(ticket.lane)}</Chip>
      </td>
      <td className="w-12 py-2 pr-1 text-right align-middle text-2xs whitespace-nowrap text-muted">
        {ageOf(ticket.raisedAt)}
      </td>
    </tr>
  );
}

/**
 * The reference's own control row: raise one, search what is here, and choose
 * how to read it. The four controls after the view toggle are the reference's
 * too, and each is drawn as what it is — the board answers a project's cards in
 * the record's own order and takes no grouping, sorting or filtering.
 */
function Toolbar({ onRaise }: { readonly onRaise: () => void }): ReactElement {
  return (
    <div className="mb-1 flex flex-wrap items-center gap-2">
      <Button variant="ghost" size="sm" onClick={onRaise}>
        <Plus /> New ticket
      </Button>
      <Input
        defaultValue=""
        placeholder="Search these tickets"
        aria-label="Search these tickets"
        className="h-7 w-56 text-xs"
      />
      <span className="flex-1" />
      <Button variant="quiet" size="sm" aria-label="List" aria-pressed className="text-fg">
        <LayoutList />
      </Button>
      <Button variant="quiet" size="sm" aria-label="Board">
        <Columns3 />
      </Button>
      <Inert className="px-1.5" reason="No read records a ticket's parent, so there is no tree.">
        <ListTree aria-hidden className="size-4" />
      </Inert>
      <Inert className="px-1.5" reason="Choosing columns is not built yet.">
        <Group aria-hidden className="size-4" />
      </Inert>
      <Inert className="px-1.5" reason="Filtering this list is not built yet.">
        <Filter aria-hidden className="size-4" />
      </Inert>
      <Inert
        className="px-1.5"
        reason="The board answers in the record's own order; re-sorting it here would overrule the record."
      >
        <SortAsc aria-hidden className="size-4" />
      </Inert>
    </div>
  );
}
