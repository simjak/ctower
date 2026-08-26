import { Dialog } from "radix-ui";
import { X } from "lucide-react";
import type { ReactElement } from "react";
import { Button, Mono } from "../ui/primitives";
import { Inert } from "../projects/Inert";
import { cn } from "../ui/cn";

/**
 * What "make a crew" opens today, and it is a placeholder that says so.
 *
 * Two things stop this being a form, and both are the record's shape rather
 * than unfinished work:
 *
 * 1. Issuing a seat credential does not **mint** one. `--credential-ref` and
 *    its digest are both required inputs: the ceremony records a reference to
 *    credential material the operator already holds. A console cannot invent
 *    that, so it cannot complete the ceremony on its own.
 * 2. Nothing reads a seat back. `issueSeatCredential` and `revokeSeatCredential`
 *    are the whole surface; the register read is proposed under AC-CHAT-11 and
 *    does not exist. Even a mint that succeeded could never be confirmed on a
 *    later visit, so a form here would take an answer and be unable to say
 *    whether it landed.
 *
 * `DESIGN.md` is unambiguous about what to draw instead: an affordance the
 * record cannot honour is dimmed, dashed, not a control, with its reason on
 * hover and on focus — and it is never an input, because a box that takes an
 * answer and drops it is worse than an absence. So the shape of a crew is
 * drawn, the one sentence is said in words, and the command sits behind the
 * developer disclosure that is the one place machine text is allowed to live.
 */
export function NewCrew({
  company,
  open,
  onOpenChange,
}: {
  /** The company's name, for the trail at the top. */
  readonly company: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}): ReactElement {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[color-mix(in_srgb,var(--ink)_45%,transparent)]" />
        <Dialog.Content
          aria-describedby={undefined}
          className={cn(
            "fixed top-1/2 left-1/2 z-50 flex max-h-[86dvh] w-[min(560px,92vw)] flex-col",
            "-translate-x-1/2 -translate-y-1/2 rounded-md border border-line bg-card"
          )}
        >
          <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
            <span className="flex min-w-0 items-center gap-1.5 text-2xs text-muted">
              <span className="truncate">{company}</span>
              <span aria-hidden>›</span>
              <Dialog.Title className="m-0 truncate text-2xs font-normal text-fg">
                New crew
              </Dialog.Title>
            </span>
            <span className="flex-1" />
            <Dialog.Close asChild>
              <Button variant="quiet" size="sm" aria-label="Close">
                <X />
              </Button>
            </Dialog.Close>
          </header>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5">
            <p className="m-0 text-sm text-muted">
              A crew is one of your people, on a harness, working in one project.
            </p>
            <div className="space-y-2">
              <Slot label="Who" hint="One of the agents this company records." />
              <Slot label="On what" hint="The harness that agent already runs on." />
              <Slot label="In which project" hint="A crew works in exactly one." />
            </div>
            <p className="m-0 text-sm">
              ctower records the crew, but the key that lets it work is one you bring from outside —
              and no read gives it back — so a crew is made from your own command line until this
              console can tell you it worked.
            </p>
            <Developer />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/**
 * Why every part of this is dimmed, said once and reachable from each of them.
 * `Inert` keeps it in the tab order, so a keyboard reaches the reason too.
 */
const SLOT_REASON = "Nothing here can be filled in: no read confirms a seat once it is issued.";

/** One part of a crew, drawn as the shape it will take and not as a control. */
function Slot({ label, hint }: { readonly label: string; readonly hint: string }): ReactElement {
  return (
    <Inert
      reason={SLOT_REASON}
      className="flex items-center gap-3 rounded-sm border border-line px-3 py-2"
    >
      <span className="w-[128px] shrink-0 text-xs font-semibold">{label}</span>
      <span className="min-w-0 flex-1 truncate text-xs">{hint}</span>
    </Inert>
  );
}

/** The one place a machine-owned value may sit, named for who opens it. */
function Developer(): ReactElement {
  return (
    <details className="border-t border-line pt-3">
      <summary className="cursor-pointer text-xs text-muted">Developer details</summary>
      <p className="mt-2 mb-1 text-xs text-muted">
        Two ceremonies, in order: the company bundle binds the profile to the seat, then the
        operator issues the seat credential.
      </p>
      <Mono className="block text-2xs break-all text-muted">
        ctowerctl credential seat issue --project-key … --seat-key … --display-name … --scope
        capture --credential-ref … --credential-digest …
      </Mono>
    </details>
  );
}
