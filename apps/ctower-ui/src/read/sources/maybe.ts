/**
 * A sub-read that may not have answered.
 *
 * Round-1 review of PR #215 found several adapters catching a failed
 * sub-command and returning `""`, which a screen then rendered as
 * "no branch recorded" or "not a git checkout" — a failed read painted as a
 * recorded absence, inside a `Reading` that was otherwise honestly `present`.
 *
 * The outer `Reading` cannot express that: the screen *does* have a value to
 * show, just not this field of it. So a field that can fail on its own carries
 * this instead of a nullable, and the screens render the three cases in three
 * different ways — a value, "the record holds none", and "this read failed".
 */
export type Known<T> =
  | { readonly known: "value"; readonly value: T }
  /** The source answered and holds nothing here. */
  | { readonly known: "none"; readonly why: string }
  /** The sub-read did not answer. Never rendered as `none`. */
  | { readonly known: "unread"; readonly reason: string };

export function valueOf<T>(value: T): Known<T> {
  return { known: "value", value };
}

export function noneOf<T>(why: string): Known<T> {
  return { known: "none", why };
}

export function unreadOf<T>(reason: string): Known<T> {
  return { known: "unread", reason };
}

/** Run a sub-read, keeping a failure distinct from an empty answer. */
export async function attempted<T>(
  load: () => Promise<T>,
  empty: (value: T) => boolean,
  why: string
): Promise<Known<T>> {
  try {
    const value = await load();
    return empty(value) ? noneOf(why) : valueOf(value);
  } catch (error: unknown) {
    return unreadOf(error instanceof Error ? error.message : "the sub-read did not complete");
  }
}

/** True when any field of a record was left unread, so a screen can say so. */
export function anyUnread(fields: readonly Known<unknown>[]): boolean {
  return fields.some((field) => field.known === "unread");
}
