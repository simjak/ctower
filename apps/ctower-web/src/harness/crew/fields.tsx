import type { ComponentProps, ReactElement } from "react";
import type { CredentialScope } from "@ctower/client";
import { Select as SelectControl } from "../../ui/primitives";
import { Checkbox } from "../../ui/form";

/**
 * The two controls this screen needs that the shared vocabulary does not carry.
 *
 * The select is the shared `Select` primitive with one thing added: a list of
 * options where a recorded thing this command cannot take is shown and
 * disabled, and a record with nothing to offer says so instead of rendering
 * blank. The control itself — its metrics, its focus treatment, its disabled
 * state — is the shell's, not a second copy of it. A scope is a set of three,
 * which is a row of checkboxes rather than a widget.
 */
export function Select({
  options,
  empty,
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
    <SelectControl disabled={options.length === 0} {...props}>
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
    </SelectControl>
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
