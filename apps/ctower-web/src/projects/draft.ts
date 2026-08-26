import { GOALS_AT_LEAST, NAME_LENGTH, patternFor, PROJECT_SCHEMA_REF, REQUIRED } from "./schema";

/**
 * A project being written, and what the record will make of it.
 *
 * The operator types a name and the address of the repository the record files
 * this project under. Everything else the record insists on is derived here — the
 * key it is stored under, the prefix its tickets carry, the reference form of
 * the repository — because none of those is a decision: they are the same fact
 * spelled the way the record spells it, and asking someone to spell it twice is
 * how a form starts refusing perfectly good answers.
 *
 * The derivation runs on every keystroke and the result is checked against the
 * authored contract in `schema.ts` before anything is proposed. That is what
 * makes an invalid payload unreachable: Review is downstream of `problems`
 * being empty, so a payload the kernel would answer `bundle-schema-invalid` to
 * never gets sent.
 */
export interface Draft {
  readonly name: string;
  /** What this project is for, in the operator's own words. */
  readonly description: string;
  /** The repository this project is filed under, as a person would paste it. */
  readonly repoUrl: string;
  /** Where the code sits on this machine. */
  readonly localFolder: string;
}

export const BLANK: Draft = { name: "", description: "", repoUrl: "", localFolder: "" };

/** Which field an inline message belongs under. */
export type Slot = "name" | "repoUrl";

export interface Problem {
  readonly slot: Slot;
  /** What happened and the one thing to do about it. One line. */
  readonly message: string;
}

/**
 * The key this project is stored under, taken from its name.
 *
 * Lower case, one hyphen where the name had anything that is not a letter or a
 * digit, and no hyphen at either end — the shape the contract's own pattern
 * describes. It is derived rather than asked because a key is machine text: the
 * operator never sees it and has no way to prefer one.
 */
export function keyOf(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 127);
}

/**
 * The prefix this project's tickets carry, taken from its name.
 *
 * The letters of the name, the first three of them, upper case — the one piece
 * of derived machine text that does render, because a ticket is called by it.
 */
export function prefixOf(name: string): string {
  return name
    .toUpperCase()
    .replace(/[^A-Z]/g, "")
    .slice(0, 3);
}

/**
 * The repository, in the reference form the record stores.
 *
 * An operator pastes what they would clone — `https://github.com/acme/widgets`
 * — and the record keeps `repository:github/acme/widgets`. The host's first
 * label is the forge, the path is the path, and a `.git` suffix or a trailing
 * slash is noise from a copied address rather than part of the name. Nothing
 * about that conversion is a decision the operator should be asked to make, so
 * it is not one they are shown.
 *
 * An address this cannot read returns null, and the field says so rather than
 * building a reference out of a guess.
 */
export function repositoryRefOf(url: string): string | null {
  const typed = url.trim();
  if (typed === "") {
    return null;
  }
  const match = /^(?:https?:\/\/)?(?:www\.)?([^/\s]+)\/(.+)$/.exec(typed);
  const host = match?.[1]?.toLowerCase().split(".")[0] ?? "";
  const path = (match?.[2] ?? "").replace(/\.git$/, "").replace(/\/+$/, "");
  if (host === "" || path === "") {
    return null;
  }
  return `repository:${host}/${path}`;
}

/**
 * Everything wrong with this draft, against the record's own contract.
 *
 * Each problem names the field the operator can actually reach. The key and the
 * prefix are derived from the name, so a key or prefix the contract refuses is
 * reported on the name — telling someone their key is malformed when they never
 * typed one is telling them about a field that does not exist on their screen.
 */
export function problemsIn(draft: Draft, taken: readonly string[]): readonly Problem[] {
  const problems: Problem[] = [];
  const name = draft.name.trim();
  if (name.length < NAME_LENGTH.min) {
    problems.push({ slot: "name", message: "Give this project a name." });
  } else if (name.length > NAME_LENGTH.max) {
    problems.push({
      slot: "name",
      message: `That name is longer than ${String(NAME_LENGTH.max)} characters. Shorten it.`,
    });
  } else if (!patternFor("key").test(keyOf(name))) {
    problems.push({
      slot: "name",
      message: "Use at least three letters or digits in the name.",
    });
  } else if (!patternFor("prefix").test(prefixOf(name))) {
    problems.push({
      slot: "name",
      message: "Use at least two letters in the name; its tickets are called by them.",
    });
  } else if (taken.includes(keyOf(name))) {
    problems.push({ slot: "name", message: "This company already has a project by that name." });
  }
  problems.push(...repositoryProblems(draft));
  return problems;
}

/**
 * The repository is required, and the reference console's field is not.
 *
 * `contracts/components/project.schema.json` lists `repository_ref` among the
 * fields a project must carry, so a project without one cannot be recorded and
 * the field says required rather than optional. The alternative — accepting an
 * empty field and refusing at Review — is the dead page this ticket exists to
 * remove, and deriving a stand-in reference for a project that has no
 * repository would put a fact nobody stated into the record.
 *
 * The operator's question — why a project that is not software engineering must
 * name a repository — has no answer this module can give, because the answer is
 * that the record's project shape says so. So the messages say that, in words,
 * and the field's own note carries the same reason where he asks it. Making the
 * field genuinely optional is a change to the project component contract; this
 * guard reads the contract, so the day it lands the field softens by itself.
 */
function repositoryProblems(draft: Draft): readonly Problem[] {
  if (!REQUIRED.includes("repository_ref")) {
    return [];
  }
  if (draft.repoUrl.trim() === "") {
    return [
      {
        slot: "repoUrl",
        message:
          "A recorded project names one repository. Give the address of the one this work belongs to.",
      },
    ];
  }
  const reference = repositoryRefOf(draft.repoUrl);
  if (reference === null || !patternFor("repository_ref").test(reference)) {
    return [
      {
        slot: "repoUrl",
        message: "That is not an address this can read. Paste the repository's own web address.",
      },
    ];
  }
  return [];
}

/** The message under one field, when that field has one. */
export function problemAt(problems: readonly Problem[], slot: Slot): string | null {
  return problems.find((problem) => problem.slot === slot)?.message ?? null;
}

/**
 * The payload this draft records, once nothing is wrong with it.
 *
 * The goal is supplied rather than asked. A project must serve one and this
 * company has one; which outcomes a company pursues is authored on the company
 * itself, and making someone re-answer it to create a project asks them to
 * declare a goal when what they wanted was a project.
 */
export function payloadOf(
  draft: Draft,
  goals: readonly string[]
): Readonly<Record<string, unknown>> & { readonly key: string } {
  const name = draft.name.trim();
  return {
    schema: PROJECT_SCHEMA_REF,
    key: keyOf(name),
    display_name: name,
    prefix: prefixOf(name),
    repository_ref: repositoryRefOf(draft.repoUrl) ?? "",
    goal_refs: goals.slice(0, Math.max(GOALS_AT_LEAST, 1)),
  };
}
