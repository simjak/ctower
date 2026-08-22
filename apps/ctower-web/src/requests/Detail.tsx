import { X } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import type { RequestRow } from "@ctower/client";
import { Mark } from "../ui/marks";
import { Button, Card, CardBody, CardHeader, Chip, Mono } from "../ui/primitives";
import { age, moment, shortDigest, stateMark, triageTone } from "./facts";

/**
 * One request, in full.
 *
 * There is no read behind this panel. The contract declares no operation that
 * returns a single Request, so every value here is the row the list already
 * answered with — which is why opening one costs nothing and why nothing on
 * this panel can be fresher than the list header says it is. That absence is
 * recorded as a gap rather than filled with a second, invented call.
 *
 * The request's own words are never truncated. The copy budget governs what
 * ctower says, never what the record holds.
 */
export function Detail({
  row,
  onClose,
}: {
  readonly row: RequestRow;
  readonly onClose: () => void;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <Mono className="text-md text-fg">{row.reference}</Mono>
        <Chip tone={triageTone(row.triage)}>{row.triage.toLowerCase()}</Chip>
        <span className="flex-1" />
        <Button size="sm" variant="quiet" aria-label="Close this request" onClick={onClose}>
          <X />
        </Button>
      </CardHeader>
      <CardBody>
        {/* What was asked, then what was recorded about it. The rule between
            them is the whole distinction: above it is the operator's sentence,
            below it is the record's answer. */}
        <p className="m-0 text-sm wrap-anywhere whitespace-pre-wrap">{row.content}</p>
        <dl className="mt-4 mb-0 grid grid-cols-[78px_minmax(0,1fr)] gap-x-3 gap-y-1.5 border-t border-line pt-4 text-sm">
          <Fact label="Where">
            <Mark name={stateMark(row.state)} />
            <span>{row.state.toLowerCase()}</span>
          </Fact>
          <Fact label="Priority">
            <span>{row.priority}</span>
            {row.priority_default ? <span className="text-muted">· default</span> : null}
          </Fact>
          <Owner row={row} />
          <Fact label="Filed">
            <span>{moment(row.created_at)}</span>
            <span className="text-muted">· {age(row.age_seconds)} ago</span>
          </Fact>
          <Fact label="Project">
            <Mono>{row.project_key}</Mono>
          </Fact>
          <Fact label="From">
            <Mono className="truncate" title={row.source_ref}>
              {row.source_kind} · {row.source_ref}
            </Mono>
          </Fact>
          <Tickets row={row} />
          <Proof row={row} />
          {row.blocker === null ? null : (
            <Fact label="Blocked by">
              {/* Not the danger tone: blocked work is parked, and danger is
                  spent only on what is dead, refused or removed. */}
              <span>{row.blocker}</span>
            </Fact>
          )}
          {row.decision_brief === null ? null : (
            <Fact label="Brief">
              {/* The brief is a surface of its own. What belongs here is that
                  one exists and whether it is still asking for an answer. */}
              <Chip tone={row.decision_brief.status === "open" ? "amber" : "neutral"}>
                {row.decision_brief.status}
              </Chip>
            </Fact>
          )}
          {row.unknown_reason === null ? null : (
            <Fact label="Unknown">
              <span className="text-muted">{row.unknown_reason}</span>
            </Fact>
          )}
          <Fact label="Digest">
            <Mono className="text-muted" title={row.content_sha256}>
              {shortDigest(row.content_sha256)}
            </Mono>
          </Fact>
        </dl>
      </CardBody>
    </Card>
  );
}

function Fact({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <>
      <dt className="pt-px text-2xs text-muted">{label}</dt>
      <dd className="m-0 flex min-w-0 items-center gap-1.5">{children}</dd>
    </>
  );
}

/**
 * An imported request's owner was mapped from a name the old ledger held. The
 * digest of that original name is recorded, so the mapping is stated rather
 * than the new owner being presented as the one who always filed it.
 *
 * The contract gives `owner` a minimum length, so there is no unowned case to
 * draw — a row that arrived without one would be a malformed answer and would
 * never reach this panel.
 */
function Owner({ row }: { readonly row: RequestRow }): ReactElement {
  return (
    <Fact label="Owner">
      <span>{row.owner}</span>
      {row.original_owner_sha256 === null ? null : (
        <Mono className="text-muted" title={row.original_owner_sha256}>
          · carried over
        </Mono>
      )}
    </Fact>
  );
}

/**
 * The tickets the record mirrored this ask into. The two relation kinds stay
 * apart because their exclusivity is the record's own rule, and a request
 * mirrored into no ticket draws nothing rather than an empty count.
 */
function Tickets({ row }: { readonly row: RequestRow }): ReactElement | null {
  if (row.ticket_count === 0) {
    return null;
  }
  return (
    <Fact label="Tickets">
      <span className="min-w-0">
        {row.required_ticket_ids.length === 0
          ? null
          : `${String(row.required_ticket_ids.length)} required`}
        {row.optional_ticket_ids.length === 0 ? null : (
          <span className="text-muted">
            {row.required_ticket_ids.length === 0 ? "" : " · "}
            {String(row.optional_ticket_ids.length)} optional
          </span>
        )}
      </span>
    </Fact>
  );
}

/** `null` is "no coverage was recorded", which is not the same fact as zero. */
function Proof({ row }: { readonly row: RequestRow }): ReactElement {
  return (
    <Fact label="Proof">
      {row.proof_coverage === null ? (
        <span className="text-muted">not recorded</span>
      ) : (
        <span>{row.proof_coverage} recorded</span>
      )}
    </Fact>
  );
}
