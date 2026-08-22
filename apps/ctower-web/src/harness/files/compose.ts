import type {
  CompanyBundleDocument,
  CompanyBundleResource,
  ComponentProvenance,
  ComponentReference,
  VersionedComponent,
} from "@ctower/client";
import { canonicalDigest } from "../../mint/digest";
import { closureOf, idOf, isFileKind, strings, text } from "./read";
import type { FileKind } from "./read";

/**
 * The one function that turns an edited agent file back into the company
 * definition, because there is nowhere else for a file to live.
 *
 * The authored contract declares no operation that writes a persona, a skill or
 * a tool. Each is a component of the company bundle, so editing one is editing
 * the bundle: the same document, the same check, the same plan, the same
 * command under the operator's own authority.
 *
 * The digest is minted here the way the kernel mints it — RFC 8785 then
 * SHA-256 — and the registry recomputes it. A wrong byte is not a silent
 * failure: the bundle is refused at `digest.canonical`, which is exactly why a
 * browser is allowed to author a component at all.
 *
 * **A dependency pin is exact, so a revision moves everything that names it.**
 * The agent profile pins its persona, its skills and its tools by revision
 * *and* digest, and names them again inside its own payload. Revising a file
 * alone leaves those pins naming a revision the bundle no longer carries and
 * the registry answers `bundle-reference-invalid`. So every component that
 * names what moved moves with it, every payload pointer is re-aimed, every
 * binding is re-aimed, and the operator reads the whole set in the plan before
 * anything is applied.
 */
const AUTHORED_SOURCE = "ctower-web/agent-files";

/**
 * One file, as recorded and as edited. The payload *is* the file, so the draft
 * carries the payload and nothing else: what is recorded stays exactly the
 * bytes the API answered with.
 */
export interface FileDraft {
  readonly base: CompanyBundleResource;
  readonly payload: Readonly<Record<string, unknown>>;
}

export function draftOf(base: CompanyBundleResource): FileDraft {
  return { base, payload: base.payload };
}

export function withField(draft: FileDraft, field: string, value: unknown): FileDraft {
  return { ...draft, payload: { ...draft.payload, [field]: value } };
}

/**
 * Whether this differs from what is recorded, asked the registry's own way. The
 * digest over the canonical payload is what pins a component, so it is also the
 * only honest answer to "is this edited" — a re-typed identical value is not an
 * edit, and the digest says so.
 */
export function isEdited(draft: FileDraft): boolean {
  return canonicalDigest(draft.payload) !== draft.base.component.content_digest;
}

interface Move {
  readonly base: CompanyBundleResource;
  readonly payload: Readonly<Record<string, unknown>>;
  readonly digest: string;
  readonly revision: number;
}

export function documentWith(base: CompanyBundleDocument, draft: FileDraft): CompanyBundleDocument {
  const moves = movesFor(base, draft);
  const refs = new Map(
    [...moves].map(([id, move]) => [
      id,
      {
        content_digest: move.digest,
        key: move.base.component.key,
        kind: move.base.component.kind,
        revision: move.revision,
      },
    ])
  );
  const kept = base.resources.filter((resource) => !moves.has(idOf(resource.component)));
  return {
    ...base,
    assignments: base.assignments.map((assignment) => ({
      ...assignment,
      component: refs.get(idOf(assignment.component)) ?? assignment.component,
    })),
    resources: [...kept, ...[...moves.values()].map((move) => resourceOf(move, base, refs))],
  };
}

/**
 * Everything this edit moves, with the bytes each one ends up carrying.
 *
 * The set is `closureOf` — the edited file plus every component that names it,
 * through its declared pins *and* through the `key@revision` pointers its
 * payload carries. Each moved payload has those pointers re-aimed at what those
 * components now are, which is why a digest is computed here rather than
 * carried: an agent profile that now speaks as revision 2 is different bytes.
 */
function movesFor(base: CompanyBundleDocument, draft: FileDraft): ReadonlyMap<string, Move> {
  const edited = idOf(draft.base.component);
  const moving = new Map<string, CompanyBundleResource>(
    closureOf(base, draft.base).map((resource) => [idOf(resource.component), resource])
  );

  const renames = renamesFor(moving);
  const moves = new Map<string, Move>();
  for (const [id, resource] of moving) {
    const source = id === edited ? draft.payload : resource.payload;
    const payload = reaimed(source, renames);
    moves.set(id, {
      base: resource,
      payload,
      digest: canonicalDigest(payload),
      revision: resource.component.revision + 1,
    });
  }
  return moves;
}

/**
 * The payload pointers this move invalidates: `key@revision` to `key@revision`.
 *
 * A payload names a component by key and revision and never by kind, so a key
 * held by two moving components could not be re-aimed without guessing which
 * one a string meant. It is not guessed: an ambiguous key is left exactly as it
 * was recorded, and the plan shows a pointer that did not move.
 */
function renamesFor(
  moving: ReadonlyMap<string, CompanyBundleResource>
): ReadonlyMap<string, string> {
  const byKey = new Map<string, CompanyBundleResource[]>();
  for (const resource of moving.values()) {
    byKey.set(resource.component.key, [...(byKey.get(resource.component.key) ?? []), resource]);
  }
  const renames = new Map<string, string>();
  for (const [key, held] of byKey) {
    const only = held.length === 1 ? held[0] : undefined;
    if (only !== undefined) {
      renames.set(
        `${key}@${String(only.component.revision)}`,
        `${key}@${String(only.component.revision + 1)}`
      );
    }
  }
  return renames;
}

/**
 * One payload with every `key@revision` string it holds re-aimed, wherever it
 * holds it. A pointer is a string, and a payload is free to nest one inside an
 * object or a list, so the whole value is walked rather than its top level.
 */
function reaimed(
  payload: Readonly<Record<string, unknown>>,
  renames: ReadonlyMap<string, string>
): Readonly<Record<string, unknown>> {
  return reaimedValue(payload, renames) as Readonly<Record<string, unknown>>;
}

function reaimedValue(value: unknown, renames: ReadonlyMap<string, string>): unknown {
  if (typeof value === "string") {
    return renames.get(value) ?? value;
  }
  if (Array.isArray(value)) {
    return value.map((item: unknown) => reaimedValue(item, renames));
  }
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([field, held]: [string, unknown]) => [
        field,
        reaimedValue(held, renames),
      ])
    );
  }
  return value;
}

/**
 * One moved component, rebuilt: the next revision, superseding exactly the
 * revision it came from, pinned to the bytes it now carries, with every pin it
 * holds re-aimed at what that pin now is.
 *
 * Provenance is appended to and never replaced. The first entry says which
 * authored pack this component came from, which stays true; this browser adds
 * where the new bytes came from rather than erasing where the old ones did.
 */
function resourceOf(
  move: Move,
  base: CompanyBundleDocument,
  refs: ReadonlyMap<string, ComponentReference>
): CompanyBundleResource {
  const component = move.base.component;
  const requires = isFileKind(component.kind)
    ? capabilityPins(base, move.payload, component.kind)
    : component.compatibility.requires;
  return {
    component: {
      ...component,
      compatibility: {
        ...component.compatibility,
        requires: requires.map((required) => refs.get(idOf(required)) ?? required),
      },
      content_digest: move.digest,
      payload_ref: `object:${move.digest}`,
      provenance: provenanceOf(component, move),
      revision: move.revision,
      supersedes: {
        content_digest: component.content_digest,
        key: component.key,
        kind: component.kind,
        revision: component.revision,
      },
    },
    payload: move.payload,
  };
}

function provenanceOf(component: VersionedComponent, move: Move): readonly ComponentProvenance[] {
  if (move.digest === component.content_digest) {
    return component.provenance;
  }
  return [
    ...component.provenance,
    { digest: move.digest, kind: "authored", source: AUTHORED_SOURCE },
  ];
}

/**
 * What a file depends on, read out of its own payload rather than restated.
 *
 * These three kinds pin capabilities and nothing else — that is what the
 * recorded definition holds and what their authored schemas allow — so the
 * pins are derived from the payload the operator just edited. A capability the
 * company does not declare produces no pin, because the digest that would pin
 * it is not knowable here.
 */
function capabilityPins(
  base: CompanyBundleDocument,
  payload: Readonly<Record<string, unknown>>,
  kind: FileKind
): readonly ComponentReference[] {
  const declared = base.resources.filter((resource) => resource.component.kind === "capability");
  return namedCapabilities(payload, kind)
    .map((reference) =>
      declared.find(
        (resource) =>
          `${resource.component.key}@${String(resource.component.revision)}` === reference ||
          resource.component.key === reference
      )
    )
    .filter((resource): resource is CompanyBundleResource => resource !== undefined)
    .map((resource) => ({
      content_digest: resource.component.content_digest,
      key: resource.component.key,
      kind: resource.component.kind,
      revision: resource.component.revision,
    }));
}

/**
 * How each kind names a capability. A skill lists `key@revision` refs; a tool
 * names one capability by key; a persona names none. Each is that kind's own
 * authored schema, not this file's convention.
 */
function namedCapabilities(
  payload: Readonly<Record<string, unknown>>,
  kind: FileKind
): readonly string[] {
  switch (kind) {
    case "persona":
      return [];
    case "skill":
      return strings(payload, "capability_refs");
    case "tool": {
      const capability = text(payload, "capability");
      return capability === null ? [] : [capability];
    }
  }
}
