import { readdir, readFile } from "node:fs/promises";
import { noneOf, unreadOf, valueOf } from "./maybe";
import type { Known } from "./maybe";
import { coordinationRoot } from "./paths";
import { redacted } from "./redact";
import type { SignedClaim } from "../interface";

/**
 * Interim source: the status files a crew writes about its own work.
 *
 * The fleet's rule is that an artifact without a signature block is not
 * reviewable, mergeable or releasable, so a crew's `SIGNED-OFF` blocks are the
 * closest thing the record has to what that crew claimed and what it stood
 * under. They are quoted, never summarised: a paraphrase of a signature is not
 * a signature.
 *
 * Two bounds keep this a read a page can afford. Only files whose *name* names
 * the crew are opened — the convention is
 * `<stamp>--<crew>--<slug>.status.md`, so the directory listing does the
 * filtering — and only the newest few of those, with the number stated on the
 * screen so a cap never reads as "this is all of them".
 *
 * Read-only: the directory is listed and the files are opened for reading.
 * Every quoted byte passes `redacted` first — a status file is free text
 * another seat wrote, and nothing guarantees it never pasted a credential into
 * a claim.
 */

/** Newest-first by the stamp the filename starts with; at most this many. */
const FILE_CAP = 6;
/** One field of one signature. Long enough for every real claim, bounded. */
const FIELD_CAP = 1_400;
/**
 * How many signatures are quoted. A signature is long — a claim and what the
 * seat stood under, both verbatim — and eight of them buries the lifecycle
 * above them. The approved profile quotes the newest few and prints the total
 * beside them, so a reader sees how many exist and reads the ones that matter.
 */
const CLAIM_CAP = 3;
const REFERENCE_CAP = 24;

/** The keys a signature block declares. A line opening any other key is text. */
const FIELDS = ["seat", "crew", "model", "claim", "stood-under", "if-this-breaks"] as const;
type Field = (typeof FIELDS)[number];

const OPENER = /^\s*SIGNED-OFF\s*$/u;
const INDENTED = /^\s+\S/u;
const KEY_LINE = /^(\s+)([a-z][a-z-]*):\s?(.*)$/u;
const FENCE = /^\s*(?:```|~~~)/u;
/** A change this fleet can point at: `#215`, `PR #215`, `pull/215`. */
const REFERENCE = /(?:\bpull\/|#)(\d{1,6})\b/gu;

/**
 * One change reference a crew's own record names, where it named it, and the
 * project that record was filed under.
 *
 * The project travels with the reference on purpose. A long-lived crew moves
 * between projects, and `#1` written while it was on one fleet's repository is
 * a different change from `#1` on another's — joining every reference against
 * whatever project the crew is on *today* would put another repository's commit
 * subject under this crew's name.
 */
export interface ChangeReference {
  readonly reference: string;
  readonly citedIn: string;
  readonly project: Known<string>;
  /**
   * True when the project above is the crew's rather than the record's own —
   * a status file names no project, and many crew-log lines leave the field
   * empty. It is a derivation, so the row says so instead of presenting the
   * fallback as the record's answer.
   */
  readonly projectFromCrew: boolean;
}

/** Where one reference was found, and which project decides its verdict. */
export interface ReferenceOrigin {
  readonly citedIn: string;
  readonly project: Known<string>;
  readonly projectFromCrew: boolean;
}

export interface CrewRecords {
  readonly claims: readonly SignedClaim[];
  /** Every signature found, so a quote cap never reads as the whole set. */
  readonly signatures: number;
  readonly references: readonly ChangeReference[];
  /** How the coordination directory answered: what was read, or why nothing was. */
  readonly outcome: Known<string>;
  /** Files this crew has that were not opened, so a cap is never silent. */
  readonly beyondCap: number;
}

function capped(text: string): string {
  const trimmed = text.trim().replace(/\s+/gu, " ");
  return trimmed.length > FIELD_CAP ? `${trimmed.slice(0, FIELD_CAP)}…` : trimmed;
}

function fieldOf(block: ReadonlyMap<string, string>, key: Field, why: string): Known<string> {
  const held = block.get(key);
  return held === undefined || held.trim().length === 0
    ? noneOf(why)
    : valueOf(redacted(capped(held)));
}

function isField(key: string): key is Field {
  return (FIELDS as readonly string[]).includes(key);
}

/**
 * Pull every signature block out of one status file.
 *
 * A block runs from its `SIGNED-OFF` line to the first line that is neither
 * indented nor blank, or to a fence. A continuation line is any indented line
 * that does not open one of the declared keys — which is why the key set is
 * closed: a claim wrapping onto a line that happens to read `note: …` stays
 * part of the claim instead of silently becoming a field nobody signed.
 */
function blocksIn(text: string): readonly ReadonlyMap<string, string>[] {
  const lines = text.split("\n");
  const blocks: Map<string, string>[] = [];
  let open: Map<string, string> | null = null;
  let key: Field | null = null;

  for (const line of lines) {
    if (OPENER.test(line)) {
      open = new Map<string, string>();
      key = null;
      blocks.push(open);
      continue;
    }
    if (open === null) {
      continue;
    }
    if (FENCE.test(line)) {
      open = null;
      continue;
    }
    if (line.trim().length === 0) {
      continue;
    }
    if (!INDENTED.test(line)) {
      // the block's fields are indented under it; anything flush left ends it
      open = null;
      key = null;
      continue;
    }
    const matched = KEY_LINE.exec(line);
    const name = matched?.[2] ?? "";
    if (matched !== null && isField(name)) {
      key = name;
      open.set(name, matched[3] ?? "");
      continue;
    }
    // an indented line that opens no declared key is the previous field
    // wrapping — which is why the key set is closed, so a claim continuing on a
    // line that happens to read `note: …` stays part of the claim
    if (key !== null) {
      open.set(key, `${open.get(key) ?? ""} ${line.trim()}`);
    }
  }
  return blocks.filter((block) => block.size > 0);
}

/**
 * Every change reference one piece of a crew's own writing names. Shared with
 * the crew-log reader so a reference found in a log line and one found in a
 * status file are recognised by the same rule rather than by two spellings of
 * it.
 */
export function changeReferencesIn(
  text: string,
  origin: ReferenceOrigin
): readonly ChangeReference[] {
  return [...text.matchAll(REFERENCE)].map((match) => ({
    reference: `#${match[1] ?? ""}`,
    ...origin,
  }));
}

/** The crew's own status files, newest first. The convention is the filter. */
async function statusFiles(crew: string): Promise<readonly string[]> {
  const entries = await readdir(coordinationRoot());
  return entries
    .filter((entry) => entry.endsWith(".status.md") && entry.includes(`--${crew}--`))
    .sort((left, right) => right.localeCompare(left));
}

/**
 * `crewProject` is the project the crew is recorded under now. A status file
 * names no project of its own, so a reference found in one is joined against
 * that — stated on the row, so a reference the crew wrote while it was on
 * another project is not silently checked against this one's trunk.
 */
export async function readCrewRecords(
  crew: string,
  crewProject: Known<string>
): Promise<CrewRecords> {
  let named: readonly string[];
  try {
    named = await statusFiles(crew);
  } catch (error: unknown) {
    return {
      claims: [],
      signatures: 0,
      references: [],
      outcome: unreadOf(
        error instanceof Error ? error.message : "the coordination directory could not be listed"
      ),
      beyondCap: 0,
    };
  }
  if (named.length === 0) {
    return {
      claims: [],
      signatures: 0,
      references: [],
      outcome: noneOf(`no status file in ${coordinationRoot()} names this crew`),
      beyondCap: 0,
    };
  }

  const opened = named.slice(0, FILE_CAP);
  const claims: SignedClaim[] = [];
  const references: ChangeReference[] = [];
  const unread: string[] = [];
  for (const file of opened) {
    let text: string;
    try {
      text = await readFile(`${coordinationRoot()}/${file}`, "utf8");
    } catch {
      unread.push(file);
      continue;
    }
    references.push(
      ...changeReferencesIn(text, {
        citedIn: file,
        project: crewProject,
        projectFromCrew: true,
      })
    );
    for (const block of blocksIn(text)) {
      // the block's own `crew:` decides, not the filename: a status file can
      // quote a signature from another seat, and attributing that to this crew
      // would put a claim under a name that never made it. Seats qualify the
      // field — `cso-216-glm (round two)` — so the crew is the first token,
      // and the rest is the seat's own annotation, not a different crew.
      const signer = block.get("crew")?.trim().split(/\s+/u)[0];
      if (signer !== undefined && signer !== crew) {
        continue;
      }
      claims.push({
        file: redacted(file),
        seat: fieldOf(block, "seat", "the block names no seat"),
        model: fieldOf(block, "model", "the block names no model"),
        claim: fieldOf(block, "claim", "the block carries no claim"),
        stoodUnder: fieldOf(block, "stood-under", "the block records nothing stood under"),
        ifThisBreaks: fieldOf(block, "if-this-breaks", "the block records no repair route"),
      });
    }
  }

  const read = opened.length - unread.length;
  return {
    // newest first, because the newest claim is the one still standing
    claims: claims.reverse().slice(0, CLAIM_CAP),
    signatures: claims.length,
    references: references.slice(0, REFERENCE_CAP),
    outcome:
      read === 0
        ? unreadOf(`none of this crew's ${String(opened.length)} status files could be opened`)
        : valueOf(
            `${String(read)} of ${String(named.length)} status files this crew wrote` +
              (unread.length === 0 ? "" : `; ${String(unread.length)} could not be opened`)
          ),
    beyondCap: named.length - opened.length,
  };
}
