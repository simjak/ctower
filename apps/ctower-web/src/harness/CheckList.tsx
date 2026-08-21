import type { ReactElement, ReactNode } from "react";
import { Chip, Mono } from "../ui/primitives";
import { Mark } from "../ui/marks";
import type { Check, Level } from "./checks";
import { worstLevel } from "./checks";

const MARK: Readonly<Record<Level, "done" | "warn" | "dead">> = {
  info: "done",
  warn: "warn",
  error: "dead",
};

/**
 * One render for every list of checks this product will ever show.
 *
 * Paperclip's environment probe and ctower's registry answer the same shape —
 * a code, a level, a message — so they draw the same way and an operator learns
 * the vocabulary once. The chip is the worst level in the list, because a list
 * that is four greens and one red is a red.
 */
export function CheckList({
  title,
  checks,
  empty,
}: {
  readonly title: string;
  readonly checks: readonly Check[];
  readonly empty: ReactNode;
}): ReactElement {
  const worst = worstLevel(checks);
  const passed = checks.filter((check) => check.level === "info").length;

  return (
    <div className="rounded-md border border-line">
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <span className="text-sm font-semibold text-fg">{title}</span>
        <span className="flex-1" />
        {checks.length === 0 ? null : (
          <>
            <Mono className="text-muted">
              {passed} of {checks.length}
            </Mono>
            <Chip tone={statusTone(worst)}>{statusWord(worst)}</Chip>
          </>
        )}
      </div>
      {checks.length === 0 ? (
        <div className="px-4 py-3">{empty}</div>
      ) : (
        <ul className="m-0 list-none p-0">
          {checks.map((check) => (
            <li
              key={check.code}
              className="flex items-baseline gap-3 border-b border-line px-4 py-2.5 last:border-b-0"
            >
              <Mark name={MARK[check.level]} />
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-fg">{check.message}</span>
                {check.hint === undefined ? null : (
                  <span className="mt-0.5 block text-xs text-muted">{check.hint}</span>
                )}
              </span>
              <Mono className="hidden shrink-0 text-muted sm:inline">{check.code}</Mono>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function statusWord(level: Level): string {
  switch (level) {
    case "info":
      return "pass";
    case "warn":
      return "warn";
    case "error":
      return "fail";
  }
}

function statusTone(level: Level): "ok" | "amber" | "danger" {
  switch (level) {
    case "info":
      return "ok";
    case "warn":
      return "amber";
    case "error":
      return "danger";
  }
}
