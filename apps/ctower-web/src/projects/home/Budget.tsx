import type { ReactElement } from "react";
import { Card, CardBody, CardHeader, CardTitle } from "../../ui/primitives";
import { Inert } from "../Inert";

/**
 * What this project costs. Nothing here is a number yet, and that is the whole
 * screen's content.
 *
 * ctower records what work happened, not what it cost: no declared operation
 * answers with a spend, a rate, or a budget, so every figure on this tab would
 * have to be made up. The shape stands — it is where the answer will land — and
 * each slot says why it is empty rather than drawing a zero. A zero is a fact
 * about money spent; this is the absence of a read.
 */
export function Budget(): ReactElement {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Spend</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Slot
              label="Observed"
              reason="No declared read answers with what a project has spent."
            />
            <Slot label="Budget" reason="A recorded project carries no budget." />
          </div>

          <div>
            <div className="mb-1.5 text-2xs text-muted">Remaining</div>
            <Inert
              className="block h-2 w-full rounded-full border border-line"
              reason="A bar needs a spend and a budget. Neither is recorded."
            >
              <span className="sr-only">no figure</span>
            </Inert>
          </div>

          <Slot label="Alert above" reason="There is no spend to threshold." />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Set a budget</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1">
            <div className="mb-1.5 text-2xs text-muted">Amount</div>
            <Inert
              className="flex h-9 items-center rounded-sm border border-line px-3 text-sm"
              reason="No declared operation records a budget against a project."
            >
              Not set
            </Inert>
          </div>
          <Inert
            className="flex h-9 items-center rounded-sm border border-line px-4 text-sm font-semibold"
            reason="No declared operation records a budget against a project."
          >
            Set budget
          </Inert>
        </CardBody>
      </Card>
    </div>
  );
}

function Slot({
  label,
  reason,
}: {
  readonly label: string;
  readonly reason: string;
}): ReactElement {
  return (
    <div>
      <div className="mb-1.5 text-2xs text-muted">{label}</div>
      <Inert className="block text-lg font-semibold" reason={reason}>
        Not recorded
      </Inert>
    </div>
  );
}
