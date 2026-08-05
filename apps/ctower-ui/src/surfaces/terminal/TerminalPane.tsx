import type { ReactElement } from "react";
import { StateGlyph } from "@/frame/StateGlyph";
import { clockText, stampText } from "@/read/elapsed";
import type { SessionStream } from "@/read/interface";

/**
 * The crew's real tmux pane, read-only.
 *
 * Source-neutral like `StreamThread`/`StreamRaw`: this renders whatever
 * `sessionStream` handed over — `rawLines`, the fidelity note, whether a
 * credential shape was redacted out of it — and knows nothing about tmux
 * itself. The pane keeps one fixed dark palette in both app themes; that
 * choice and why live beside the CSS in `design-reference/app.css`.
 *
 * A relative "updated Ns ago" caption goes stale the moment it is painted:
 * nothing here re-ticks on the client, so this states the absolute captured
 * time instead (the same choice `feed`'s `StreamMeta` already made) and lets
 * the poll that re-renders this pane be the liveness signal. That is a
 * disclosed deviation from the approved mockup's relative phrasing.
 */

interface TerminalIdentity {
  /** The crew name as it renders elsewhere on this surface — already redacted. */
  readonly crew: string;
  readonly seatInitials: string;
}

function Avatar({ initials }: { readonly initials: string }): ReactElement {
  return <i className="av">{initials}</i>;
}

export function LiveTerminalPane({
  identity,
  stream,
}: {
  readonly identity: TerminalIdentity;
  readonly stream: SessionStream;
}): ReactElement {
  return (
    <div className="term-frame">
      <header>
        <span className="term-who">
          <Avatar initials={identity.seatInitials} />
          <b>{identity.crew}</b>
        </span>
        <span className="live">
          <span className="pulse" />
          capturing pane · captured {clockText(stream.observedAt)}
        </span>
        <span className="term-ro">read-only</span>
      </header>
      <pre className="term-body">{stream.rawLines.join("\n")}</pre>
      <footer>
        <span>
          src: <span className="mono">live tmux pane, capture-pane -p</span> — captured{" "}
          {stampText(stream.observedAt)}
        </span>
        <span>{stream.fidelityNote}</span>
        {stream.wasRedacted ? <span>redacted before render</span> : null}
      </footer>
    </div>
  );
}

export function IdleTerminalPane({
  identity,
  headline = "No live tmux session — crew idle",
  detail,
  sourceLine,
  chip = "closed",
}: {
  readonly identity: TerminalIdentity;
  readonly headline?: string;
  readonly detail: string;
  readonly sourceLine: string;
  readonly chip?: string;
}): ReactElement {
  return (
    <div className="term-frame">
      <header>
        <span className="term-who">
          <Avatar initials={identity.seatInitials} />
          <b>{identity.crew}</b>
        </span>
        <span className="chip">{chip}</span>
      </header>
      <div className="term-empty">
        <StateGlyph name="parked" />
        <b>{headline}</b>
        <span className="d">{detail}</span>
      </div>
      <footer>
        <span>src: {sourceLine}</span>
      </footer>
    </div>
  );
}
