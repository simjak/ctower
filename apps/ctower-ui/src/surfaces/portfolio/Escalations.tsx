import Link from "next/link";
import type { ReactElement } from "react";
import { NoSourceYet, UnknownSet } from "@/frame/Declared";
import { escalationsOf } from "@/read/portfolioProjection";
import { NO_OPEN_ESCALATIONS } from "@/read/futureSources";
import { shortId } from "@/read/elapsed";
import type { Portfolio, PortfolioEscalation, UnreachedScope } from "@/read/interface";

/**
 * What is waiting on a human, across every project board that answered.
 *
 * An escalation here is not a word this screen chose: it is an attention
 * finding whose effective owner is the operator and which carries no
 * disposition — the same fact the Board card prints as human-waiting. The row
 * therefore states the finding's own kind and reason codes rather than a
 * severity this surface invented, and links to the ticket it is filed against.
 *
 * Empty is a measurement, and it is drawn as one — but only where it *is* one.
 * The panel takes the fold's own verdict rather than reading the length of the
 * list it was handed, because an empty list means two opposite things: every
 * board answered and holds no such finding, or a board never answered and this
 * page has no idea. The first is the record-holds-none block; the second names
 * the boards that were not reached and claims nothing.
 */

function Row({ escalation }: { readonly escalation: PortfolioEscalation }): ReactElement {
  return (
    <Link className="msg" href={`/ticket/${encodeURIComponent(escalation.ticketId)}`}>
      <span className="dot" />
      <div className="subj">{escalation.title}</div>
      <div className="when">{escalation.priority}</div>
      <div className="meta">
        <span className="chip">{escalation.projectKey}</span>
        <span>{escalation.kindKey}</span>
        <span>{escalation.reasonCode}</span>
        <span>lane {escalation.lane}</span>
        <span className="mono" title={`finding ${escalation.findingId}`}>
          finding {shortId(escalation.findingId)}
        </span>
        <span className="mono">ticket {shortId(escalation.ticketId)}</span>
      </div>
    </Link>
  );
}

/** The caveat under a real list that may not be the whole one. */
function Partial({ scopes }: { readonly scopes: readonly UnreachedScope[] }): ReactElement | null {
  if (scopes.length === 0) {
    return null;
  }
  return (
    <div className="src-line">
      <span>from the project boards that answered — what the rest hold was not read</span>
      {scopes.map((scope) => (
        <span key={scope.key}>
          {scope.key} not reached: {scope.reason}
        </span>
      ))}
    </div>
  );
}

export function Escalations({ portfolio }: { readonly portfolio: Portfolio }): ReactElement {
  const found = escalationsOf(portfolio);
  switch (found.known) {
    case "none":
      return <NoSourceYet brief source={NO_OPEN_ESCALATIONS} />;
    case "unknown":
      return <UnknownSet what="What is waiting on a human" scopes={found.unreached} />;
    case "open":
      return (
        <div>
          {found.escalations.map((escalation) => (
            <Row escalation={escalation} key={escalation.findingId} />
          ))}
          <Partial scopes={found.unreached} />
        </div>
      );
  }
}
