# Request-maintenance proposals

A Request-maintenance proposal is an immutable suggestion about an existing Request. It lets a maintainer
surface likely duplicate work, completed work that remains open, supersession, kill, or keep judgment
without quietly changing the Request. The proposal queue is an operator review surface, not writable
Request state.

## A proposal is not a Request change

Appending or ranking a proposal creates its own proposal identity, event, evidence facts, and durability
result. The target Request keeps the same identity, text, version, disposition, relations, blockers, and
proof links. Pending proposals are absent from accepted reads. Similarity can create only an uncertain
duplicate proposal; it is never authority to merge, alias, overwrite, or triage Requests.

The five kinds are:

- `duplicate`: the target may repeat a second independently preserved Request.
- `completed-but-open`: accepted proof may support an ordinary closure evaluation.
- `supersession`: one exact Request may supersede another, while both identities and texts remain.
- `kill`: an operator may reject the target through ordinary Request triage.
- `keep`: an operator may accept the target through ordinary Request triage.

## What a proposal must contain

Every append names the target Project, Request UUID, observed Request version, byte-exact Request text,
source Record watermark, and at least one typed stable evidence pointer. Ctower derives the proposer from
the authenticated Actor; a caller cannot claim it. A duplicate or supersession also names the related
Request UUID/version and quotes its exact text. Ctower re-reads both records and refuses missing or altered
quotes before appending anything.

Evidence pointers are either an accepted canonical Record event with its UUID, kind, and digest, or an
accepted proof-evidence identity with Ticket, proof, evidence, and artifact digest. Semantic resemblance is
not delivery proof. A completed-but-open proposal without accepted proof remains `OPEN` with
`completion-unproven`.

## Ambiguity is an answer

An open row can record exactly one of five reasons:

- `evidence-conflicting-or-incomplete`
- `duplicate-uncertain`
- `supersession-unclear`
- `target-version-stale`
- `completion-unproven`

Ctower does not turn missing information into success. Correct the source facts by appending new evidence,
then make an explicit decision. The original proposal and ambiguity remain historical facts.

## Confirming and rejecting

Only the authenticated existing operator can confirm or reject. Rejection records operator identity,
server time, and an optional bounded reason; it derives `REJECTED` while preserving the proposal, evidence, quotes,
and target. Terminal proposals cannot reopen or receive a second decision.

Confirmation is one proposal decision plus one separately identified ordinary Request command in the same
transaction. The target command has its own idempotency identity, expected version, authority check, event,
result, and durability lifecycle. Before a duplicate or supersession command, Ctower re-proves both exact
Request texts and stable identities. The proposal decision honestly reports whether that target command was
accepted or refused; a refusal leaves the Request unchanged.

Direct Request triage uses the same protected path for an operator or Commander. Proposal confirmation does
not impersonate a Commander, mint a principal, or bypass normal Request policy.

## Reviewing the top 20

The operator-only review contains at most one row for each Request targeted by an open proposal. It ranks
those Requests by active Catalog Goal relation, recorded open operator-decision requirement, older Request
creation time, then stable Request UUID. Multiple proposals cannot duplicate a Request in the view; if
their Request source facts conflict, the stable smallest proposal identity is retained as the pointer and
the view is marked partial. Missing or conflicting Goal/Project Catalog facts likewise stay `unknown` and
mark the view partial. The fixed limit is 20; callers cannot supply a relevance score or flag.

The morning digest embeds only counts by kind and terminal state, the review pointer, source watermark,
and named incomplete scopes. Partial or unavailable sources expose `UNKNOWN` counts rather than false
zeroes, and an unavailable source does not claim a watermark. It never embeds a proposal row, Request row,
identity, quote, or evidence.

See the [CLI reference](../reference/cli.md#request-maintenance-proposals) and
[HTTP API reference](../reference/http-api.md#request-maintenance-proposals).
