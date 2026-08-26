import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { Button } from "../ui/primitives";

/**
 * The two shapes one project's tickets are read in.
 *
 * A list is the thing you walk down and a board is the thing you scan, and both
 * are the same `getBoard` answer — so this is a switch between two shapes of one
 * read rather than two destinations that ask the record separately.
 */
export type TicketShape = "list" | "board";

/**
 * The switch, drawn as one segmented control rather than as two loose buttons.
 *
 * Two buttons would say two acts. A segment says one control with two
 * positions, which is what this is, and it is the same control on both screens
 * so the operator never has to learn a second way back.
 *
 * Choosing a shape moves the rail. `Board` is a destination of its own and the
 * rail carries a row for it, so a toggle that changed the shape while leaving
 * the rail on `Tickets` would leave the two disagreeing about where the
 * operator is — and the address, which is what a screenshot and a shared link
 * are made of, would describe the screen nobody is looking at.
 */
export function ViewToggle({
  shape,
  onShape,
}: {
  readonly shape: TicketShape;
  readonly onShape: (shape: TicketShape) => void;
}): ReactElement {
  return (
    <div
      role="group"
      aria-label="How these tickets are shown"
      className="inline-flex gap-0.5 rounded-md bg-raised p-0.5"
    >
      <Shape here={shape === "list"} label="List" onChoose={onShape} />
      <Shape here={shape === "board"} label="Board" onChoose={onShape} />
    </div>
  );
}

function Shape({
  here,
  label,
  onChoose,
}: {
  readonly here: boolean;
  readonly label: "List" | "Board";
  readonly onChoose: (shape: TicketShape) => void;
}): ReactElement {
  return (
    <Button
      variant="quiet"
      size="sm"
      aria-pressed={here}
      onClick={(): void => {
        onChoose(label === "Board" ? "board" : "list");
      }}
      className={cn("h-6 font-medium", here && "bg-card text-fg")}
    >
      {label}
    </Button>
  );
}
