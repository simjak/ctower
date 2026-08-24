import type { ReactElement } from "react";
import { Card, CardBody, CardHeader, CardTitle, Mono } from "../../ui/primitives";

/**
 * What "make a crew" opens today, and it is a placeholder that says so.
 *
 * Two things stop this being a form, and both are the record's shape rather than
 * unfinished work:
 *
 * 1. Only the operator may issue a seat credential, and the issue command does
 *    not MINT one — it records a reference to credential material the operator
 *    already holds (`--credential-ref` and its digest are both required inputs).
 *    A console cannot invent that, so it cannot complete the ceremony.
 * 2. Nothing reads a seat back. `issueSeatCredential` and `revokeSeatCredential`
 *    are the whole surface; no operation lists one. Even a mint that succeeded
 *    could never be confirmed on a later visit, so a form here would take an
 *    answer and be unable to say whether it landed.
 *
 * `DESIGN.md` is unambiguous about what to draw instead: an affordance the
 * record cannot honour is dimmed, dashed, not a control, with its reason on
 * focus — and it is never an input, because a box that takes an answer and drops
 * it is worse than an absence. So the shape of a crew is drawn, the one sentence
 * is said in words, and the command sits behind the developer disclosure that is
 * the one place machine text is allowed to live.
 */
export function NewCrew(): ReactElement {
  return (
    <Card className="max-w-[560px]">
      <CardHeader>
        <CardTitle className="flex-1">New crew</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <p className="m-0 text-sm text-muted">
          A crew is one of your people, on a harness, working in one project.
        </p>
        <div className="space-y-2">
          <Slot label="Who" hint="One of the agents this company records." />
          <Slot label="On what" hint="The harness that agent already runs on." />
          <Slot label="In which project" hint="A crew works in exactly one." />
        </div>
        <p className="m-0 text-sm">
          ctower records the crew, but the key that lets it work is one you bring from outside — and
          no read gives it back — so a crew is made from your own command line until this console
          can tell you it worked.
        </p>
        <Developer />
      </CardBody>
    </Card>
  );
}

/**
 * One part of a crew, drawn as the shape it will take and not as a control.
 *
 * Dashed and dimmed, `aria-disabled`, and reachable by keyboard so the reason is
 * available to someone who never uses a pointer. It is a `div`, not an `input`:
 * nothing here can be typed into, and looking like it could is the lie.
 */
function Slot({ label, hint }: { readonly label: string; readonly hint: string }): ReactElement {
  return (
    <div
      aria-disabled="true"
      tabIndex={0}
      title={hint}
      className="flex items-center gap-3 rounded-sm border border-dashed border-line px-3 py-2 opacity-60 focus:outline-2 focus:outline-offset-2 focus:outline-amber"
    >
      <span className="w-[128px] shrink-0 text-xs font-semibold">{label}</span>
      <span className="min-w-0 flex-1 truncate text-xs text-muted">{hint}</span>
    </div>
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
