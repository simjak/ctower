import Link from "next/link";
import type { ReactElement } from "react";
import { NoSourceYet } from "@/frame/Declared";
import { NO_OPEN_ESCALATIONS } from "@/read/futureSources";
import { shortId } from "@/read/elapsed";
import type { Portfolio, PortfolioEscalation } from "@/read/interface";

/**
 * What is waiting on a human, across every project board that answered.
 *
 * An escalation here is not a word this screen chose: it is an attention
 * finding whose effective owner is the operator and which carries no
 * disposition — the same fact the Board card prints as human-waiting. The row
 * therefore states the finding's own kind and reason codes rather than a
 * severity this surface invented, and links to the ticket it is filed against.
 *
 * Empty is a measurement, and it is drawn as one. Boards that answered and hold
 * no such finding render the record-holds-none block from the reviewed
 * declared-source table, not an empty list — an empty list reads the same
 * whether the record was consulted or not.
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

export function Escalations({ portfolio }: { readonly portfolio: Portfolio }): ReactElement {
  if (portfolio.escalations.length === 0) {
    return <NoSourceYet brief source={NO_OPEN_ESCALATIONS} />;
  }
  return (
    <div>
      {portfolio.escalations.map((escalation) => (
        <Row escalation={escalation} key={escalation.findingId} />
      ))}
    </div>
  );
}
