import { ChevronRight } from "lucide-react";
import type { ReactElement } from "react";
import { Mono } from "../ui/primitives";
import { cn } from "../ui/cn";
import type { Crew } from "./roster";
import { BREADCRUMB } from "./panes";
import { Composer, Unbuilt } from "./Unbuilt";

const TRANSCRIPT_REASON =
  "The typed transcript read and stream are authored contract law with no implementation at this head.";

/**
 * The middle pane: which seat is selected, and the conversation with it.
 *
 * The head is the reference's breadcrumb at its measured 52px — `project ›
 * seat` — with the two facts the bundle records about that seat riding the same
 * row, right-aligned in the machine face. One row, not a second header: the
 * reference has no pane header here and inventing one is what the earlier build
 * did.
 *
 * There is no tab strip. The reference tabs over concurrent workspaces in one
 * project; ctower's record has no such object, so empty tabs would be chrome
 * for its own sake.
 */
export function Conversation({ crew }: { readonly crew: Crew }): ReactElement {
  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col">
      <header className={cn(BREADCRUMB)}>
        <div className="flex min-w-0 items-center gap-1.5">
          <Mono className="shrink-0 text-muted">{crew.projectKey}</Mono>
          <ChevronRight aria-hidden className="size-3 shrink-0 text-muted" />
          <span className="min-w-0 truncate text-sm font-medium">{crew.seat}</span>
        </div>
        <span className="flex-1" />
        <div className="flex shrink-0 items-center gap-3">
          <span className="text-2xs text-muted">{crew.personaName ?? "no persona recorded"}</span>
          {crew.harnessRef === null ? (
            <span className="text-2xs text-muted">no harness recorded</span>
          ) : (
            <Mono className="text-muted">{crew.harnessRef}</Mono>
          )}
        </div>
      </header>

      <Unbuilt
        className="min-h-0 flex-1"
        what="No transcript renders here until the chat surface exists."
        why={TRANSCRIPT_REASON}
      />

      <div className="shrink-0 px-4 pb-4">
        <Composer />
      </div>
    </section>
  );
}
