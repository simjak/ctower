import { useState } from "react";
import type { ReactElement } from "react";
import { AgentsRail } from "../../agents/AgentsRail";
import { Shell } from "../../shell/Shell";
import { ProjectSwitcher } from "../../shell/ProjectSwitcher";
import type { ProjectChoice } from "../../shell/ProjectSwitcher";
import { Button, Chip, Input } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import { cn } from "../../ui/cn";
import { ViewToggle } from "../../tickets/ViewToggle";
import { standingWords } from "../../tickets/standing";
import { PAYROLL } from "../stories";
import { LADDER, NOW, ROWS, THIN_ROWS, statusOf } from "./board";
import type { Standing } from "./board";
import { ParityBoard } from "./ParityBoard";
import type { Draw } from "./ParityBoard";

/**
 * The bench for T-CTW-035: the operator's command-line board, drawn in the
 * console, on the bones of the Board the operator froze on T-028.
 *
 * Nothing is wired. Every row is a fixture typed as the contract's own
 * `BoardCard`, no read runs, `vite build` never sees this page and no
 * destination points at it — so the four frames can be judged side by side in
 * both themes, including the two states a live tower will not produce on
 * demand.
 *
 * The shell around them is the app's own: the same rail, the same company
 * switcher, the same project dropdown and the same staff section, so a
 * judgement made about a mock here holds for the screen.
 */
/** The four frames, each shot at `gallery.html?bench=t035&frame=…`. */
export type Frame = "today" | "attributed" | "reference" | "thin";

const ACME: ProjectChoice[] = [
  { key: "ctower", name: "Ctower control plane", prefix: "CTW" },
  { key: "bh-loop", name: "BH.Loop delivery", prefix: "BHL" },
  { key: "manibo", name: "Manibo", prefix: "MNB" },
];

export function Bench({ frame }: { readonly frame: Frame }): ReactElement {
  const rows = frame === "thin" ? THIN_ROWS : ROWS;
  const draw: Draw =
    frame === "reference" ? "reference" : frame === "attributed" ? "attributed" : "today";
  const [live, setLive] = useState(true);
  const [narrowed, setNarrowed] = useState<"all" | "atwork">("all");
  const kept = narrowed === "all" ? rows : rows.filter((row) => row.session !== null);
  return (
    <Shell
      here="board"
      lockReason={null}
      onGo={(): void => undefined}
      org={{ name: "Jakit Labs", key: "jakit" }}
      project={
        <ProjectSwitcher
          projects={ACME}
          current={ACME[0] ?? null}
          onChoose={(): void => undefined}
          onAdd={(): void => undefined}
        />
      }
      agents={
        <AgentsRail
          agents={PAYROLL.slice(0, 5)}
          here={false}
          current={null}
          onOpen={(): void => undefined}
          onSeeAll={(): void => undefined}
        />
      }
    >
      <Head rows={rows} live={live} />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Narrow narrowed={narrowed} onNarrow={setNarrowed} crews={draw !== "today"} />
        <Input
          value=""
          readOnly
          placeholder="Search these tickets"
          aria-label="Search these tickets"
          className="h-7 w-52 text-xs"
          onChange={(): void => undefined}
        />
        <span className="flex-1" />
        <Live live={live} onLive={setLive} />
        <ViewToggle shape="board" onShape={(): void => undefined} />
      </div>

      <ParityBoard
        rows={kept}
        ladder={LADDER}
        draw={draw}
        now={NOW}
        onOpen={(): void => undefined}
      />

      {frame === "thin" ? (
        <p className="mt-4 mb-0 max-w-[80ch] text-2xs text-muted">
          Three tickets carry no times: the project&rsquo;s feed is walked to a cap and their
          raising was further back than the walk reached. An unread fact is drawn as unread rather
          than as a fresh one.
        </p>
      ) : null}
    </Shell>
  );
}

/**
 * Whose board this is and how the factory stands, in the one line his terminal
 * prints above the belt.
 *
 * The counts are the board's own — open, needing a person, stuck — plus the two
 * this screen adds because they are what a factory reading is for: how much is
 * moving, and how much has stopped without saying why.
 */
function Head({
  rows,
  live,
}: {
  readonly rows: readonly Standing[];
  readonly live: boolean;
}): ReactElement {
  const working = rows.filter((row) => statusOf(row, NOW) === "working").length;
  const stalled = rows.filter((row) => statusOf(row, NOW) === "stalled").length;
  return (
    <header className="mb-4 flex flex-wrap items-center gap-3">
      <h1 className="m-0 min-w-0 truncate text-xl leading-tight font-bold tracking-[-0.02em]">
        Ctower control plane
      </h1>
      <Chip>CTW</Chip>
      <span className="text-sm text-muted">
        {standingWords(rows.map((row) => row.card))} · {working} at work
      </span>
      {stalled === 0 ? null : (
        <span className="inline-flex items-center text-sm text-amber-ink">
          <Mark name="warn" />
          {stalled} stalled
        </span>
      )}
      {live ? <span className="text-2xs text-muted">Read a moment ago</span> : null}
    </header>
  );
}

/**
 * Which tickets are on the board.
 *
 * His board takes `--active` for everything that has started and `--crew` for
 * one crew's work. The first is a fact the record answers today. The second is
 * the same gap the crew column is: a filter needs the name it filters on, so it
 * arrives with the join and not before — drawn here inert, one control among
 * live ones, which is exactly the case `DESIGN.md` keeps inert for.
 */
function Narrow({
  narrowed,
  onNarrow,
  crews,
}: {
  readonly narrowed: "all" | "atwork";
  readonly onNarrow: (narrowed: "all" | "atwork") => void;
  readonly crews: boolean;
}): ReactElement {
  return (
    <div
      role="group"
      aria-label="Which tickets"
      className="inline-flex gap-0.5 rounded-md bg-raised p-0.5"
    >
      <Pick
        here={narrowed === "all"}
        label="Everything"
        onPick={(): void => {
          onNarrow("all");
        }}
      />
      <Pick
        here={narrowed === "atwork"}
        label="At work"
        onPick={(): void => {
          onNarrow("atwork");
        }}
      />
      {crews ? (
        <Pick here={false} label="By crew" onPick={(): void => undefined} />
      ) : (
        <span
          aria-disabled
          tabIndex={0}
          title="A run cannot name the crew that ran it yet."
          className="inline-flex h-6 cursor-default items-center rounded-sm border border-dashed border-line px-2.5 text-xs text-muted opacity-60"
        >
          By crew
        </span>
      )}
    </div>
  );
}

function Pick({
  here,
  label,
  onPick,
}: {
  readonly here: boolean;
  readonly label: string;
  readonly onPick: () => void;
}): ReactElement {
  return (
    <Button
      variant="quiet"
      size="sm"
      aria-pressed={here}
      onClick={onPick}
      className={cn("h-6 font-medium", here && "bg-card text-fg")}
    >
      {label}
    </Button>
  );
}

/**
 * The heartbeat.
 *
 * `DESIGN.md` reserves motion for real work moving, and a board that re-reads
 * itself every two seconds is exactly that — so this is the one screen in the
 * console that is allowed not to be still, and it says when it is. Turned off,
 * the board holds the answer it has and stops asking.
 */
function Live({
  live,
  onLive,
}: {
  readonly live: boolean;
  readonly onLive: (live: boolean) => void;
}): ReactElement {
  return (
    <Button
      variant="quiet"
      size="sm"
      aria-pressed={live}
      onClick={(): void => {
        onLive(!live);
      }}
      className={cn("h-7 font-medium", live && "text-fg")}
    >
      {live ? <Mark name="working" /> : <Mark name="idle" />}
      Live
    </Button>
  );
}

/** The bench's own frame chooser, for anyone opening it by hand. */
export function frameFrom(search: string): Frame {
  const asked = new URLSearchParams(search).get("frame");
  const known: readonly Frame[] = ["today", "attributed", "reference", "thin"];
  return known.find((frame) => frame === asked) ?? "today";
}
