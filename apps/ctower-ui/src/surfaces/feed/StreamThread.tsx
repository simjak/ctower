import type { ReactElement } from "react";
import type { SessionStream } from "@/read/interface";

/**
 * A session stream in the approved chat layout.
 *
 * The component knows only that a stream is turns, each with a body, some
 * collapsed tool blocks and the source's own status lines. It does not know
 * whether a terminal capture or a recorded turn stream produced them, so
 * replacing the source needs no edit here — that was round-1 review's F4, and
 * this is the contract that answers it.
 *
 * The bubble wraps to its own width. Round-3 QA (#242) found it rendering with
 * `pre-wrap`, which preserved the terminal's ~135-column hard breaks inside a
 * 370px bubble and re-wrapped them there, so every paragraph broke mid-sentence
 * with a hanging indent. The source hands over lines the pane wrapped already
 * rejoined; a paragraph is therefore one line, and the bubble is the only thing
 * wrapping it. The raw view keeps the terminal's own shape.
 */
export function StreamThread({ stream }: { readonly stream: SessionStream }): ReactElement {
  return (
    <div className="chat">
      {stream.turns.map((turn, index) => (
        <div
          className="turn"
          key={`${index.toString()}:${turn.body[0] ?? turn.tools[0]?.summary ?? turn.notes[0] ?? ""}`}
        >
          <span className="who">
            <i className="av">SS</i>
          </span>
          <div className="e">
            <div className="hdr">
              <span className="seat">{stream.chosen}</span>
            </div>
            {turn.body.length === 0 ? null : (
              <div className="bub">
                {/* one paragraph per line the source handed over: the bubble
                    wraps them, the terminal's column does not (#242) */}
                {turn.body.map((line, position) => (
                  <p
                    key={`${position.toString()}:${line}`}
                    style={{ margin: position === 0 ? 0 : "6px 0 0" }}
                  >
                    {line}
                  </p>
                ))}
              </div>
            )}
            {turn.tools.length === 0 ? null : (
              <div className="tools">
                {turn.tools.map((tool, position) => (
                  <details className="toolchip" key={`${position.toString()}:${tool.summary}`}>
                    <summary>
                      <span className="kind">tool</span>
                      <span className="arg">{tool.summary.slice(0, 120)}</span>
                    </summary>
                    <div className="out" style={{ whiteSpace: "pre-wrap" }}>
                      {tool.output.join("\n")}
                    </div>
                  </details>
                ))}
              </div>
            )}
            {turn.notes.length === 0 ? null : (
              <div className="tools">
                {/* the spinner ticks and scheduled-wake lines, folded onto the
                    turn they interrupted instead of becoming bubbles of their
                    own — collapsed, counted, and still readable (#242) */}
                <details className="toolchip">
                  <summary>
                    <span className="kind">status</span>
                    <span className="arg">
                      {turn.notes.length} {turn.notes.length === 1 ? "line" : "lines"} from the
                      session itself
                    </span>
                  </summary>
                  <div className="out" style={{ whiteSpace: "pre-wrap" }}>
                    {turn.notes.join("\n")}
                  </div>
                </details>
              </div>
            )}
          </div>
        </div>
      ))}
      {stream.turns.length === 0 ? (
        <div className="turn">
          <div className="e">
            <div className="bub">
              The source answered and this stream carries no turn right now. That is what it
              reported, not a claim that the session is idle.
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** The same stream as its numbered raw lines, for debugging. */
export function StreamRaw({ stream }: { readonly stream: SessionStream }): ReactElement {
  return (
    <div className="stream">
      {stream.rawLines.map((line, index) => (
        <div className="fl" key={`${index.toString()}:${line}`}>
          <span className="k">{(index + 1).toString().padStart(3, "0")}</span>
          <span className="m" style={{ whiteSpace: "pre-wrap" }}>
            {line}
          </span>
        </div>
      ))}
    </div>
  );
}
