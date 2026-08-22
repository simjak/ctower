import type { ComponentProps, ReactElement } from "react";
import type { CredentialScope } from "@ctower/client";
import { cn } from "../../ui/cn";
import { Checkbox } from "../../ui/form";

/**
 * The two controls this screen needs that the shared vocabulary does not carry.
 *
 * Both are deliberately plain. A native `select` already answers to the keyboard
 * on every platform and takes the one focus treatment the token layer puts on
 * everything focusable, and a scope is a set of three, which is a row of
 * checkboxes rather than a widget.
 */
export function Select({
  options,
  empty,
  className,
  ...props
}: ComponentProps<"select"> & {
  readonly options: readonly {
    readonly value: string;
    readonly label: string;
    /** Recorded, but not something this command can take. Shown, never chosen. */
    readonly unavailable?: boolean;
  }[];
  /** What the control says when the record offers it nothing to choose from. */
  readonly empty: string;
}): ReactElement {
  return (
    <select
      className={cn(
        "h-9 w-full min-w-0 rounded-sm border border-line bg-bg px-3 text-sm text-fg",
        "disabled:cursor-not-allowed disabled:text-muted",
        className
      )}
      disabled={options.length === 0}
      {...props}
    >
      {/* A blank dropdown reads as a control that has not loaded. One that has
          nothing to offer says so, because that is the honest state. */}
      {options.length === 0 ? (
        <option value="">{empty}</option>
      ) : (
        options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.unavailable === true}>
            {option.label}
          </option>
        ))
      )}
    </select>
  );
}

/** What the bearer of this address may do. Nothing is chosen by default but capture. */
export function ScopeChoice({
  all,
  chosen,
  onChosen,
}: {
  readonly all: readonly CredentialScope[];
  readonly chosen: readonly CredentialScope[];
  readonly onChosen: (scopes: readonly CredentialScope[]) => void;
}): ReactElement {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      {all.map((scope) => (
        <label key={scope} className="flex cursor-pointer items-center gap-2">
          <Checkbox
            checked={chosen.includes(scope)}
            label={scope}
            onCheckedChange={(next): void => {
              onChosen(next ? [...chosen, scope] : chosen.filter((held) => held !== scope));
            }}
          />
          <span className="text-sm text-fg">{scope}</span>
        </label>
      ))}
    </div>
  );
}
