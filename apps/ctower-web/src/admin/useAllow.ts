import { useCallback, useState } from "react";
import type { ConsoleSessionAllowance, ConsoleSessionAllowRequest } from "@ctower/client";
import { ask, ASKING, singleShotCommands } from "../api/client";
import type { Answer } from "../api/client";

/**
 * The one console command this app can reach, and the four states it produces.
 *
 * `null` is not a fifth state hiding in a nullable: it is "the operator has not
 * asked yet", which is a different fact from "the tower has not answered yet"
 * and must not be drawn as one. Everything after the first send is an `Answer`.
 *
 * A send while one is out is dropped rather than queued. The command carries no
 * idempotency key, so two in flight would be two allowances with nothing in
 * either answer to tell the operator which one the tower kept.
 */
export function useAllow(): {
  readonly answer: Answer<ConsoleSessionAllowance> | null;
  readonly allow: (body: ConsoleSessionAllowRequest) => void;
} {
  const [answer, setAnswer] = useState<Answer<ConsoleSessionAllowance> | null>(null);

  const allow = useCallback(
    (body: ConsoleSessionAllowRequest): void => {
      if (answer?.kind === "asking") {
        return;
      }
      setAnswer(ASKING);
      void ask(() => singleShotCommands.allowConsoleSession({ body })).then(setAnswer);
    },
    [answer]
  );

  return { answer, allow };
}
