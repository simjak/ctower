import { useState } from "react";
import type { ReactElement, ReactNode } from "react";
import type { TicketSession } from "@ctower/client";
import { Mono } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { Hint } from "../ui/form";
import { cn } from "../ui/cn";
import type { Answer } from "../api/client";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { livenessOf } from "./liveness";
import { PANE_HEAD } from "./panes";
import { Unbuilt } from "./Unbuilt";

/**
 * The console viewer is a real, shipped server surface and it is deliberately
 * not this browser's.
 *
 * It answers only on its own exact HTTPS origin, behind a human session cookie
 * and a CSRF value bound to that cookie, and its four operations are marked out
 * of the generated client for exactly that reason. This console holds an
 * operator bearer on a private HTTP origin and can hold none of those things,
 * so there is nothing here to read a crew's terminal with — and inventing the
 * read would be inventing the authority behind it.
 */
const TERMINAL_REASON =
  "The console viewer answers only on its own origin, behind a browser session this console does not hold.";

/**
 * Why this pane is the project's work and not this seat's: an assignment is
 * keyed by subject and a session by seat, and nothing at this head joins them.
 */
const SCOPE_REASON =
  "A session records its own seat and crew, and no read ties either to a bundle assignment's subject.";

type TabKey = "work" | "terminal";

export function Workspace({
  projectKey,
  sessions,
}: {
  readonly projectKey: string;
  readonly sessions: Answer<readonly TicketSession[]>;
}): ReactElement {
  const [tab, setTab] = useState<TabKey>("work");

  return (
    <section className="flex min-h-0 flex-1 flex-col border-l border-line">
      <div role="tablist" aria-label="Workspace" className={cn(PANE_HEAD, "gap-1 px-2")}>
        <Tab here={tab} me="work" label="Work" onPick={setTab} />
        <Tab here={tab} me="terminal" label="Terminal" onPick={setTab} />
      </div>
      <div
        role="tabpanel"
        id={`workspace-panel-${tab}`}
        aria-labelledby={`workspace-tab-${tab}`}
        // A scroll container that is not a positioning context lets any
        // absolutely-positioned descendant resolve against the document and
        // escape the clip. This one holds a list, so it says so once here.
        className="relative min-h-0 flex-1 overflow-y-auto"
      >
        {tab === "work" ? (
          <Work projectKey={projectKey} sessions={sessions} />
        ) : (
          <Unbuilt
            className="h-full"
            what="A crew's terminal is not readable from this console."
            why={TERMINAL_REASON}
          />
        )}
      </div>
    </section>
  );
}

function Tab({
  here,
  me,
  label,
  onPick,
}: {
  readonly here: TabKey;
  readonly me: TabKey;
  readonly label: string;
  readonly onPick: (tab: TabKey) => void;
}): ReactElement {
  return (
    <button
      type="button"
      role="tab"
      id={`workspace-tab-${me}`}
      // Both tabs stay in the tab order rather than taking a roving index: the
      // law here is that every control is keyboard-reachable, and two stops
      // reach both panels without teaching an arrow-key convention first.
      aria-selected={here === me}
      aria-controls={`workspace-panel-${me}`}
      onClick={(): void => {
        onPick(me);
      }}
      className={cn(
        // The underline sits on the head's own rule rather than floating above
        // it, so the active tab reads as attached to the panel it opens.
        "-mb-px flex cursor-pointer items-center self-stretch border-b-2 px-2 text-xs",
        here === me ? "border-amber font-semibold text-fg" : "border-transparent text-muted"
      )}
    >
      {label}
    </button>
  );
}

/** The work the record holds for this project, newest first. */
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
    <div className="px-4 py-3">
      <p className="mt-0 mb-3 flex items-center gap-1.5 text-2xs text-muted">
        Work recorded in <Mono>{projectKey}</Mono>
        <Hint text={SCOPE_REASON} />
      </p>
      {sessions.value.length === 0 ? (
        <p className="m-0 text-sm text-muted">Nothing has been worked on in this project yet.</p>
      ) : (
        <ul className="m-0 list-none space-y-3 p-0">
          {sessions.value.map((session) => (
            <SessionCard key={session.session_id} session={session} />
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
    return <Asking what="Reading this project's work" />;
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

function SessionCard({ session }: { readonly session: TicketSession }): ReactElement {
  const live = livenessOf(session);
  return (
    <li className="border-t border-line pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-baseline gap-1.5">
        {live.mark === null ? null : <Mark name={live.mark} />}
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{session.seat_key}</span>
        <span className="shrink-0 text-2xs text-muted">{live.word}</span>
      </div>
      <dl className="m-0 mt-1.5">
        <Fact label="Crew">{session.crew_name}</Fact>
        <Fact label="Branch">{session.branch_ref}</Fact>
        <Fact label="Worktree">{session.worktree_ref}</Fact>
        <Fact label="Model">{session.model_ref}</Fact>
        <Fact label="Started">{session.started_at}</Fact>
        <Fact label="State changes">{session.transition_count}</Fact>
        <Fact label="Tokens">
          {session.tokens === null
            ? null
            : `${String(session.tokens.input_tokens)} in · ${String(session.tokens.output_tokens)} out`}
        </Fact>
      </dl>
    </li>
  );
}

function Fact({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}): ReactElement {
  // Label over value rather than beside it. A branch or worktree ref is longer
  // than the column a two-up split leaves in a 304px pane, and the break lands
  // mid-word — `/srv/projects/ctowe` / `r/.worktrees/…` is a path an operator
  // has to reassemble by eye before they can read it.
  return (
    <div className="py-1">
      <dt className="text-2xs text-muted">{label}</dt>
      <dd className="m-0 break-all">
        {children === null ? (
          <span className="text-2xs text-muted">none recorded</span>
        ) : (
          <Mono>{children}</Mono>
        )}
      </dd>
    </div>
  );
}
