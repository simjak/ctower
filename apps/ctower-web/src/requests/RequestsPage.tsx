import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";
import type { RequestList } from "@ctower/client";
import { Mark } from "../ui/marks";
import { Mono, PageHead } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { Detail } from "./Detail";
import { Empty } from "./Empty";
import { coverage, moment } from "./facts";
import { Ledger } from "./Ledger";
import { Scope } from "./Scope";
import { useCarryOver } from "./useCarryOver";
import { useLedger } from "./useLedger";

/**
 * Requests — everything asked of this company, and where each ask stands.
 *
 * The page is one read wide. `listRequests` is the only operation the contract
 * declares over this record that answers with Requests, so the ledger, the
 * detail and the scope control are all that read: opening a row costs no second
 * call, and there is no per-request operation to make one with.
 *
 * Five outcomes render as five different things, and none of them collapses
 * into another — a refusal, silence, an answer this client cannot read, an
 * answer with rows, and an answer with none.
 */
export function RequestsPage(): ReactElement {
  const [project, setProject] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [opened, setOpened] = useState<string | null>(null);
  const [portfolio, setPortfolio] = useState<readonly string[]>([]);
  const ledger = useLedger(project, reloadKey);
  const answered = ledger.kind === "answered" ? ledger.value : null;
  const rows = answered?.rows ?? [];
  // Nothing found and nothing looked at are different facts. When no project
  // answered, the ledger is not empty — it is unread — and the only honest
  // render is the warning that says so. The empty state, and the second read
  // behind it, exist for the case where something actually answered.
  const emptied = answered !== null && rows.length === 0 && answered.answered_project_count > 0;
  const carryOver = useCarryOver(emptied);
  const open = rows.find((row) => row.request_id === opened) ?? null;

  const close = useCallback((): void => {
    setOpened(null);
  }, []);

  // The whole portfolio is a fact of the unfiltered read alone: a scoped answer
  // knows only its own project, so a control built from one would forget every
  // other destination the moment it was used.
  useEffect(() => {
    if (project === null && answered !== null) {
      setPortfolio(answered.requested_projects);
    }
  }, [project, answered]);

  useEffect((): (() => void) => {
    const dismiss = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        close();
      }
    };
    window.addEventListener("keydown", dismiss);
    return (): void => {
      window.removeEventListener("keydown", dismiss);
    };
  }, [close]);

  return (
    <>
      <PageHead title="Requests" subtitle={answered === null ? undefined : standing(answered)}>
        <Scope
          projects={portfolio}
          here={project}
          onGo={(next): void => {
            setProject(next);
          }}
        />
      </PageHead>

      {ledger.kind === "asking" ? <Asking what="Reading the requests" /> : null}
      {ledger.kind === "refused" ? (
        <Refused problem={ledger.problem} action="Nothing was read. Read again to ask ctower." />
      ) : null}
      {ledger.kind === "unreachable" ? (
        <Unreachable
          detail={ledger.detail}
          action="This is not an empty ledger; it is a ledger that was not read."
        />
      ) : null}
      {ledger.kind === "malformed" ? <Malformed detail={ledger.detail} /> : null}

      {answered === null ? null : (
        <>
          <Unanswered projects={answered.unanswered_projects} />
          {rows.length === 0 ? (
            emptied ? (
              <Empty
                carryOver={carryOver}
                onReadAgain={(): void => {
                  setReloadKey((count) => count + 1);
                }}
              />
            ) : null
          ) : (
            <div className="flex items-start gap-4">
              <div className="min-w-0 flex-1">
                <Ledger rows={rows} open={open?.request_id ?? null} onOpen={setOpened} />
              </div>
              {open === null ? null : (
                <aside className="sticky top-[68px] w-[380px] shrink-0">
                  <Detail row={open} onClose={close} />
                </aside>
              )}
            </div>
          )}
        </>
      )}
    </>
  );
}

/** What this answer covers, at which position, and when it was taken. */
function standing(list: RequestList): ReactElement {
  return (
    <>
      <span>{coverage(list)}</span>
      <span>·</span>
      <span>{list.rows.length} shown</span>
      <span>·</span>
      <Mono>read {moment(list.observed_at)}</Mono>
    </>
  );
}

/**
 * A project that did not answer is not a project with no requests.
 *
 * The warning is about this answer's reach, and it draws the warn mark for
 * exactly that reason: nothing here claims a state for the projects it names,
 * because their state is what was not read.
 */
function Unanswered({ projects }: { readonly projects: readonly string[] }): ReactElement | null {
  if (projects.length === 0) {
    return null;
  }
  return (
    <div className="mb-4 flex items-start gap-2 rounded-md border border-amber/40 bg-amber/10 p-3">
      <Mark name="warn" className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <p className="m-0 text-sm font-medium text-fg">
          {projects.length === 1
            ? "One project did not answer; its requests are not below."
            : `${String(projects.length)} projects did not answer; their requests are not below.`}
        </p>
        <Mono className="mt-1 block text-muted">{projects.join(" · ")}</Mono>
      </div>
    </div>
  );
}
