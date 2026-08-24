import { useId } from "react";
import type { ReactElement } from "react";
import type { VersionedComponent } from "@ctower/client";
import { Chip, Mono } from "../../ui/primitives";
import { Copy } from "./Copy";

/**
 * Where the instructions come from, and where they are kept — both shut by
 * default.
 *
 * The operator's amendment puts Mode, Root and Entry inside an `Advanced`
 * disclosure and nowhere else, and AC-7 puts every piece of machine text in the
 * same place. Those turn out to be one requirement: the two questions this
 * panel answers are *whose files are these* and *what exactly is being edited*,
 * and the second one can only be answered in the record's own words. So the
 * disclosure is where those words live, it says who it is written for, and it
 * is a native `details` so a keyboard reaches it without this screen teaching
 * anyone a new control.
 */
export function Advanced({
  component,
}: {
  /** The component open in the editor. Every field here is machine text. */
  readonly component: VersionedComponent;
}): ReactElement {
  return (
    <details className="border-t border-line pt-3">
      <summary className="cursor-pointer text-2xs text-muted">Advanced</summary>
      <div className="mt-3 space-y-4">
        <Mode />
        <Where component={component} />
      </div>
    </details>
  );
}

/**
 * Managed or External, and only one of them is a thing this record can be.
 *
 * External is drawn and disabled rather than dropped. The operator asked for
 * the choice, so the screen shows the choice and says why one side of it is
 * not reachable — hiding it would answer "where is External" with silence, and
 * the harness picker settled that argument one lane over. What blocks it is not
 * a missing screen: `persona.schema.json` and `skill.schema.json` both close
 * their payloads with `additionalProperties: false` and declare no field for a
 * path, so an external root has nowhere in the record to be written down.
 * Reaching it is a schema change, not a control.
 */
function Mode(): ReactElement {
  const group = useId();
  return (
    <fieldset className="mx-0 min-w-0 border-0 p-0">
      <legend className="mb-2 p-0 text-2xs text-muted">Where instructions are kept</legend>
      <div className="space-y-2">
        <Choice
          group={group}
          checked
          label="Managed"
          says="ctower keeps these files. Editing one here is what changes them."
        />
        <Choice
          group={group}
          checked={false}
          label="External"
          says="An agent reading from a folder you keep. The record has no field for that path yet, so nothing here could write it down."
          unbuilt
        />
      </div>
    </fieldset>
  );
}

function Choice({
  group,
  checked,
  label,
  says,
  unbuilt = false,
}: {
  readonly group: string;
  readonly checked: boolean;
  readonly label: string;
  readonly says: string;
  readonly unbuilt?: boolean;
}): ReactElement {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-sm has-disabled:cursor-not-allowed">
      <input
        type="radio"
        name={group}
        defaultChecked={checked}
        disabled={unbuilt}
        className="mt-0.5 size-3.5 shrink-0 accent-amber disabled:opacity-50"
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className={unbuilt ? "text-muted" : "font-medium"}>{label}</span>
          {unbuilt ? <Chip>Not built</Chip> : null}
        </span>
        <span className="mt-0.5 block text-xs text-muted">{says}</span>
      </span>
    </label>
  );
}

/**
 * What is being edited, in the record's own words.
 *
 * A managed file has no folder and no path — it is a component of the company
 * definition, and the three values below are the whole of its address. They are
 * the closest honest thing to the reference console's storage root, so they get
 * its copy button: the one reason to open this disclosure is to carry one of
 * them somewhere else.
 */
function Where({ component }: { readonly component: VersionedComponent }): ReactElement {
  return (
    <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5">
      <Line label="Kept as" value={`${component.kind} ${component.key}`} />
      <Line label="Revision" value={String(component.revision)} />
      <Line label="Pinned to" value={component.content_digest} />
    </dl>
  );
}

function Line({ label, value }: { readonly label: string; readonly value: string }): ReactElement {
  return (
    <>
      <dt className="m-0 text-2xs text-muted">{label}</dt>
      <dd className="m-0 min-w-0">
        <Mono className="block truncate text-muted">{value}</Mono>
      </dd>
      <Copy what={value} label={label} />
    </>
  );
}
