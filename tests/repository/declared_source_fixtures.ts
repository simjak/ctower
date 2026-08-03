// Drivers for the two contracts the surface makes in words rather than numbers:
// what it cites for a fact it cannot show, and where a nav item promises to go.
//
// Round-3 QA found nine "not built yet" panels all reading *lands with #186* —
// an issue about the operator-channel feed, which covers none of them (#241) —
// and a nav item called *Tickets* that opened the detail page of one arbitrary
// ticket (#243). Both are honesty defects in data this app declares, so both are
// checked here rather than left to a reviewer noticing.
//
// Both modules are pure, so Node runs them directly with type stripping.

import { DECLARED_SOURCES } from "../../apps/ctower-ui/src/read/futureSources.ts";
import { NEW_TICKET_INERT, RAIL } from "../../apps/ctower-ui/src/frame/rail.ts";
import {
  configuredProjects,
  defaultProjectKey,
  selectedProjectKey,
} from "../../apps/ctower-ui/src/read/projects.ts";
import { issueReferenceOf, namesAnIssueTracker } from "../../apps/ctower-ui/src/read/issueRef.ts";

/* ── the three project boards, and the issue link ─────────────────────────
   The operator runs three projects and asked to see three boards. Both the
   project list and the issue-link rule are decisions this surface makes about
   what it may claim, so both are driven here. */

const projects = {
  configured: configuredProjects(),
  default: defaultProjectKey(),
  // a key the fleet does not configure may not become a board
  selectedFromUnknown: selectedProjectKey("not-a-project"),
  selectedFromKnown: selectedProjectKey("manibo"),
  selectedFromNothing: selectedProjectKey(null),
};

const issues = {
  // the record names the tracker AND the ref carries the repository
  resolvedGithub: issueReferenceOf("github-issue", "simjak/ctower#236"),
  resolvedGitlab: issueReferenceOf("gitlab-issue", "group/proj#7"),
  // the kinds this instance actually holds: none is an issue tracker
  missionControlRequest: issueReferenceOf("mission-control-request", "manibo-R2507"),
  dogfoodGap: issueReferenceOf("dogfood-gap", "manibo-G1-gh192"),
  operatorSpec: issueReferenceOf("operator-spec", "R2738"),
  fixture: issueReferenceOf("fixture", "ctower:i1.6:api-cli-trust-spine"),
  // an issue kind whose ref does not carry a repository: the number alone is
  // not addressable, and choosing a repository for it would be the guess
  bareNumber: issueReferenceOf("github-issue", "#236"),
  refWithoutRepository: issueReferenceOf("github-issue", "236"),
  looksLikeARepo: issueReferenceOf("github-issue", "manibo-G1-gh192"),
  namesTracker: {
    githubIssue: namesAnIssueTracker("github-issue"),
    dogfoodGap: namesAnIssueTracker("dogfood-gap"),
    missionControlRequest: namesAnIssueTracker("mission-control-request"),
  },
};

process.stdout.write(
  JSON.stringify(
    { sources: DECLARED_SOURCES, rail: RAIL, newTicket: NEW_TICKET_INERT, projects, issues },
    null,
    2
  )
);
