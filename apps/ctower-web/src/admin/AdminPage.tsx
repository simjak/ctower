import { useState } from "react";
import type { ReactElement } from "react";
import type { ConsoleSessionAllowance } from "@ctower/client";
import type { Answer } from "../api/client";
import { Mark } from "../ui/marks";
import { Card, CardBody, Mono, PageHead } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { AllowCard } from "./AllowCard";
import { EMPTY } from "./allowance";
import type { Draft } from "./allowance";
import { OutOfReach } from "./OutOfReach";
import { useAllow } from "./useAllow";

/**
 * SYSTEM. One job the operator has here: decide who may watch a crew's
 * terminal.
 *
 * The screen is in two halves and the second one is the point. Console access
 * is five jobs; this console can reach exactly one of them, and the other four
 * are named on the page with their reasons rather than left to be discovered.
 * The alternative — showing the one job alone — would read as the whole of
 * console access and would be the one dishonest thing on an honest surface.
 */
export function AdminPage(): ReactElement {
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const { answer, allow } = useAllow();

  return (
    <>
      <PageHead title="Admin" subtitle="Who may watch a crew's terminal." />
      <div className="space-y-4">
        <AllowCard
          draft={draft}
          onDraft={setDraft}
          onAllow={allow}
          busy={answer?.kind === "asking"}
        />
        {answer === null ? null : <Outcome answer={answer} />}
        <OutOfReach />
      </div>
    </>
  );
}

/** What the tower said about the last allowance, and nothing before there was one. */
function Outcome({ answer }: { readonly answer: Answer<ConsoleSessionAllowance> }): ReactElement {
  switch (answer.kind) {
    case "asking":
      return <Asking what="Allowing this terminal" />;
    case "answered":
      return <Allowed allowance={answer.value} />;
    case "refused":
      return <Refused problem={answer.problem} action="Nothing was recorded. Fix what it names." />;
    case "unreachable":
      return (
        <Unreachable
          detail={answer.detail}
          action="This command carries no key, so it was sent once. It may already be recorded — check before asking again."
        />
      );
    case "malformed":
      return <Malformed detail={answer.detail} />;
  }
}

/**
 * The allowance the tower recorded. `●` is earned here and only here on this
 * screen: it is the one state on the page backed by a fact ctower wrote down.
 */
function Allowed({ allowance }: { readonly allowance: ConsoleSessionAllowance }): ReactElement {
  return (
    <Card className="border-ok/40">
      <CardBody className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <Mark name="done" />
          Watching allowed
        </span>
        <Mono className="text-muted">{allowance.console_session_id}</Mono>
        <span className="ml-auto text-xs text-muted">
          {allowance.crew_name} · {allowance.project_key}
        </span>
        <Mono className="text-muted">{allowance.allowed_at}</Mono>
      </CardBody>
    </Card>
  );
}
