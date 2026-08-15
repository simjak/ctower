import type { ReactElement, ReactNode } from "react";
import { Resolved } from "@/frame/Declared";
import { recordAdapter } from "@/read/adapter";
import { clockText } from "@/read/elapsed";
import { NothingGlyph } from "./glyphs";
import type { SessionStream } from "@/read/interface";

/**
 * The live session under the work pane.
 *
 * Conductor keeps a Run/Terminal pane at the foot of its right column, so the
 * operator can watch what the session is doing without leaving the transcript.
 * ctower's equivalent is the correspondent's own pane, read through the same
 * capture bridge the Feed and the crew profile already use — a read, never a
 * write, and the pane says so on itself.
 *
 * The seat this shows is the *other* participant: the operator is reading their
 * own conversation and wants the other end of it. A conversation whose other
 * participant runs no session gets a glyph and four words rather than a shell
 * that reads like a session with nothing in it.
 */

function Body({ stream }: { readonly stream: SessionStream }): ReactElement {
  return (
    <>
      <div className="cw-head">
        <h2>Terminal</h2>
        <span className="cw-art">{stream.chosen}</span>
        <span className="grow" />
        <span className="cw-as" title={stream.fidelityNote}>
          {clockText(stream.observedAt)}
        </span>
        {stream.wasRedacted ? <span className="verdict v-changes">redacted</span> : null}
      </div>
      <div className="cw-scrollable">
        <pre className="term-body" style={{ borderRadius: 0, border: 0 }}>
          {stream.rawLines.join("\n")}
        </pre>
      </div>
    </>
  );
}

function NoPane({ subject }: { readonly subject: string }): ReactElement {
  return (
    <div className="cw-nil">
      <NothingGlyph />
      <span>no live session for {subject}</span>
    </div>
  );
}

export async function SessionPane({
  subject,
}: {
  /** The seat whose pane this is: the other end of the conversation. */
  readonly subject: string;
}): Promise<ReactNode> {
  const stream = await recordAdapter.sessionStream(subject);
  return (
    <div className="cw-run">
      <Resolved
        brief
        frame={(declared) => (
          <>
            <div className="cw-head">
              <h2>Terminal</h2>
              <span className="cw-art">{subject}</span>
            </div>
            <div className="cw-scrollable">{declared}</div>
          </>
        )}
        reading={stream}
        subject={`the pane for ${subject}`}
      >
        {(value) =>
          // the bridge answers with whichever session it resolved; a pane that
          // is not this seat's would put another crew's screen on this
          // conversation, so a mismatch is treated exactly like no pane at all
          value.chosen === subject ? <Body stream={value} /> : <NoPane subject={subject} />
        }
      </Resolved>
    </div>
  );
}
