import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { StateGlyph } from "@/frame/StateGlyph";
import type { GlyphName } from "@/frame/StateGlyph";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { shortId, spanText, stampText } from "@/read/elapsed";
import { configuredProjects } from "@/read/projects";
import type { RequestEntry, RequestsSnapshot } from "@/read/interface";
import { ChoiceTabs } from "@/surfaces/ChoiceTabs";
import { readParam } from "@/surfaces/screenParams";

export const dynamic = "force-dynamic";

const ALL_PROJECTS = "all";

/**
 * The two axes the record keeps for a Request, drawn as two chips.
 *
 * `state` is where the work is; `triage` is what was decided about the ask.
 * They are separate columns because they are separate facts — a `TRIAGED` row
 * that is a `DUPLICATE` and a `TRIAGED` row that was `ACCEPTED` are opposite
 * instructions to an operator, and the previous screen drew them identically.
 *
 * The glyph is the same vocabulary `ctowerctl` prints; the tone is the manibo
 * verdict map the rest of this surface already uses. `UNTRIAGED` is the one
 * value drawn in the warn tone, because it is the only one that is asking the
 * reader for something.
 */
const STATE_MARK: Readonly<Record<RequestEntry["state"], { glyph: GlyphName; tone: string }>> = {
  NEW: { glyph: "open", tone: "v-filed" },
  TRIAGED: { glyph: "open", tone: "v-filed" },
  WIP: { glyph: "flight", tone: "v-flight" },
  BLOCKED: { glyph: "held", tone: "v-held" },
  DONE: { glyph: "done", tone: "v-pass" },
};

const TRIAGE_TONE: Readonly<Record<RequestEntry["triage"], string>> = {
  UNTRIAGED: "v-changes",
  ACCEPTED: "v-filed",
  DUPLICATE: "v-filed",
  REJECTED: "v-held",
};

function projectFor(value: string | null): string | null {
  if (value === null || value === ALL_PROJECTS) {
    return null;
  }
  return configuredProjects().some((project) => project.key === value) ? value : null;
}

function StateChip({ state }: { readonly state: RequestEntry["state"] }): ReactElement {
  const mark = STATE_MARK[state];
  return (
    <span className={`verdict ${mark.tone} request-state`}>
      <StateGlyph name={mark.glyph} />
      {state.toLowerCase()}
    </span>
  );
}

function TriageChip({ triage }: { readonly triage: RequestEntry["triage"] }): ReactElement {
  return (
    <span className={`verdict ${TRIAGE_TONE[triage]} request-triage`} title="triage disposition">
      {triage.toLowerCase()}
    </span>
  );
}

function PriorityChip({ request }: { readonly request: RequestEntry }): ReactElement {
  const tone = `pri ${request.priority.toLowerCase()}`;
  if (!request.priorityDefault) {
    return <span className={tone}>{request.priority}</span>;
  }
  return (
    <span className={`${tone} dflt`} title="the record's default; nobody set this priority">
      {request.priority}
    </span>
  );
}

function ProjectMark({ projectKey }: { readonly projectKey: string }): ReactElement {
  const configured = configuredProjects().find((project) => project.key === projectKey);
  const mark = configured === undefined ? "chip proj" : `chip proj ${configured.scopeToken}`;
  return <span className={mark}>{projectKey}</span>;
}

/**
 * The tickets a Request was mirrored into, linked where the record serves one.
 *
 * `required` and `optional` are the record's own two relation kinds and stay
 * apart: exclusivity between them is an acceptance criterion, so collapsing
 * them into one "tickets" count would render a fact the record refuses to hold.
 * A row whose arrays are both empty draws nothing — the record answered, and
 * what it answered is that this ask has produced no ticket yet.
 */
function TicketLinks({ request }: { readonly request: RequestEntry }): ReactElement | null {
  const links = [
    ...request.requiredTicketIds.map((ticketId) => ({ ticketId, kind: "ticket" })),
    ...request.optionalTicketIds.map((ticketId) => ({ ticketId, kind: "optional" })),
  ];
  if (links.length === 0) {
    return null;
  }
  const scope = `?project=${encodeURIComponent(request.projectKey)}`;
  return (
    <>
      {links.map((link) => (
        <Link
          className="chip request-ticket"
          href={`/ticket/${encodeURIComponent(link.ticketId)}${scope}`}
          key={link.ticketId}
          title={`${link.kind === "ticket" ? "required" : "optional"} ticket ${link.ticketId}`}
        >
          {link.kind} {shortId(link.ticketId)}
        </Link>
      ))}
    </>
  );
}

function RequestFacts({ request }: { readonly request: RequestEntry }): ReactElement {
  return (
    <details className="request-details">
      <summary>record facts</summary>
      <ul className="kv">
        <li>
          <span className="k">request id</span>
          <span className="v mono">{request.requestId}</span>
        </li>
        <li>
          <span className="k">captured</span>
          <span className="v">{stampText(request.createdAt)}</span>
        </li>
        <li>
          <span className="k">source</span>
          <span className="v mono">
            {request.sourceKind} · {request.sourceRef}
          </span>
        </li>
        <li>
          <span className="k">proof</span>
          {/* a proof count the record did not answer is unknown, never zero */}
          <span className="v mono">
            {request.proofCoverage === null ? "unknown" : request.proofCoverage.toString()}
          </span>
        </li>
        <li>
          <span className="k">freshness</span>
          <span className="v mono">record {request.freshness.toString()}</span>
        </li>
        <li>
          <span className="k">content digest</span>
          <span className="v mono">{request.contentSha256}</span>
        </li>
      </ul>
    </details>
  );
}

function RequestRow({
  request,
  rank,
}: {
  readonly request: RequestEntry;
  readonly rank: number;
}): ReactElement {
  const owner = request.owner.trim() === "" ? "unowned" : request.owner;
  return (
    <article className="request-row">
      <div className="request-rank" aria-label={`record order ${rank.toString()}`}>
        {rank.toString()}
      </div>
      <div className="request-body">
        <div className="request-head">
          <span className="request-reference">{request.reference}</span>
          <StateChip state={request.state} />
          <TriageChip triage={request.triage} />
          <PriorityChip request={request} />
          <span className="request-age" title={`captured ${stampText(request.createdAt)}`}>
            age {spanText(Math.max(0, request.ageSeconds) * 1000)}
          </span>
        </div>
        <p className="request-content">{request.content}</p>
        {request.blocker === null ? null : (
          <div className="request-blocker">blocked · {request.blocker}</div>
        )}
        {request.unknownReason === null ? null : (
          <div className="request-blocker">unknown · {request.unknownReason}</div>
        )}
        <div className="request-foot">
          <span className="request-owner" title={`owner principal ${request.ownerId}`}>
            {owner}
          </span>
          <ProjectMark projectKey={request.projectKey} />
          <TicketLinks request={request} />
        </div>
        <RequestFacts request={request} />
      </div>
    </article>
  );
}

function UnknownProjects({
  projects,
}: {
  readonly projects: readonly string[];
}): ReactElement | null {
  if (projects.length === 0) {
    return null;
  }
  return (
    <section className="panel request-unknown" aria-label="Unknown request sources">
      <div className="request-unknown-line">
        <StateGlyph name="attn" />
        <strong>unknown</strong>
        <span>the Request read did not answer for {projects.join(", ")}</span>
      </div>
    </section>
  );
}

function RequestQueue({ snapshot }: { readonly snapshot: RequestsSnapshot }): ReactElement {
  if (snapshot.rows.length === 0) {
    return snapshot.unansweredProjects.length === 0 ? (
      <div className="request-empty">
        <StateGlyph name="open" />
        <span>the record holds no Requests for this scope</span>
      </div>
    ) : (
      <div className="request-empty">
        <StateGlyph name="attn" />
        <span>unknown until every requested project answers</span>
      </div>
    );
  }
  return (
    <div className="request-queue">
      {snapshot.rows.map((request, index) => (
        <RequestRow key={request.requestId} rank={index + 1} request={request} />
      ))}
    </div>
  );
}

function RequestsBody({
  snapshot,
  project,
}: {
  readonly snapshot: RequestsSnapshot;
  readonly project: string | null;
}): ReactElement {
  const choices = [
    { key: ALL_PROJECTS, label: "all projects" },
    ...configuredProjects().map((item) => ({ key: item.key, label: item.key })),
  ];
  const path = project === null ? "/v1/requests" : `/v1/requests?project_key=${project}`;
  return (
    <>
      <Chrome
        section="Requests"
        headerExtra={
          <ChoiceTabs
            choices={choices}
            label="Choose a Request project"
            parameter="project"
            route="/requests"
            selected={project ?? ALL_PROJECTS}
          />
        }
      />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Requests</h1>
          </div>

          <UnknownProjects projects={snapshot.unansweredProjects} />

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Requests</h2>
              {/* the record's order is the ledger's order, and the one thing
                  this screen cannot do is said where the control would be */}
              <span className="sub request-order">
                <span className="verdict v-held">read-only</span>
                record order · re-ranking is not yet available
              </span>
            </header>
            <RequestQueue snapshot={snapshot} />
          </section>

          <RecordFoot
            readPath={path}
            watermark={`record watermark ${snapshot.watermark.toString()} · ${snapshot.answeredProjectCount.toString()} of ${snapshot.requestedProjectCount.toString()} project reads answered`}
          />
        </div>
      </main>
    </>
  );
}

export default async function RequestsPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const project = projectFor(readParam(await searchParams, "project"));
  const requests = await recordAdapter.requests(project);
  return (
    <Resolved
      reading={requests}
      frame={(declared) => (
        <>
          <Chrome section="Requests" />
          <main className="page">
            <div className="wrap">
              <div className="lede">
                <h1>Requests</h1>
              </div>
              <section className="panel" style={{ marginTop: "16px" }}>
                <header>
                  <h2>Request read</h2>
                </header>
                {declared}
              </section>
              <RecordFoot readPath={SOURCE_LABELS.requests} />
            </div>
          </main>
        </>
      )}
    >
      {(snapshot) => <RequestsBody project={project} snapshot={snapshot} />}
    </Resolved>
  );
}
