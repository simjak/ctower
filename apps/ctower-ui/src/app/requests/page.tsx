import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { spanText } from "@/read/elapsed";
import { configuredProjects } from "@/read/projects";
import type { RequestEntry, RequestsSnapshot } from "@/read/interface";
import { ChoiceTabs } from "@/surfaces/ChoiceTabs";
import { readParam } from "@/surfaces/screenParams";

export const dynamic = "force-dynamic";

const ALL_PROJECTS = "all";

function projectFor(value: string | null): string | null {
  if (value === null || value === ALL_PROJECTS) {
    return null;
  }
  return configuredProjects().some((project) => project.key === value) ? value : null;
}

function requestGlyph(state: RequestEntry["state"]): "done" | "open" | "flight" | "held" {
  switch (state) {
    case "DONE":
      return "done";
    case "BLOCKED":
      return "held";
    case "WIP":
      return "flight";
    case "NEW":
    case "TRIAGED":
      return "open";
  }
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
          <span className="v">{request.createdAt}</span>
        </li>
        <li>
          <span className="k">triage</span>
          <span className="v">{request.triage}</span>
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
  const priorityClass = request.priorityDefault ? "pri dflt" : "pri";
  return (
    <article className="request-row">
      <div className="request-rank" aria-label={`record order ${rank.toString()}`}>
        {rank.toString()}
      </div>
      <div className="request-body">
        <div className="request-head">
          <span className="request-reference">{request.reference}</span>
          <StateGlyph name={requestGlyph(request.state)} />
          <span className="request-state">{request.state.toLowerCase()}</span>
          <span className={priorityClass}>{request.priority}</span>
          <span className="request-owner" title={`owner principal ${request.ownerId}`}>
            {owner}
          </span>
          <span className="request-project">{request.projectKey}</span>
          <span className="request-age">
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
        <span>Request rows are unknown until every requested project answers</span>
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

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Record order</h2>
              <span className="sub">accepted Requests · order is not a client sort</span>
            </header>
            <div className="request-order-note">
              <span>Rows below keep the order the Request read returned.</span>
              <span className="verdict v-held">read-only</span>
              <span className="mono">re-ranking is not yet available</span>
            </div>
          </section>

          <UnknownProjects projects={snapshot.unansweredProjects} />

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Requests</h2>
              <span className="sub">id · text · state · owner · project · age</span>
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
