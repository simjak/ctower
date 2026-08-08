import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { Count } from "@/surfaces/Count";
import { Escalations } from "@/surfaces/portfolio/Escalations";
import { ProjectLanes } from "@/surfaces/portfolio/ProjectLanes";
import { SeatComms } from "@/surfaces/portfolio/SeatComms";
import type { Portfolio } from "@/read/interface";

export const dynamic = "force-dynamic";

/**
 * Portfolio — the whole fleet in one read.
 *
 * The per-project board answers one project's question, and the director
 * supervises three; before this the sweep was three tabs plus a shell script
 * over git, gh and tmux. This screen asks the same record the boards ask, once
 * per configured project, and folds the answers into the three things the sweep
 * was actually looking for: where the work sits, what is waiting on a human,
 * and what mail is unread.
 *
 * Nothing on it is a number this screen chose. The lanes are the record's own,
 * the escalations are undisposed operator-owned attention findings, the unread
 * counts are the inbox projection's, and a project whose board did not answer
 * is counted out of the totals and says so on its row rather than contributing
 * a zero. The tiles below are counted from the rows beneath them, so a reader
 * can check the summary against the table without leaving the page.
 *
 * It is read-only by scope: the operator's UI-may-mutate ruling permits
 * controls, and this view carries none, because a portfolio sweep is a thing
 * you read before deciding, not a thing you act in.
 */

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Three projects, one sweep</h1>
      <p>
        Every registered project&rsquo;s tickets by lane, the escalations waiting on a human, and
        the seat comms this surface&rsquo;s principal has unread — folded from one board read per
        project and one inbox read, at the moment this page rendered. A project appears here when
        its scope registers; nothing on this page is entered by hand.
      </p>
    </div>
  );
}

function Tiles({ portfolio }: { readonly portfolio: Portfolio }): ReactElement {
  const comms = portfolio.comms;
  return (
    <div className="totals">
      <div className="tgrid">
        <div>
          <div className="k">Boards answered</div>
          <div className="v">
            {portfolio.answered}
            <small> of {portfolio.considered}</small>
          </div>
        </div>
        <div>
          <div className="k">Tickets</div>
          <div className="v">{portfolio.tickets}</div>
        </div>
        <div>
          <div className="k">Open escalations</div>
          <div className="v">{portfolio.escalations.length}</div>
        </div>
        <div>
          <div className="k">Unread comms</div>
          {/* a dash, not a zero, for both of the two ways this tile has no
              number: the read did not answer, or it answered for a principal no
              thread can be addressed to. A `0` would read as quiet seats in
              both cases. The panel below says which one it is. */}
          <div className="v">
            {comms.known === "value" && comms.value.addressable ? comms.value.totalUnread : "—"}
          </div>
        </div>
      </div>
    </div>
  );
}

function LaneSource({ portfolio }: { readonly portfolio: Portfolio }): ReactElement {
  return (
    <div className="src-line">
      <span>
        columns are the record&rsquo;s own lanes: the instance runs a four-stage workflow and{" "}
        <span className="mono">lane</span> is the fact every card carries
      </span>
      <span>
        {portfolio.staged} of {portfolio.tickets} counted cards carry a recorded workflow stage
      </span>
      <span>
        totals count the {portfolio.answered} of {portfolio.considered} project boards that answered
      </span>
      {portfolio.reason === null ? null : <span>first board failure: {portfolio.reason}</span>}
    </div>
  );
}

/**
 * How the unread mail was split, and the rule that split it.
 *
 * Nothing is rendered for a principal the projection cannot address: a row of
 * per-project zeroes under a paragraph explaining that no thread can arrive
 * here would put the misreading back that the tile above just removed.
 */
function CommsSource({ portfolio }: { readonly portfolio: Portfolio }): ReactElement | null {
  const comms = portfolio.comms;
  if (comms.known === "value" && !comms.value.addressable) {
    return null;
  }
  return (
    <div className="src-line">
      {portfolio.projects.map((project) => (
        <span key={project.key}>
          {project.key}{" "}
          {project.unread.known === "value" ? (
            <Count
              value={project.unread.value}
              unit="unread"
              detail={`unread messages on threads ${project.key}'s board cards link`}
            />
          ) : (
            "not counted"
          )}
        </span>
      ))}
      {comms.known === "value" ? (
        <span>
          {comms.value.unlinkedUnread} of {comms.value.totalUnread} on threads no card links
        </span>
      ) : null}
      <span>
        a thread belongs to a project only where that project&rsquo;s board card names it; mail on
        threads no card links is counted apart, never spread across projects
      </span>
    </div>
  );
}

function PortfolioBody({ portfolio }: { readonly portfolio: Portfolio }): ReactElement {
  return (
    <>
      <Chrome section="Portfolio" />
      <main className="page">
        <div className="wrap">
          <Lede />

          <section className="panel" style={{ marginTop: "18px" }}>
            <header>
              <h2>Portfolio right now</h2>
              <span className="sub">counted from the rows below, not reported</span>
            </header>
            <Tiles portfolio={portfolio} />
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Projects &times; lanes</h2>
              <span className="sub">tickets per lane, per project</span>
            </header>
            <ProjectLanes portfolio={portfolio} />
            <LaneSource portfolio={portfolio} />
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Open escalations</h2>
              <span className="sub">
                <Count
                  value={portfolio.escalations.length}
                  unit="waiting on a human"
                  detail="undisposed attention findings whose effective owner is the operator, across the boards that answered"
                />
              </span>
            </header>
            <Escalations portfolio={portfolio} />
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Unread seat comms</h2>
              <span className="sub">durable threads addressed to this principal</span>
            </header>
            <SeatComms comms={portfolio.comms} />
            <CommsSource portfolio={portfolio} />
          </section>

          <RecordFoot
            readPath={SOURCE_LABELS.portfolio}
            watermark={`${portfolio.answered.toString()} of ${portfolio.considered.toString()} project boards answered · observed ${portfolio.observedAt}`}
          />
        </div>
      </main>
    </>
  );
}

function PortfolioFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
  return (
    <>
      <Chrome section="Portfolio" />
      <main className="page">
        <div className="wrap">
          <Lede />
          <section className="panel" style={{ marginTop: "18px" }}>
            <header>
              <h2>Projects &times; lanes</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath={SOURCE_LABELS.portfolio} />
        </div>
      </main>
    </>
  );
}

export default async function PortfolioPage(): Promise<ReactNode> {
  const portfolio = await recordAdapter.portfolio();
  return (
    <Resolved
      reading={portfolio}
      subject="the configured projects"
      frame={(declared) => <PortfolioFrame declared={declared} />}
    >
      {(value) => <PortfolioBody portfolio={value} />}
    </Resolved>
  );
}
