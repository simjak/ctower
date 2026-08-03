import type { ReactElement } from "react";
import type { SessionStream } from "@/read/interface";

/**
 * A session stream in the approved chat layout.
 *
 * The component knows only that a stream is turns, each with a body and some
 * collapsed tool blocks. It does not know whether a terminal capture or a typed
 * G5 turn stream produced them, so replacing the source needs no edit here —
 * that was round-1 review's F4, and this is the contract that answers it.
 */
export function StreamThread({ stream }: { readonly stream: SessionStream }): ReactElement {
  return (
    <div className="chat">
      {stream.turns.map((turn, index) => (
        <div
          className="turn"
          key={`${index.toString()}:${turn.body[0] ?? turn.tools[0]?.summary ?? ""}`}
        >
          <span className="who">
            <i className="av">SS</i>
          </span>
          <div className="e">
            <div className="hdr">
              <span className="seat">{stream.chosen}</span>
            </div>
            {turn.body.length === 0 ? null : (
              <div className="bub" style={{ whiteSpace: "pre-wrap" }}>
                {turn.body.join("\n")}
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
                    <div className="out">{tool.output.join("\n")}</div>
                  </details>
                ))}
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
