/**
 * How one component names another from inside a payload.
 *
 * A component is pinned twice. `compatibility.requires` is the declared pin,
 * carrying kind, key, revision and digest, and the registry checks it. The
 * payload names the same thing again as a bare `key@revision` string — an agent
 * profile's `persona_ref` is what every screen resolves an agent's name
 * through — and nothing checks that one. Both go stale when a revision moves,
 * so both are read here.
 *
 * The bare string cannot say what it names: the wizard mints a persona and an
 * agent profile under one key, so `ctower.commander@1` is two different
 * components. The authored schemas answer it. A field that names a component is
 * `<kind>_ref` or `<kind>_refs` — `persona_ref`, `harness_ref`, `skill_refs`,
 * `capability_refs`, `environment_ref`. So the field carries the kind, and this
 * module reads the kind off the field instead of guessing it from the key.
 *
 * A field whose stem is not a component kind (`dependency_refs`,
 * `repository_ref`) names nothing this screen moves: it matches no component and
 * is left exactly as recorded.
 */
const REVISION_POINTER = /^[a-z][a-z0-9.-]{2,127}@[1-9][0-9]*$/;

/** One `key@revision` string a payload holds, and the kind its field names. */
export interface Pointer {
  readonly kind: string;
  readonly ref: string;
}

/** How a payload names one exact revision: its kind, key and revision. */
export function pointerTo(component: {
  readonly kind: string;
  readonly key: string;
  readonly revision: number;
}): string {
  return `${component.kind}|${component.key}@${String(component.revision)}`;
}

/** Every revision pointer a payload holds, wherever it holds it. */
export function pointersHeldBy(value: unknown, kind: string | null = null): readonly Pointer[] {
  if (typeof value === "string") {
    return kind !== null && REVISION_POINTER.test(value) ? [{ kind, ref: value }] : [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item: unknown) => pointersHeldBy(item, kind));
  }
  if (typeof value === "object" && value !== null) {
    return Object.entries(value).flatMap(([field, held]: [string, unknown]) =>
      pointersHeldBy(held, kindNamedBy(field) ?? kind)
    );
  }
  return [];
}

/**
 * One payload with every pointer it holds re-aimed, wherever it holds it.
 *
 * `renames` is keyed the way `pointerTo` writes it, so a persona and an agent
 * profile sharing a key re-aim independently. A string under a field that names
 * no kind is untouched.
 */
export function reaimedPayload(
  payload: Readonly<Record<string, unknown>>,
  renames: ReadonlyMap<string, string>
): Readonly<Record<string, unknown>> {
  return reaimedValue(payload, renames, null) as Readonly<Record<string, unknown>>;
}

function reaimedValue(
  value: unknown,
  renames: ReadonlyMap<string, string>,
  kind: string | null
): unknown {
  if (typeof value === "string") {
    return kind === null ? value : (renames.get(`${kind}|${value}`) ?? value);
  }
  if (Array.isArray(value)) {
    return value.map((item: unknown) => reaimedValue(item, renames, kind));
  }
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([field, held]: [string, unknown]) => [
        field,
        reaimedValue(held, renames, kindNamedBy(field) ?? kind),
      ])
    );
  }
  return value;
}

/** The kind a field names, by the authored `<kind>_ref` / `<kind>_refs` naming. */
function kindNamedBy(field: string): string | null {
  if (field.endsWith("_refs")) {
    return field.slice(0, -"_refs".length);
  }
  if (field.endsWith("_ref")) {
    return field.slice(0, -"_ref".length);
  }
  return null;
}
