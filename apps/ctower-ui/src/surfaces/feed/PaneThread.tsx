import type { ReactElement } from "react";
import type { PaneCapture } from "@/read/interface";

/**
 * A live pane, rendered as the approved chat layout.
 *
 * The bridge hands back a terminal capture, not a typed turn stream, so the
 * grouping rule is stated rather than implied and every part of it is a shape
 * the harness actually prints:
 *
 * - a run of prose lines is one turn's bubble;
 * - a block the harness opens with `⎿` is a tool call and its output, so it
 *   collapses into the product's one chip idiom — the same `<details>` the
 *   ticket's record stream uses;
 * - the prompt rule, the status line and the box drawing are terminal chrome,
 *   not session content, and are dropped.
 *
 * None of this claims ctower recorded turns. The session header says
 * `capture, not a recorded session`, and the typed turn stream lands with G5.
 */

/* The glyphs the two harnesses in this fleet actually print. These are
   structural markers the terminal emits, not English the model chose, so the
   grouping does not depend on wording. */
const TURN_OPENER = /^[●✻✽·⏺*]/u;
const TOOL_OPENER = /^[•↳⎿]/u;
const TOOL_CONTINUATION = /^[└│]/u;
const CHROME = /^[─━]{6,}\s*$|^\s*⏵⏵|^\s*❯\s*$|^\s*←\s+for agents/u;

interface Tool {
  readonly summary: string;
  readonly output: readonly string[];
}

interface Turn {
  readonly bubble: readonly string[];
  readonly tools: readonly Tool[];
}

function indentOf(line: string): number {
  return line.length - line.trimStart().length;
}

function emptyTurn(): Turn {
  return { bubble: [], tools: [] };
}

/** Group a capture into turns and their tool blocks, by the shapes above. */
export function turnsOf(lines: readonly string[]): readonly Turn[] {
  const turns: Turn[] = [];
  let current = emptyTurn();
  let toolIndent: number | null = null;

  const close = (): void => {
    if (current.bubble.length > 0 || current.tools.length > 0) {
      turns.push(current);
    }
    current = emptyTurn();
  };

  for (const line of lines) {
    if (CHROME.test(line)) {
      continue;
    }
    if (TOOL_OPENER.test(line.trimStart())) {
      toolIndent = indentOf(line);
      const summary = line.trimStart().replace(TOOL_OPENER, "").trim();
      current = { ...current, tools: [...current.tools, { summary, output: [line] }] };
      continue;
    }
    const openTool = current.tools.at(-1);
    if (
      toolIndent !== null &&
      openTool !== undefined &&
      line.trim().length > 0 &&
      (indentOf(line) > toolIndent || TOOL_CONTINUATION.test(line.trimStart()))
    ) {
      current = {
        ...current,
        tools: [...current.tools.slice(0, -1), { ...openTool, output: [...openTool.output, line] }],
      };
      continue;
    }
    toolIndent = null;
    if (line.trim().length === 0) {
      continue;
    }
    if (
      TURN_OPENER.test(line.trimStart()) &&
      (current.bubble.length > 0 || current.tools.length > 0)
    ) {
      close();
    }
    current = { ...current, bubble: [...current.bubble, line] };
  }
  close();
  return turns;
}

function Chip({ tool }: { readonly tool: Tool }): ReactElement {
  return (
    <details className="toolchip">
      <summary>
        <span className="kind">tool</span>
        <span className="arg">{tool.summary.slice(0, 120)}</span>
      </summary>
      <div className="out">{tool.output.join("\n")}</div>
    </details>
  );
}

export function PaneThread({ capture }: { readonly capture: PaneCapture }): ReactElement {
  const turns = turnsOf(capture.lines);
  const initials = capture.harness.slice(0, 2).toUpperCase();
  return (
    <div className="chat">
      {turns.map((turn, index) => (
        <div
          className="turn"
          key={`${index.toString()}:${turn.bubble[0] ?? turn.tools[0]?.summary ?? ""}`}
        >
          <span className="who">
            <i className="av">{initials}</i>
          </span>
          <div className="e">
            <div className="hdr">
              <span className="seat">{capture.crew}</span>
              <span className="crew">{capture.session}</span>
            </div>
            {turn.bubble.length === 0 ? null : (
              <div className="bub" style={{ whiteSpace: "pre-wrap" }}>
                {turn.bubble.join("\n")}
              </div>
            )}
            {turn.tools.length === 0 ? null : (
              <div className="tools">
                {turn.tools.map((tool, position) => (
                  <Chip key={`${position.toString()}:${tool.summary}`} tool={tool} />
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
      {turns.length === 0 ? (
        <div className="turn">
          <div className="e">
            <div className="bub">
              The pane is captured and carries no content line right now — the crew is between
              turns. This is the capture, not a claim that the session is idle.
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** The same capture as the numbered monospace stream, for debugging. */
export function PaneRaw({ capture }: { readonly capture: PaneCapture }): ReactElement {
  return (
    <div className="stream">
      {capture.lines.map((line, index) => (
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
