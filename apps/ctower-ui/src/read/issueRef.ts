import type { IssueReference } from "./interface";

/**
 * The issue a ticket was raised from, resolved from the record's own source.
 *
 * The operator asked the board to reflect the issue each ticket is linked to.
 * The only link the record holds is `source: {kind, ref}`, so this resolves a
 * URL from exactly two things and refuses on anything else:
 *
 * 1. a **kind** that names an issue tracker this surface knows how to address,
 *    and
 * 2. a **ref** that already carries the repository, in the `owner/repo#123`
 *    form that tracker uses.
 *
 * Everything else renders as the raw ref, as text. That is the whole point of
 * the rule. A ref like `manibo-G1-gh192` *looks* like it names issue 192, and a
 * title like "…(GH manibo#3283)" *looks* like it names a repository — but
 * turning either into `https://github.com/…/issues/192` means choosing an owner
 * and a repository that nothing recorded, from the spelling of an identifier.
 * SPEC INV-66 forbids inferring a fact that way, and a wrong link is worse than
 * no link: the operator clicks it and lands on someone else's issue.
 *
 * On the instance this surface reads today, no ticket carries an issue kind —
 * the four recorded kinds are `mission-control-request`, `dogfood-gap`,
 * `operator-spec` and `fixture`. So this resolves nothing yet, and the ticket
 * screen says the source is not an issue reference rather than showing an empty
 * space where a link would be. It resolves the day a ticket is captured from an
 * issue.
 */

/** Issue trackers this surface knows how to address, and how. */
const TRACKERS: Readonly<Record<string, (repository: string, number: number) => string>> = {
  "github-issue": (repository, number) =>
    `https://github.com/${repository}/issues/${String(number)}`,
  "gitlab-issue": (repository, number) =>
    `https://gitlab.com/${repository}/-/issues/${String(number)}`,
};

/** `owner/repo#123` — the repository is in the ref, never supplied by us. */
const QUALIFIED = /^([A-Za-z0-9][\w.-]*\/[A-Za-z0-9][\w.-]*)#(\d{1,9})$/u;

export function issueReferenceOf(kind: string, ref: string): IssueReference | null {
  const address = TRACKERS[kind];
  if (address === undefined) {
    return null;
  }
  const parsed = QUALIFIED.exec(ref.trim());
  const repository = parsed?.[1];
  const digits = parsed?.[2];
  if (repository === undefined || digits === undefined) {
    // the kind says "issue" and the ref does not carry a repository. The number
    // alone cannot be addressed, and choosing a repository for it would be the
    // guess this module exists to refuse
    return null;
  }
  const number = Number.parseInt(digits, 10);
  return {
    repository,
    number,
    url: address(repository, number),
    label: `${repository}#${String(number)}`,
  };
}

/** Whether a recorded source kind claims to be an issue at all. */
export function namesAnIssueTracker(kind: string): boolean {
  return kind in TRACKERS;
}
