import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { KnownValue, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { clockText } from "@/read/elapsed";
import type { SessionStream } from "@/read/interface";
import { ChoiceTabs } from "@/surfaces/ChoiceTabs";
import { Composer } from "@/surfaces/feed/Composer";
import { FeedViews } from "@/surfaces/feed/FeedViews";
import { StreamRaw, StreamThread } from "@/surfaces/feed/StreamThread";
import { readParam } from "@/surfaces/screenParams";

export const dynamic = "force-dynamic";

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Live feed</h1>
    </div>
  );
}

/**
 * The session header renders the facts the source names and the fidelity it
 * claims for itself. The screen makes no claim of its own about what kind of
 * stream this is — round-1 review's F4.
 */
function StreamMeta({ stream }: { readonly stream: SessionStream }): ReactElement {
  return (
    <>
      <span className="av" style={{ width: "27px", height: "27px", fontSize: "10.5px" }}>
        SS
      </span>
      <span>
        <span className="who">{stream.chosen}</span>
      </span>
      {stream.header.map((entry) => (
        <span className="chip" key={entry.label}>
          {entry.label} <KnownValue value={entry.value} />
        </span>
      ))}
      <span className="live">
        <span className="pulse" />
        observed {clockText(stream.observedAt)}
      </span>
      {stream.wasRedacted ? (
        <span className="verdict v-changes">redacted before render</span>
      ) : null}
    </>
  );
}

function FeedBody({ stream }: { readonly stream: SessionStream }): ReactElement {
  return (
    <>
      <Chrome section="Feed" />
      <main className="page">
        <div className="wrap">
          <Lede />

          <ChoiceTabs
            label="Choose a session"
            route="/feed"
            selected={stream.chosen}
            choices={stream.choices.map((choice) => ({ key: choice, label: choice }))}
          />

          <section className="panel" style={{ marginTop: "16px" }}>
            <FeedViews
              sessionMeta={<StreamMeta stream={stream} />}
              chat={<StreamThread stream={stream} />}
              raw={<StreamRaw stream={stream} />}
            />
            <Composer />
          </section>

          <RecordFoot
            readPath={SOURCE_LABELS.feed}
            watermark={`${stream.turns.length.toString()} turns over ${stream.rawLines.length.toString()} lines · ${stream.fidelityNote}`}
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
  const stream = await recordAdapter.sessionStream(readParam(await searchParams, "seat"));
  return (
    <Resolved
      reading={stream}
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
      {(value) => <FeedBody stream={value} />}
    </Resolved>
  );
}
