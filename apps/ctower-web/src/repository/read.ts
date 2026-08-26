/**
 * What a recorded repository reference means to a person.
 *
 * `repository:github/simjak/ctower/<40 hex>` is a scheme, a host family, a path
 * and the commit a project pins. What survives the translation is the
 * repository's own name and, when the host is one this console can address, a
 * link to it — nothing else reaches a screen.
 *
 * The Projects surface keeps its own reader in `projects/read.ts`, and the two
 * disagree on purpose about one thing: it renders `github/acme/widgets`, naming
 * the forge in the text, and this one renders `acme/widgets` and lets the mark
 * name the forge. Two readers of one reference is one too many and the tree
 * should end with a single module — but which label survives is a design
 * decision about two screens, not a merge conflict to settle quietly here.
 */

/** The hosts this console can address, and what a person calls each one. */
const HOSTS: Readonly<Record<string, { readonly origin: string; readonly name: string }>> = {
  github: { origin: "https://github.com", name: "GitHub" },
  gitlab: { origin: "https://gitlab.com", name: "GitLab" },
};

/**
 * A repository, as a person reads it and as a browser opens it.
 *
 * Only the repository's own name survives the translation: an operator reads
 * `simjak/ctower`, never `repository:` and never forty hex characters. What is
 * dropped is dropped everywhere — label, hover and address carry the same name —
 * because a technical string a person cannot act on has no business on a
 * rendered surface.
 */
export interface Repository {
  /** What a row says, and all it says: `simjak/ctower`. */
  readonly label: string;
  /** Where it opens, or null when this console cannot address the host. */
  readonly href: string | null;
  /** The host as authored, so a row can draw its mark: `github`. */
  readonly host: string;
  /** The host as a person names it — `GitHub` — or null when it has no address. */
  readonly site: string | null;
}

/** `repository:<host>/<path>[/<40 hex>]` reduced to the repository's own name. */
export function repositoryOf(reference: string): Repository {
  const path = reference.replace(/^repository:/, "");
  const match = /^([a-z][a-z0-9.-]*)\/(.+?)(?:\/[0-9a-f]{40})?$/.exec(path);
  const host = match?.[1] ?? "";
  const label = match?.[2] ?? path;
  const site = HOSTS[host];
  if (site === undefined) {
    // A host with no address gets no link. Composing a URL out of a host this
    // console does not know would be inventing a domain nobody recorded.
    return { label, href: null, host, site: null };
  }
  return { label, href: `${site.origin}/${label}`, host, site: site.name };
}
