import type { BoardCard, BoardView } from "@ctower/client";

/**
 * What the board's own head says about the project, and what it refuses to say.
 *
 * One line, three facts, and every one of them is counted from the cards the
 * read answered with: how much is open, how much is waiting on a person, how
 * much is stuck. A zero is not a fact worth a phrase — "0 stuck" is noise on a
 * board with nothing stuck — so a term that counts nothing is left out and the
 * open count, which is the board's own size, always stays.
 */
export function standingWords(cards: readonly BoardCard[]): string {
  const open = cards.filter((card) => card.lane !== "complete").length;
  const waiting = cards.filter((card) => card.human_waiting.state === "waiting").length;
  const stuck = cards.filter((card) => card.lane === "blocked").length;
  const said = [`${String(open)} open`];
  if (waiting > 0) {
    said.push(`${String(waiting)} need you`);
  }
  if (stuck > 0) {
    said.push(`${String(stuck)} stuck`);
  }
  return said.join(" · ");
}

/**
 * Whether this count is the whole truth yet, in the words a person would use.
 *
 * A board is a projection, and a projection folds after the command it
 * describes is durable. So a read that has not caught up is not a board with
 * fewer tickets on it — it is a board that has not finished being written, and
 * presenting its count as complete is the one lie this screen could tell
 * without printing a single wrong number.
 *
 * The two watermarks behind that judgement are record positions rather than
 * numbers of tickets, so neither is drawn: an operator who read "folded to 41
 * of 44" would reasonably conclude three tickets are missing, which is not what
 * it says. `STATE_UNKNOWN` is not "up to date" and is never quietly drawn as
 * one; it gets its own sentence, because "it did not say" and "it said yes"
 * are different answers.
 */
export function catchingUpWords(view: BoardView): string | null {
  if (view.health === "STATE_UNKNOWN") {
    return "This board could not say whether it is up to date.";
  }
  return view.projection_watermark < view.source_watermark
    ? "Still catching up, so a ticket raised a moment ago may not be here yet."
    : null;
}
