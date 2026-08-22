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
  className,
  ...props
}: ComponentProps<"select"> & {
  readonly options: readonly { readonly value: string; readonly label: string }[];
}): ReactElement {
  return (
    <select
      className={cn(
        "h-9 w-full min-w-0 rounded-sm border border-line bg-bg px-3 text-sm text-fg",
        "disabled:cursor-not-allowed disabled:text-muted",
        className
      )}
      {...props}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
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
