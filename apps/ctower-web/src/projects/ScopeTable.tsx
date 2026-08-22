import type { ReactElement } from "react";
import type { BoardView } from "@ctower/client";
import type { Answer } from "../api/client";
import { cn } from "../ui/cn";
import { Mark } from "../ui/marks";
import { Mono } from "../ui/primitives";
import { laneCount } from "./board";
import type { ProjectScope } from "./read";

/**
 * The portfolio, one row per project.
 *
 * Two numbers come from the bundle and land with the page; three come from that
 * project's own board read and land when it lands. A row whose board has not
 * answered says which of the four things happened to it instead of showing a
 * blank where a count goes — a missing number and a zero are different facts.
 */
export function ScopeTable({
  scopes,
  boards,
  here,
  onGo,
}: {
  readonly scopes: readonly ProjectScope[];
  readonly boards: ReadonlyMap<string, Answer<BoardView>>;
  readonly here: string | null;
  readonly onGo: (key: string) => void;
}): ReactElement {
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-line text-2xs text-muted">
          <th className="py-1.5 pl-2.5 text-left font-normal">Project</th>
          <th className="py-1.5 text-right font-normal">Scoped</th>
          <th className="w-[36%] py-1.5 pl-6 text-right font-normal">On the board</th>
          <th className="py-1.5 pl-6 text-right font-normal">In progress</th>
          <th className="py-1.5 pr-2.5 pl-6 text-right font-normal">Complete</th>
        </tr>
      </thead>
      <tbody>
        {scopes.map((scope) => (
          <Row
            key={scope.key}
            scope={scope}
            board={boards.get(scope.key) ?? { kind: "asking" }}
            here={scope.key === here}
            onGo={onGo}
          />
        ))}
      </tbody>
    </table>
  );
}

function Row({
  scope,
  board,
  here,
  onGo,
}: {
  readonly scope: ProjectScope;
  readonly board: Answer<BoardView>;
  readonly here: boolean;
  readonly onGo: (key: string) => void;
}): ReactElement {
  return (
    <tr className={cn("border-b border-line text-sm", here ? "bg-amber/8" : "hover:bg-raised")}>
      <td className={cn("py-1.5 pr-3", here ? "border-l-2 border-amber pl-2" : "pl-2.5")}>
        <button
          type="button"
          aria-current={here ? "true" : undefined}
          onClick={(): void => {
            onGo(scope.key);
          }}
          className="cursor-pointer text-left font-medium text-fg"
        >
          <Mono className="text-sm">{scope.key}</Mono>
        </button>
      </td>
      <td className="py-1.5 text-right text-muted">{scope.resources.length}</td>
      <BoardCells board={board} />
    </tr>
  );
}

/** The three board numbers, or the one thing that happened instead. */
function BoardCells({ board }: { readonly board: Answer<BoardView> }): ReactElement {
  switch (board.kind) {
    case "asking":
      return <Instead mark="working" text="Reading the board" tone="text-muted" />;
    case "refused":
      return <Instead mark="dead" text={board.problem.code} tone="text-danger" mono />;
    case "unreachable":
      return <Instead mark={null} text="ctower did not answer" tone="text-muted" />;
    case "malformed":
      return <Instead mark="warn" text="Unreadable answer" tone="text-muted" />;
    case "answered":
      return (
        <>
          <td className="py-1.5 pl-6 text-right">{board.value.cards.length}</td>
          <td className="py-1.5 pl-6 text-right">{laneCount(board.value, "in_progress")}</td>
          <td className="py-1.5 pr-2.5 pl-6 text-right">{laneCount(board.value, "complete")}</td>
        </>
      );
  }
}

function Instead({
  mark,
  text,
  tone,
  mono = false,
}: {
  readonly mark: "working" | "dead" | "warn" | null;
  readonly text: string;
  readonly tone: string;
  readonly mono?: boolean;
}): ReactElement {
  return (
    <td colSpan={3} className={cn("py-1.5 pr-2.5 pl-6 text-right text-xs", tone)}>
      <span className="inline-flex items-center gap-1">
        {mark === null ? null : <Mark name={mark} />}
        {mono ? <Mono className={tone}>{text}</Mono> : text}
      </span>
    </td>
  );
}
