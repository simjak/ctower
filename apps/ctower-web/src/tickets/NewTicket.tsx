import { ArrowLeft } from "lucide-react";
import type { ReactElement } from "react";
import type { Priority, TicketCommandResult } from "@ctower/client";
import { Field } from "../ui/form";
import { Button, Card, CardBody, Chip, Input, Mono, PageHead } from "../ui/primitives";
import { cn } from "../ui/cn";
import { Fact } from "./facts";
import { NotYetDurable, Sent } from "./Sent";
import { useRaise } from "./useRaise";
import type { Draft } from "./useRaise";

const PRIORITIES: readonly Priority[] = ["P0", "P1", "P2"];

/**
 * Raising a ticket.
 *
 * Every field is one the command carries, named as the job it does rather than
 * as the property it sets. There is no field this form invents and none it
 * fills in behind the operator: what is sent is what is on the screen.
 */
export function NewTicket({
  projectKey,
  custodians,
  onBack,
  onRaised,
}: {
  readonly projectKey: string;
  /** The custodians this board already has, offered as suggestions. */
  readonly custodians: readonly string[];
  readonly onBack: () => void;
  readonly onRaised: (ticketId: string) => void;
}): ReactElement {
  const raise = useRaise(projectKey);
  const edit = (part: Partial<Draft>): void => {
    raise.setDraft({ ...raise.draft, ...part });
  };

  return (
    <>
      <Button variant="quiet" size="sm" className="-ml-2.5 mb-3" onClick={onBack}>
        <ArrowLeft /> Tickets
      </Button>
      <PageHead
        title="New ticket"
        subtitle={
          <>
            <span>on</span>
            <Mono>{projectKey}</Mono>
          </>
        }
      />
      {/* A form is read down a column, not across a deck: five fields stretched
          to 1200px put a 36-character id in a box six times its length. */}
      <Card className="max-w-[720px]">
        <CardBody className="space-y-4">
          <Field label="TITLE">
            <Input
              aria-label="Title"
              value={raise.draft.title}
              maxLength={200}
              onChange={(event): void => {
                edit({ title: event.target.value });
              }}
            />
          </Field>

          <Field label="PRIORITY" hint="Only an operator may raise a P0.">
            <div className="flex gap-1.5">
              {PRIORITIES.map((priority) => (
                <Button
                  key={priority}
                  size="sm"
                  aria-pressed={raise.draft.priority === priority}
                  className={cn(
                    "min-w-14",
                    raise.draft.priority === priority && "border-amber bg-amber/14 font-semibold"
                  )}
                  onClick={(): void => {
                    edit({ priority });
                  }}
                >
                  {priority}
                </Button>
              ))}
            </div>
          </Field>

          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
            <Field
              label="CAME FROM"
              hint="What kind of thing raised this: an issue, a review, a call."
            >
              <Input
                aria-label="Came from"
                className="mono"
                value={raise.draft.sourceKind}
                maxLength={64}
                onChange={(event): void => {
                  edit({ sourceKind: event.target.value });
                }}
              />
            </Field>
            <Field label="REFERENCE">
              <Input
                aria-label="Reference"
                className="mono"
                value={raise.draft.sourceRef}
                maxLength={256}
                onChange={(event): void => {
                  edit({ sourceRef: event.target.value });
                }}
              />
            </Field>
          </div>

          <Field
            label="CUSTODIAN"
            hint="The Commander who takes it; ctower reads the project from their seat."
          >
            <Input
              aria-label="Custodian"
              className="mono"
              list="ctower-custodians"
              value={raise.draft.custodian}
              onChange={(event): void => {
                edit({ custodian: event.target.value });
              }}
            />
            <datalist id="ctower-custodians">
              {custodians.map((custodian) => (
                <option key={custodian} value={custodian} />
              ))}
            </datalist>
          </Field>

          <footer className="flex items-center gap-3 border-t border-line pt-4">
            <p className="m-0 flex-1 text-2xs text-muted">
              Recorded on send. A ticket is not withdrawn, only resolved.
            </p>
            <Button variant="primary" disabled={!raise.armed} onClick={raise.send}>
              Raise it
            </Button>
          </footer>

          {raise.sent === null ? null : (
            <Sent
              sent={raise.sent}
              doing="Raising this ticket"
              nothingHappened="No ticket was raised."
              onRetry={raise.retry}
              receipt={
                raise.sent.kind === "answered" ? (
                  <Raised receipt={raise.sent.value} onOpen={onRaised} />
                ) : null
              }
            />
          )}
        </CardBody>
      </Card>
    </>
  );
}

function Raised({
  receipt,
  onOpen,
}: {
  readonly receipt: TicketCommandResult;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  const accepted = receipt.durability_state === "accepted";
  return (
    <div className="rounded-md border border-line bg-raised p-3">
      <p className="m-0 flex flex-wrap items-center gap-2 text-sm">
        {accepted ? <Chip tone="ok">raised</Chip> : <Chip tone="amber">not yet durable</Chip>}
        <Mono className="text-fg">
          {receipt.ticket.display_key ?? receipt.ticket.ticket_id.slice(0, 8)}
        </Mono>
        <span className="flex-1" />
        <Button
          size="sm"
          onClick={(): void => {
            onOpen(receipt.ticket.ticket_id);
          }}
        >
          Open it
        </Button>
      </p>
      {accepted ? null : (
        <div className="mt-1.5">
          <NotYetDurable />
        </div>
      )}
      <div className="mt-2">
        <Fact label="ticket">
          <Mono className="break-all">{receipt.ticket.ticket_id}</Mono>
        </Fact>
        <Fact label="command">
          <Mono className="break-all">{receipt.command_id}</Mono>
        </Fact>
      </div>
    </div>
  );
}
