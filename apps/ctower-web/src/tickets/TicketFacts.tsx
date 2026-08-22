import type { ReactElement } from "react";
import type { BoardCard, TicketResource } from "@ctower/client";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { Fact, Instant, Unrecorded } from "./facts";

/**
 * Everything else the two reads know about this ticket, as labelled facts.
 *
 * A field the read answered with `null` is drawn as the absence it is, in
 * words. Nothing is filled in from a neighbour and nothing is inferred: an
 * assignee nobody set is "nobody yet", not the custodian.
 */
export function TicketFacts({
  ticket,
  card,
}: {
  readonly ticket: TicketResource;
  readonly card: BoardCard | null;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Facts</CardTitle>
        <span className="flex-1" />
        <Chip tone={ticket.durability_state === "accepted" ? "ok" : "amber"}>
          {ticket.durability_state === "accepted" ? "accepted" : "not durable"}
        </Chip>
      </CardHeader>
      <CardBody className="py-1">
        <Fact label="project">
          {card === null ? (
            <Unrecorded what="Not on this board yet" />
          ) : (
            <Mono>{card.project_key}</Mono>
          )}
        </Fact>
        <Fact label="came from">
          <Mono className="break-all">
            {ticket.source.kind} {ticket.source.ref}
          </Mono>
        </Fact>
        <Fact label="raised">
          <Instant at={ticket.created_at} />
        </Fact>
        <Fact label="custodian">
          <Mono className="break-all">{ticket.custodian_id}</Mono>
        </Fact>
        <Fact label="assignee">
          {card?.assignee_id == null ? (
            <Unrecorded what="Nobody yet" />
          ) : (
            <Mono className="break-all">{card.assignee_id}</Mono>
          )}
        </Fact>
        <Fact label="version">
          <Mono>{ticket.version}</Mono>
        </Fact>
        <Fact label="ticket">
          <Mono className="break-all">{ticket.ticket_id}</Mono>
        </Fact>
      </CardBody>
    </Card>
  );
}

/** Labels a person applied, when any were. */
export function Labels({ card }: { readonly card: BoardCard }): ReactElement | null {
  if (card.applied_labels.length === 0) {
    return null;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Labels</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-wrap gap-1.5">
        {card.applied_labels.map((label) => (
          <Chip key={label.label_key} title={`applied ${label.applied_at}`}>
            {label.label}
          </Chip>
        ))}
      </CardBody>
    </Card>
  );
}

/** The changes the record has tied to this ticket, when any were recorded. */
export function Changes({ card }: { readonly card: BoardCard }): ReactElement | null {
  if (card.change_references.length === 0) {
    return null;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Changes</CardTitle>
      </CardHeader>
      <CardBody className="py-1">
        {card.change_references.map((change) => (
          <Fact key={change.change_identity} label={change.repository}>
            <Mono className="break-all">{change.reference}</Mono>
          </Fact>
        ))}
      </CardBody>
    </Card>
  );
}
