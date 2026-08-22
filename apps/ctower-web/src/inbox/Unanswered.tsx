import type { ReactElement } from "react";
import type { Answer } from "../api/client";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";

/**
 * Everything a call can be except an answer, drawn once.
 *
 * The four are different facts and stay different here — ctower is thinking,
 * ctower said no, ctower said nothing, ctower said something this client cannot
 * read — because an operator who cannot tell them apart cannot tell a refusal
 * from an outage. `null` when there is an answer: the caller draws the data.
 */
export function Unanswered<T>({
  answer,
  what,
  action,
}: {
  readonly answer: Answer<T>;
  /**
   * What is being asked, for the working line. Left out where the working state
   * is already drawn somewhere that does not move the page — a re-read that has
   * a previous answer to show must not push it down for the length of a read.
   */
  readonly what?: string;
  /** The one next action, for a refusal and for silence. */
  readonly action: string;
}): ReactElement | null {
  switch (answer.kind) {
    case "answered":
      return null;
    case "asking":
      return what === undefined ? null : <Asking what={what} />;
    case "refused":
      return <Refused problem={answer.problem} action={action} />;
    case "unreachable":
      return <Unreachable detail={answer.detail} action={action} />;
    case "malformed":
      return <Malformed detail={answer.detail} />;
  }
}
