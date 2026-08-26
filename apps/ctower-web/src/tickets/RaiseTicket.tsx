import { Check, ChevronDown, X } from "lucide-react";
import { Dialog, DropdownMenu } from "radix-ui";
import type { ReactElement, ReactNode } from "react";
import type { Priority, TicketCommandResult } from "@ctower/client";
import { cn } from "../ui/cn";
import { Button, Chip } from "../ui/primitives";
import { Inert } from "../projects/Inert";
import { Sent } from "./Sent";
import { useRaise } from "./useRaise";
import { laneWord, priorityWord } from "./words";
import type { Staff, Where } from "./who";

const PRIORITIES: readonly Priority[] = ["P0", "P1", "P2"];

/**
 * Raising a ticket, as the document the operator asked for.
 *
 * Not a form: a blank page you type a heading on, one sentence underneath
 * saying who it is for, where it goes and how urgent it is, and one button.
 * The pop-up sits over the list because raising one is a moment rather than a
 * place — the same idiom the Projects screen already uses to make a project.
 *
 * Two of the reference's affordances are drawn inert, because the record has
 * nowhere to put what they would collect: the description under the title, and
 * every name in the people picker that is not the operator's own seat. An inert
 * affordance is never an input — a box that takes an answer and drops it is
 * worse than an absence.
 */
export function RaiseTicket({
  projectKey,
  staff,
  projects,
  onClose,
  onRaised,
}: {
  readonly projectKey: string;
  /** The people this company records, offered by name and drawn honestly. */
  readonly staff: readonly Staff[];
  /** The projects a ticket may be raised on, by the name a person gave them. */
  readonly projects: readonly Where[];
  readonly onClose: () => void;
  readonly onRaised: (ticketId: string) => void;
}): ReactElement {
  const raise = useRaise(projectKey);
  const here = projects.find((project) => project.key === raise.draft.project) ?? null;

  return (
    <Dialog.Root open onOpenChange={onClose}>
      <Dialog.Portal>
        {/* `--ink`, not `--fg`: the foreground inverts with the theme, so a
            scrim mixed from it washes a dark screen white. The scrim is ink in
            both themes, the way the pop-up that makes a project already is. */}
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[color-mix(in_srgb,var(--ink)_45%,transparent)]" />
        <Dialog.Content
          aria-describedby={undefined}
          className={cn(
            "fixed top-24 left-1/2 z-50 flex max-h-[80vh] w-[min(640px,92vw)] -translate-x-1/2",
            "flex-col overflow-auto rounded-md border border-line bg-card"
          )}
        >
          <header className="flex items-center gap-2 px-5 py-3.5 text-2xs text-muted">
            {here?.prefix === undefined || here.prefix === null ? null : <Chip>{here.prefix}</Chip>}
            <Dialog.Title className="m-0 text-2xs font-normal text-fg">New ticket</Dialog.Title>
            <span className="flex-1" />
            <Dialog.Close asChild>
              <Button variant="quiet" size="sm" aria-label="Close">
                <X />
              </Button>
            </Dialog.Close>
          </header>

          <div className="px-6 pb-6">
            <input
              autoFocus
              value={raise.draft.title}
              maxLength={200}
              placeholder="What needs doing?"
              aria-label="Ticket title"
              onChange={(event): void => {
                raise.setDraft({ ...raise.draft, title: event.target.value });
              }}
              className={cn(
                "w-full border-0 bg-transparent p-0 text-xl font-bold tracking-[-0.02em]",
                "text-fg outline-none placeholder:text-muted/70"
              )}
            />
            <Inert
              className="mt-2.5 block text-md"
              reason="A raised ticket carries a title and nothing longer. Say more about it in a note once it exists."
            >
              Say more about it…
            </Inert>

            <p className="mt-7 mb-0 flex flex-wrap items-center gap-2 text-sm text-muted">
              <span>For</span>
              <WhoPicker staff={staff} />
              <span>in</span>
              <WherePicker
                projects={projects}
                chosen={raise.draft.project}
                onChoose={(project): void => {
                  raise.setDraft({ ...raise.draft, project });
                }}
              />
              <span>and it is</span>
              <Picker what="How urgent" label={priorityWord(raise.draft.priority)}>
                {PRIORITIES.map((priority) => (
                  <Row
                    key={priority}
                    chosen={priority === raise.draft.priority}
                    onChoose={(): void => {
                      raise.setDraft({ ...raise.draft, priority });
                    }}
                  >
                    {priorityWord(priority)}
                  </Row>
                ))}
              </Picker>
            </p>

            {raise.sent === null ? null : (
              <Sent
                sent={raise.sent}
                doing="Raising this ticket"
                nothingHappened="No ticket was raised."
                onRetry={raise.retry}
                receipt={
                  raise.sent.kind === "answered" ? (
                    <Raised receipt={raise.sent.value} onOpen={onRaised} />
                  ) : null
                }
              />
            )}
          </div>

          <footer className="flex flex-wrap items-center gap-2 border-t border-line px-6 py-3.5">
            {/* Where it lands is the record's answer, not a question: a new
                ticket enters the first lane and nothing on this screen chooses
                that. */}
            <Inert className="chip" reason="Every new ticket starts here. Nothing chooses it.">
              Starts in {laneWord("backlog")}
            </Inert>
            <span className="flex-1" />
            <Button variant="quiet" size="sm" onClick={onClose}>
              Discard
            </Button>
            <Button variant="primary" disabled={!raise.armed} onClick={raise.send}>
              Raise it
            </Button>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/**
 * Who takes the ticket.
 *
 * One row is live and it is not a shortcut: leaving the person off the command
 * is what makes the record hand the ticket to the seat this console acts as, so
 * "Me" is the record's own answer. Every other name the company records is here
 * and is dimmed, because a ticket is handed to a principal the record names by
 * identifier and no declared read turns one of these names into one.
 */
function WhoPicker({ staff }: { readonly staff: readonly Staff[] }): ReactElement {
  return (
    <Picker what="Who takes it" label="Me">
      <Row chosen onChoose={(): void => undefined}>
        Me
      </Row>
      {staff.map((person) => (
        <DropdownMenu.Item
          key={person.key}
          disabled
          className="flex items-center gap-2.5 rounded-sm px-3 py-1.5 text-muted outline-none"
        >
          <span className="min-w-0 flex-1 truncate text-sm">{person.name}</span>
          <span className="shrink-0 text-2xs">cannot take one yet</span>
        </DropdownMenu.Item>
      ))}
    </Picker>
  );
}

/** Which project it is raised on — the switcher's own answer, changeable here. */
function WherePicker({
  projects,
  chosen,
  onChoose,
}: {
  readonly projects: readonly Where[];
  readonly chosen: string;
  readonly onChoose: (project: string) => void;
}): ReactElement {
  const here = projects.find((project) => project.key === chosen);
  return (
    <Picker what="Which project" label={here?.name ?? "this project"}>
      {projects.map((project) => (
        <Row
          key={project.key}
          chosen={project.key === chosen}
          prefix={project.prefix}
          onChoose={(): void => {
            onChoose(project.key);
          }}
        >
          {project.name}
        </Row>
      ))}
    </Picker>
  );
}

/**
 * The reference's picker: a word with a chevron, opening a list of real rows.
 *
 * The word it is showing is the answer, so it is what the button says. What the
 * word is an answer *to* is only knowable from the sentence around it, which a
 * screen reader reaching the button out of order does not have — so the
 * accessible name carries both, and the visible label stays one word.
 */
function Picker({
  what,
  label,
  children,
}: {
  /** The question this picker answers, for anyone who meets the control alone. */
  readonly what: string;
  readonly label: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label={`${what}: ${label}`}
          className={cn(
            "inline-flex cursor-pointer items-center gap-1.5 rounded-full bg-raised",
            "px-3 py-1 text-sm font-medium text-fg hover:bg-line"
          )}
        >
          {label}
          <ChevronDown aria-hidden className="size-3.5 shrink-0 text-muted" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={4}
          className="z-50 max-h-72 w-[260px] overflow-auto rounded-md border border-line bg-card p-1"
        >
          {children}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function Row({
  chosen = false,
  prefix = null,
  onChoose,
  children,
}: {
  readonly chosen?: boolean;
  readonly prefix?: string | null;
  /** Choosing the row that is already chosen is a no-op, and still closes the menu. */
  readonly onChoose: () => void;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <DropdownMenu.Item
      onSelect={onChoose}
      className="flex cursor-pointer items-center gap-2.5 rounded-sm px-3 py-1.5 outline-none data-[highlighted]:bg-raised"
    >
      {prefix === null ? null : <Chip className="shrink-0">{prefix}</Chip>}
      <span className="min-w-0 flex-1 truncate text-sm text-fg">{children}</span>
      {chosen ? <Check aria-hidden className="size-3.5 shrink-0 text-ok" /> : null}
    </DropdownMenu.Item>
  );
}

/**
 * What the record answered. A ticket it took but has not confirmed durable is
 * not a raised ticket, and this says so rather than drawing acceptance.
 */
function Raised({
  receipt,
  onOpen,
}: {
  readonly receipt: TicketCommandResult;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  const accepted = receipt.durability_state === "accepted";
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 rounded-md border border-line bg-raised p-3">
      <span className="text-sm font-medium">
        {accepted ? "Raised" : "Sent, and not confirmed yet"}
      </span>
      <span className="text-xs text-muted">
        {receipt.ticket.display_key ?? "It has no number yet."}
      </span>
      <span className="flex-1" />
      <Button
        size="sm"
        onClick={(): void => {
          onOpen(receipt.ticket.ticket_id);
        }}
      >
        Open it
      </Button>
    </div>
  );
}
