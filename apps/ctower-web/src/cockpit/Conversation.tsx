import type { ReactElement } from "react";
import { Mono } from "../ui/primitives";
import { cn } from "../ui/cn";
import type { Crew } from "./roster";
import { PANE_HEAD } from "./panes";
import { InertControl, Unbuilt } from "./Unbuilt";

const TRANSCRIPT_REASON =
  "The typed transcript read and stream are authored contract law with no implementation at this head.";
const COMPOSER_REASON =
  "Composer send is authored as one typed operator command with no implementation at this head.";
const STEER_REASON =
  "Steer is authored as the same typed command path as send, with no implementation at this head.";

/**
 * The middle pane: who this crew is, and the conversation with them.
 *
 * The head is the bundle's own record of this seat — the persona assigned to
 * it and the harness that profile names — and nothing else. It carries no
 * state chip, because no read at this head can say what this seat is doing.
 *
 * The composer is drawn as its two real verbs rather than as a text box. A box
 * invites typing, and typing into a surface that cannot send is the one thing
 * an operator console may never do; two inert controls that say what they would
 * be is the same information without the lie.
 */
export function Conversation({ crew }: { readonly crew: Crew }): ReactElement {
  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col">
      <header className={cn(PANE_HEAD, "gap-3 px-4")}>
        {/* The heading is the seat, because the seat is what the operator
            picked. The persona is a property of it and sits underneath — this
            company assigns one persona to every seat, so leading with it would
            title ten different screens identically. */}
        <div className="min-w-0 flex-1">
          <h2 className="m-0 truncate text-md leading-tight font-semibold tracking-[-0.02em]">
            {crew.seat}
          </h2>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-muted">
            <Mono>{crew.projectKey}</Mono>
            <span>{crew.personaName ?? "no persona recorded"}</span>
            {crew.harnessRef === null ? (
              <span>no harness recorded</span>
            ) : (
              <Mono>{crew.harnessRef}</Mono>
            )}
          </div>
        </div>
      </header>

      <Unbuilt
        className="min-h-0 flex-1"
        what="No transcript renders here until the chat surface exists."
        why={TRANSCRIPT_REASON}
      />

      <footer className="flex items-center gap-2 border-t border-line px-4 py-3">
        <InertControl label="Send a message" reason={COMPOSER_REASON} className="flex-1" />
        <InertControl label="Steer" reason={STEER_REASON} />
      </footer>
    </section>
  );
}
