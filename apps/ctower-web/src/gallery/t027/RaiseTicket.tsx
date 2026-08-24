import { useState } from "react";
import { Check, ChevronDown, Maximize2, X } from "lucide-react";
import { Dialog, DropdownMenu } from "radix-ui";
import type { ReactElement, ReactNode } from "react";
import { cn } from "../../ui/cn";
import { Button, Input } from "../../ui/primitives";
import { Inert } from "../../projects/Inert";
import { HERE, PROJECTS, STAFF } from "./fixtures";

/**
 * Raising a ticket, in the document the operator asked for.
 *
 * Not a form: a blank page with a heading you type, one sentence of who and
 * where under it, and one button. Everything the record needs and a person
 * would not type is derived — the project comes from the switcher he is
 * already standing in, the person who takes it is the seat this console acts
 * as, and where it lands is the record's own answer rather than a question.
 *
 * Two of the reference's affordances are drawn inert, because the record has
 * nowhere to put what they would collect: the description under the title, and
 * every name in the assignee picker that is not the operator's own seat.
 */
export function RaiseTicket({
  openMenu = null,
  typed = "",
  onClose,
}: {
  /** Which picker is open, so the bench can screenshot one standing open. */
  readonly openMenu?: "who" | "where" | null;
  /** A title already typed, so the bench can show the armed state too. */
  readonly typed?: string;
  readonly onClose: () => void;
}): ReactElement {
  const [title, setTitle] = useState(typed);
  const [menu, setMenu] = useState<"who" | "where" | null>(openMenu);

  return (
    <Dialog.Root open onOpenChange={onClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[color-mix(in_srgb,var(--ink)_45%,transparent)]" />
        <Dialog.Content
          aria-describedby={undefined}
          className={cn(
            "fixed top-1/2 left-1/2 z-50 flex -translate-x-1/2 -translate-y-1/2 flex-col",
            "w-[min(680px,92vw)] rounded-md border border-line bg-card"
          )}
        >
          <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
            <span className="flex min-w-0 items-center gap-1.5 text-2xs text-muted">
              {/* The project's own ticket prefix, then what is being made. It is
                  the operator's reference verbatim, and the prefix is the one
                  short code a ctower project genuinely carries. */}
              <span className="chip">{HERE.prefix}</span>
              <span aria-hidden>›</span>
              <Dialog.Title className="m-0 truncate text-2xs font-normal text-fg">
                New ticket
              </Dialog.Title>
            </span>
            <span className="flex-1" />
            <Button variant="quiet" size="sm" aria-label="Expand">
              <Maximize2 />
            </Button>
            <Dialog.Close asChild>
              <Button variant="quiet" size="sm" aria-label="Close">
                <X />
              </Button>
            </Dialog.Close>
          </header>

          <div className="px-6 py-5">
            <input
              autoFocus
              value={title}
              placeholder="Ticket title"
              aria-label="Ticket title"
              onChange={(event): void => {
                setTitle(event.target.value);
              }}
              className={cn(
                "w-full border-0 bg-transparent p-0 text-xl font-bold tracking-[-0.02em]",
                "text-fg outline-none placeholder:text-muted/70"
              )}
            />

            {/* The reference's description line. A ticket the record keeps is a
                title, a priority, where it came from and who holds it — there is
                no field under it for prose. A note can be added once it exists. */}
            <Inert
              className="mt-2 block text-sm"
              reason="A raised ticket carries a title and nothing longer. Add a note once it is raised."
            >
              Add description…
            </Inert>

            <p className="mt-6 mb-0 flex flex-wrap items-center gap-1.5 text-sm text-muted">
              <span>For</span>
              <WhoPicker open={menu === "who"} onOpenChange={setMenu} />
              <span>in</span>
              <WherePicker open={menu === "where"} onOpenChange={setMenu} />
            </p>
          </div>

          <footer className="flex flex-wrap items-center gap-2 border-t border-line px-6 py-3">
            <Priority />
            <Inert className="chip" reason="A raised ticket lands in Backlog. Nothing chooses that.">
              Backlog
            </Inert>
            <span className="flex-1" />
            <Button variant="quiet" size="sm" onClick={onClose}>
              Discard
            </Button>
            <Button variant="primary" disabled={title.trim() === ""}>
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
 * One live row, and it is not a shortcut: leaving the person off the command is
 * what makes the record hand the ticket to the seat that sent it, so "Me" is
 * the record's own answer rather than this console filling a box in. Every
 * other name the company records is here and is dimmed, because a ticket is
 * handed to a principal the record names by identifier and no read this console
 * can make turns one of these names into one.
 */
function WhoPicker({
  open,
  onOpenChange,
}: {
  readonly open: boolean;
  readonly onOpenChange: (menu: "who" | null) => void;
}): ReactElement {
  return (
    <Picker
      label="Me"
      open={open}
      onOpenChange={(next): void => {
        onOpenChange(next ? "who" : null);
      }}
    >
      <Search placeholder="Search people" />
      <Row chosen>Me</Row>
      {STAFF.map((name) => (
        <DropdownMenu.Item
          key={name}
          disabled
          className="flex items-center gap-2.5 rounded-sm px-3 py-1.5 text-muted outline-none"
        >
          <span className="min-w-0 flex-1 truncate text-sm">{name}</span>
          <span className="shrink-0 text-2xs">cannot take one yet</span>
        </DropdownMenu.Item>
      ))}
    </Picker>
  );
}

/** Which project it is raised on — the switcher's own answer, changeable here. */
function WherePicker({
  open,
  onOpenChange,
}: {
  readonly open: boolean;
  readonly onOpenChange: (menu: "where" | null) => void;
}): ReactElement {
  return (
    <Picker
      label={HERE.name}
      open={open}
      onOpenChange={(next): void => {
        onOpenChange(next ? "where" : null);
      }}
    >
      <Search placeholder="Search projects" />
      {PROJECTS.map((project) => (
        <Row key={project.key} chosen={project.key === HERE.key} prefix={project.prefix}>
          {project.name}
        </Row>
      ))}
    </Picker>
  );
}

/**
 * Priority, spent as the reference spends its status chip: one control in the
 * footer, three words, and the only one drawn in the accent is the one the
 * record treats differently — raising a P0 is operator authority.
 */
function Priority(): ReactElement {
  const [chosen, setChosen] = useState("P1");
  return (
    <span className="flex items-center gap-1">
      {["P0", "P1", "P2"].map((priority) => (
        <button
          key={priority}
          type="button"
          aria-pressed={priority === chosen}
          onClick={(): void => {
            setChosen(priority);
          }}
          className={cn(
            "chip cursor-pointer",
            priority === chosen && "border-amber bg-amber/14 font-semibold text-amber-ink"
          )}
        >
          {priority}
        </button>
      ))}
    </span>
  );
}

/** The reference's picker: a word with a chevron, opening a searchable list. */
function Picker({
  label,
  open,
  onOpenChange,
  children,
}: {
  readonly label: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <DropdownMenu.Root open={open} onOpenChange={onOpenChange}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex cursor-pointer items-center gap-1.5 rounded-sm border border-line",
            "px-2 py-0.5 text-sm text-fg hover:bg-raised"
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
          className="z-50 w-[260px] rounded-md border border-line bg-card p-1"
        >
          {children}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function Search({ placeholder }: { readonly placeholder: string }): ReactElement {
  return (
    <div className="p-1">
      <Input defaultValue="" placeholder={placeholder} aria-label={placeholder} className="h-7" />
    </div>
  );
}

function Row({
  chosen = false,
  prefix,
  children,
}: {
  readonly chosen?: boolean;
  readonly prefix?: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <DropdownMenu.Item className="flex cursor-pointer items-center gap-2.5 rounded-sm px-3 py-1.5 outline-none data-[highlighted]:bg-raised">
      {prefix === undefined ? null : <span className="chip shrink-0">{prefix}</span>}
      <span className="min-w-0 flex-1 truncate text-sm text-fg">{children}</span>
      {chosen ? <Check aria-hidden className="size-3.5 shrink-0 text-ok" /> : null}
    </DropdownMenu.Item>
  );
}
