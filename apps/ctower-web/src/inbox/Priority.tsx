import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import type { Severity } from "./commands";

/**
 * How loud this message is, in the contract's own closed set.
 *
 * Real radios, so a keyboard moves through them the way a keyboard already
 * knows how; the input carries the focus ring the law asks for and the label
 * carries the amber. Three values exist, so three are drawn — a dropdown would
 * hide a choice the sender has to make anyway.
 */
const LEVELS: readonly Severity[] = ["info", "P1", "P0"];

export function Priority({
  value,
  onChange,
}: {
  readonly value: Severity;
  readonly onChange: (value: Severity) => void;
}): ReactElement {
  return (
    <fieldset className="m-0 min-w-0 border-0 p-0">
      <legend className="mb-1.5 p-0 text-2xs text-muted">Priority</legend>
      <div className="flex h-9 items-stretch gap-1">
        {LEVELS.map((level) => (
          <label key={level} className="flex cursor-pointer">
            <input
              type="radio"
              name="priority"
              value={level}
              checked={value === level}
              onChange={(): void => {
                onChange(level);
              }}
              className="peer sr-only"
            />
            <span
              className={cn(
                "mono flex items-center rounded-sm border border-line px-2.5 text-xs text-muted",
                "peer-checked:border-amber peer-checked:bg-amber/14 peer-checked:text-amber-ink",
                "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2",
                "peer-focus-visible:outline-amber"
              )}
            >
              {level}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
