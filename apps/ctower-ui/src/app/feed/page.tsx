import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { clockText } from "@/read/elapsed";
import type { PaneCapture } from "@/read/interface";
import { Composer } from "@/surfaces/feed/Composer";
import { FeedViews } from "@/surfaces/feed/FeedViews";
import { PaneRaw, PaneThread } from "@/surfaces/feed/PaneThread";
import { ChoiceTabs } from "@/surfaces/ChoiceTabs";
import { readParam } from "@/surfaces/screenParams";

export const dynamic = "force-dynamic";

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Live feed</h1>
      <p>
        The session as a conversation: what it decided, what it ran, and every turn an operator or
        commander put into it. Tool calls collapse into the flow so the reasoning stays readable,
        and the raw terminal is one switch away when something needs debugging.
      </p>
    </div>
  );
}

function SessionMeta({ capture }: { readonly capture: PaneCapture }): ReactElement {
  return (
    <>
      <span className="av" style={{ width: "27px", height: "27px", fontSize: "10.5px" }}>
        {capture.harness.slice(0, 2).toUpperCase()}
      </span>
      <span>
        <span className="who">{capture.crew}</span> <span className="crew">{capture.session}</span>
      </span>
      <span className="chip">{capture.harness}</span>
      <span className="live">
        <span className="pulse" />
        captured {clockText(capture.capturedAt)}
      </span>
      {capture.wasRedacted ? (
        <span className="verdict v-changes">redacted before render</span>
      ) : null}
      <span className="verdict v-held">capture, not a recorded session</span>
    </>
  );
}

function FeedBody({ capture }: { readonly capture: PaneCapture }): ReactElement {
  return (
    <>
      <Chrome section="Feed" />
      <main className="page">
        <div className="wrap">
          <Lede />

          <ChoiceTabs
            label="Choose a crew"
            route="/feed"
            selected={capture.crew}
            choices={capture.crews.map((crew) => ({ key: crew, label: crew }))}
          />

          <section className="panel" style={{ marginTop: "16px" }}>
            <FeedViews
              sessionMeta={<SessionMeta capture={capture} />}
              chat={<PaneThread capture={capture} />}
              raw={<PaneRaw capture={capture} />}
            />
            <Composer />
          </section>

          <RecordFoot
            readPath={SOURCE_LABELS.feed}
            watermark={`${capture.lines.length.toString()} captured lines from ${capture.cwd} · a terminal capture, not a typed turn stream`}
          />
        </div>
      </main>
    </>
  );
}

export default async function FeedPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const capture = await recordAdapter.sessionPane(readParam(await searchParams, "seat"));
  return (
    <Resolved
      reading={capture}
      frame={(declared) => (
        <>
          <Chrome section="Feed" />
          <main className="page">
            <div className="wrap">
              <Lede />
              <section className="panel" style={{ marginTop: "16px" }}>
                <header>
                  <h2>Stream</h2>
                </header>
                {declared}
                <Composer />
              </section>
              <RecordFoot readPath={SOURCE_LABELS.feed} />
            </div>
          </main>
        </>
      )}
    >
      {(value) => <FeedBody capture={value} />}
    </Resolved>
  );
}
