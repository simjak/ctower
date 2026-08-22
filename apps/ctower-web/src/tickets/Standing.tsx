import type { ReactElement } from "react";
import type { BoardView } from "@ctower/client";
import { Chip } from "../ui/primitives";

/**
 * What the read itself knows, said as a chip.
 *
 * `STATE_UNKNOWN` is not `current` and never renders as one. A projection that
 * has folded everything the record holds is a proven fact about this list and
 * earns the success colour; one that is still catching up says so, and the two
 * watermarks stay in the hover because they are record positions, not a number
 * of tickets.
 */
export function Standing({ board }: { readonly board: BoardView }): ReactElement {
  const positions = `folded ${String(board.projection_watermark)} of ${String(board.source_watermark)}`;
  if (board.health !== "CURRENT") {
    return <Chip title={positions}>not known</Chip>;
  }
  return board.projection_watermark === board.source_watermark ? (
    <Chip tone="ok" title={positions}>
      current
    </Chip>
  ) : (
    <Chip tone="amber" title={positions}>
      catching up
    </Chip>
  );
}
