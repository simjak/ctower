import type { ReactElement } from "react";
import { Input } from "../ui/primitives";
import { Field } from "../ui/form";
import type { FieldSchema } from "./schema";

/**
 * One renderer for every adapter's settings, forever.
 *
 * This is paperclip's mechanic: an adapter declares `{key,label,type,options,
 * hint,group}` and the UI draws it. There is no React per harness, so a new
 * adapter — or a new field on an existing one — needs no change here.
 *
 * Today every adapter declares nothing, and that is drawn as what it is rather
 * than hidden: the group renders its own empty state and says so in a sentence.
 */
export function ConfigFields({
  fields,
  values,
  onValue,
  empty,
}: {
  readonly fields: readonly FieldSchema[];
  readonly values: Readonly<Record<string, string>>;
  readonly onValue: (key: string, value: string) => void;
  readonly empty: string;
}): ReactElement {
  if (fields.length === 0) {
    return <p className="m-0 text-sm text-muted">{empty}</p>;
  }

  return (
    <div className="space-y-4">
      {fields.map((field) => (
        <Field
          key={field.key}
          label={field.label}
          {...(field.hint === undefined ? {} : { hint: field.hint })}
        >
          <Control field={field} value={values[field.key] ?? ""} onValue={onValue} />
        </Field>
      ))}
    </div>
  );
}

function Control({
  field,
  value,
  onValue,
}: {
  readonly field: FieldSchema;
  readonly value: string;
  readonly onValue: (key: string, value: string) => void;
}): ReactElement {
  switch (field.type) {
    case "select":
      return (
        <select
          className="h-9 w-full rounded-sm border border-line bg-bg px-3 text-sm text-fg"
          value={value}
          onChange={(event): void => {
            onValue(field.key, event.target.value);
          }}
        >
          {(field.options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    case "toggle":
      return (
        <input
          type="checkbox"
          className="size-4 accent-amber"
          checked={value === "true"}
          onChange={(event): void => {
            onValue(field.key, event.target.checked ? "true" : "false");
          }}
        />
      );
    case "number":
    case "text":
      return (
        <Input
          type={field.type === "number" ? "number" : "text"}
          value={value}
          onChange={(event): void => {
            onValue(field.key, event.target.value);
          }}
        />
      );
  }
}
