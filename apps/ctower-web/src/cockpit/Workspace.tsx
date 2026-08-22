import { useState } from "react";
import type { ReactElement } from "react";
import type { TicketSession } from "@ctower/client";
import { Mono } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { Hint } from "../ui/form";
import { cn } from "../ui/cn";
import type { Answer } from "../api/client";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { livenessOf } from "./liveness";
import { FOOT_TAB_ROW, LIST_ROW, TAB_ROW } from "./panes";
import { Unbuilt } from "./Unbuilt";

/**
 * The console viewer is a real, shipped server surface and it is deliberately
 * not this browser's: it answers only on its own exact HTTPS origin, behind a
 * human session cookie and a CSRF value bound to it, and its operations are
 * marked out of the generated client for exactly that reason.
 */
const TERMINAL_REASON =
  "The console viewer answers only on its own origin, behind a browser session this console does not hold.";
const SCOPE_REASON =
  "A session records its own seat and crew, and no read ties either to a bundle assignment's subject.";
const FILES_REASON = "No file, diff or check read exists in the authored contract at this head.";

type TopTab = "work" | "files" | "checks";
type FootTab = "run" | "terminal";

/**
 * The right pane, in the reference's shape: a tab row over a list, and a second
 * tab row over a panel at the foot.
 *
 * The reference fills all of this with a changes list, and ctower has no diff
 * read — so `Files` and `Checks` are drawn and honestly empty. What ctower does
 * have is the project's recorded work, and it takes the reference's own row
 * grammar rather than a shape of its own: identifier left, quantities right, on
 * the same 32px pitch. One tab label is ctower's word for the job instead of
 * the reference's; that is the divergence, and it is named.
 */
export function Workspace({
  projectKey,
  sessions,
}: {
  readonly projectKey: string;
  readonly sessions: Answer<readonly TicketSession[]>;
}): ReactElement {
  const [top, setTop] = useState<TopTab>("work");
  const [foot, setFoot] = useState<FootTab>("terminal");
  const count = sessions.kind === "answered" ? sessions.value.length : null;

  return (
    <section className="flex min-h-0 flex-1 flex-col border-l border-line">
      <div role="tablist" aria-label="Workspace" className={cn(TAB_ROW)}>
        <Tab here={top} me="work" label="Work" count={count} onPick={setTop} />
        <Tab here={top} me="files" label="Files" count={null} onPick={setTop} />
        <Tab here={top} me="checks" label="Checks" count={null} onPick={setTop} />
      </div>
      <div
        role="tabpanel"
        id={`workspace-panel-${top}`}
        aria-labelledby={`workspace-tab-${top}`}
        className="relative min-h-0 flex-[3] overflow-y-auto"
      >
        {top === "work" ? (
          <Work projectKey={projectKey} sessions={sessions} />
        ) : (
          <Unbuilt
            className="h-full"
            what={top === "files" ? "No changed files render here." : "No checks render here."}
            why={FILES_REASON}
          />
        )}
      </div>

      <div role="tablist" aria-label="Session" className={cn(TAB_ROW, FOOT_TAB_ROW)}>
        <Tab here={foot} me="terminal" label="Terminal" count={null} onPick={setFoot} />
        <Tab here={foot} me="run" label="Run" count={null} onPick={setFoot} />
      </div>
      <div
        role="tabpanel"
        id={`foot-panel-${foot}`}
        aria-labelledby={`foot-tab-${foot}`}
        className="relative min-h-0 flex-[2] overflow-y-auto"
      >
        <Unbuilt
          className="h-full"
          what={
            foot === "terminal"
              ? "A crew's terminal is not readable from this console."
              : "Nothing runs from this console."
          }
          why={foot === "terminal" ? TERMINAL_REASON : FILES_REASON}
        />
      </div>
    </section>
  );
}

/**
 * The reference's active tab is a filled grey pill carrying a muted count, and
 * its inactive tabs are muted text with no decoration at all. Weight and fill
 * carry the state; no hue does.
 */
function Tab<T extends string>({
  here,
  me,
  label,
  count,
  onPick,
}: {
  readonly here: T;
  readonly me: T;
  readonly label: string;
  readonly count: number | null;
  readonly onPick: (tab: T) => void;
}): ReactElement {
  const active = here === me;
  return (
    <button
      type="button"
      role="tab"
      id={`${me === "run" || me === "terminal" ? "foot" : "workspace"}-tab-${me}`}
      aria-selected={active}
      aria-controls={`${me === "run" || me === "terminal" ? "foot" : "workspace"}-panel-${me}`}
      onClick={(): void => {
        onPick(me);
      }}
      className={cn(
        "flex h-6.5 cursor-pointer items-center gap-1.5 rounded-sm px-2.5 text-xs",
        active ? "bg-raised font-medium text-fg" : "text-muted"
      )}
    >
      {label}
      {count === null ? null : <span className="text-muted">{count}</span>}
    </button>
  );
}

function Work({
  projectKey,
  sessions,
}: {
  readonly projectKey: string;
  readonly sessions: Answer<readonly TicketSession[]>;
}): ReactElement {
  if (sessions.kind !== "answered") {
    return <Waiting sessions={sessions} />;
  }
  return (
    <div className="py-1">
      <div className="flex items-center gap-1.5 px-3 pt-1 pb-2">
        <span className="text-2xs text-muted">Work recorded in</span>
        <Mono className="text-muted">{projectKey}</Mono>
        <Hint text={SCOPE_REASON} />
      </div>
      {sessions.value.length === 0 ? (
        <p className="m-0 px-3 text-sm text-muted">
          Nothing has been worked on in this project yet.
        </p>
      ) : (
        <ul className="m-0 list-none p-0">
          {sessions.value.map((session) => (
            <SessionRow key={session.session_id} session={session} />
          ))}
        </ul>
      )}
    </div>
  );
}

/** Every answer that is not an answer, in the grammar the shell already uses. */
function Waiting({
  sessions,
}: {
  readonly sessions: Answer<readonly TicketSession[]>;
}): ReactElement {
  if (sessions.kind === "asking") {
    return (
      <div className="px-3">
        <Asking what="Reading this project's work" />
      </div>
    );
  }
  return (
    <div className="p-3">
      {sessions.kind === "refused" ? (
        <Refused problem={sessions.problem} action="Nothing was read. Reload to ask again." />
      ) : null}
      {sessions.kind === "unreachable" ? (
        <Unreachable detail={sessions.detail} action="Reload to ask again." />
      ) : null}
      {sessions.kind === "malformed" ? <Malformed detail={sessions.detail} /> : null}
    </div>
  );
}

/**
 * One session, in the reference's file-row grammar: the dimmed context first,
 * the identifier in ink, and the quantities right-aligned. The reference puts a
 * directory before a basename; this puts the crew before the seat, which is the
 * same move — the part you scan past, then the part you are looking for.
 */
function SessionRow({ session }: { readonly session: TicketSession }): ReactElement {
  const live = livenessOf(session);
  return (
    <li>
      <div className={cn(LIST_ROW, "gap-1.5")} title={session.branch_ref}>
        {live.mark === null ? null : <Mark name={live.mark} />}
        {/* The reference truncates the directory and never the basename: the
            part you scan past gives up its width, the part you are looking for
            keeps it. Here the crew is the prefix and the seat is the name. */}
        <span className="flex min-w-0 items-baseline text-sm">
          <span className="min-w-0 truncate text-muted">{session.crew_name}/</span>
          <span className="shrink-0 font-medium">{session.seat_key}</span>
        </span>
        <span className="flex-1" />
        <span className="shrink-0 text-2xs text-muted">{live.word}</span>
        {session.tokens === null ? null : (
          // A count carries its unit, or it is just a large number.
          <Mono className="shrink-0 text-muted">{session.tokens.total_tokens} tok</Mono>
        )}
      </div>
      <div className={cn(LIST_ROW, "h-5 gap-1.5 pt-0 text-2xs")}>
        <Mono className="min-w-0 truncate text-muted">{session.branch_ref}</Mono>
        <span className="flex-1" />
        <Mono className="shrink-0 text-muted">{session.model_ref}</Mono>
      </div>
    </li>
  );
}
