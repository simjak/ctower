import { useId } from "react";
import type { ReactElement } from "react";
import { Chip } from "../ui/primitives";
import { cn } from "../ui/cn";
import type { HarnessChoice, HarnessFamily } from "./harnesses";

/**
 * Step one of making an agent: which harness it runs on, picked from cards.
 *
 * The control is a real radio group — a `fieldset` of labels, each wrapping a
 * native `input type="radio"` that is visually hidden and nothing else. The
 * console settled this once already for `Select`: a closed set is offered by
 * the native control that already has a keyboard, a screen reader and a form,
 * and a listbox rebuilt in React would only be the same thing, later, with its
 * own focus bugs. Arrow keys move between these cards because they are radios.
 *
 * A card that ctower cannot run on is drawn and disabled rather than dropped.
 * Its radio is `disabled`, so the group's keyboard skips it and no operator can
 * choose a harness this tower has no way to start.
 */
export function HarnessPicker({
  choices,
  value,
  onChoose,
}: {
  readonly choices: readonly HarnessChoice[];
  /** The harness chosen so far, or nothing chosen yet. */
  readonly value: HarnessFamily | null;
  readonly onChoose: (family: HarnessFamily) => void;
}): ReactElement {
  // A radio group is named, and the name is what the browser groups by: two
  // pickers on one screen under one name would be one group, so choosing here
  // would silently clear the other. Each picker gets its own.
  const group = useId();
  return (
    <fieldset className="m-0 min-w-0 border-0 p-0">
      <legend className="mb-2 p-0 text-2xs text-muted">Harness</legend>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {choices.map((choice) => (
          <HarnessCard
            key={choice.family}
            choice={choice}
            group={group}
            chosen={choice.family === value}
            onChoose={onChoose}
          />
        ))}
      </div>
    </fieldset>
  );
}

/**
 * One card: the icon the operator recognises, the name they say out loud, one
 * line of what it is, and the badge only where it is earned.
 */
function HarnessCard({
  choice,
  group,
  chosen,
  onChoose,
}: {
  readonly choice: HarnessChoice;
  /** The radio group this card belongs to. */
  readonly group: string;
  readonly chosen: boolean;
  readonly onChoose: (family: HarnessFamily) => void;
}): ReactElement {
  const Icon = choice.icon;
  return (
    <label className={cn(cardShape, chosen ? cardChosen : cardQuiet(choice.available))}>
      <input
        type="radio"
        name={group}
        className="sr-only"
        value={choice.family}
        checked={chosen}
        disabled={!choice.available}
        onChange={(): void => {
          onChoose(choice.family);
        }}
      />
      {/* The name is a proper noun and never truncates: in a column too narrow
          for the badge beside it, the badge wraps under instead. */}
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Icon
          aria-hidden
          className={cn("size-5 shrink-0", chosen ? "text-amber-ink" : undefined)}
        />
        <span className="min-w-0 flex-1 text-sm font-semibold">{choice.name}</span>
        <Badge choice={choice} />
      </span>
      <span className="mt-2 block text-xs text-muted">{choice.blurb}</span>
    </label>
  );
}

/**
 * One badge slot, two things it can say — and most cards say neither.
 *
 * A card either carries the recommendation or carries the reason it cannot be
 * picked. Both are two words at most, per D9, and a card that is simply an
 * ordinary choice wears nothing at all.
 */
function Badge({ choice }: { readonly choice: HarnessChoice }): ReactElement | null {
  if (!choice.available) {
    return <Chip>Not built</Chip>;
  }
  return choice.recommended ? <Chip tone="amber">Recommended</Chip> : null;
}

const cardShape = cn(
  "block min-w-0 rounded-md border p-3 text-left",
  // The card is the label, so the focus ring has to be drawn for the radio
  // inside it — otherwise the one thing a keyboard is on is the one thing that
  // shows nothing.
  "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-amber"
);

const cardChosen = "border-amber bg-amber/12 cursor-pointer";

/** Unchosen, and dead-quiet when there is nothing to choose. */
function cardQuiet(available: boolean): string {
  return available
    ? "border-line bg-card cursor-pointer hover:bg-raised"
    : "border-dashed border-line bg-card cursor-default opacity-60";
}
