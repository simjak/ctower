# Requests

A **Request** is the permanent record of operator intent and its outcome. It answers “what did we ask for,
and has the outcome been proved?” A **Ticket** answers the different question “what executable work is being
done?” One Request may have no Ticket yet, or may relate to several required and optional Tickets.

## Identity and capture

Every Request has a canonical UUIDv7 identity and a tenant-wide permanent `R<number>` reference. The server
allocates both. The client supplies only an authorized project, text, and an idempotency key; it cannot claim
the submitter, owner, source, priority decision, state, relation, or acceptance.

Capture is intentionally small. It records the inbound provenance, Request, initial owner, `P2` safety
default, `UNTRIAGED` fact, command result, event, and outbox atomically. Before that write completes, Work
compares the text with accepted open Requests in the same Project using one deterministic local hashed-
subword vector. It records at most the strongest resemblance at or above the authored threshold. The new
Request is always captured; no resemblance silently drops or merges it. A qualifying result speaks in the
acknowledgement: `captured as R-new, resembles R-old (status), linked — say same to merge.` It creates no
Ticket. Replaying the same key and content returns the same Request and acknowledgement. Reusing the key with
different content is refused.

The comparison normalizes Unicode and case, derives word, adjacent-word, and character-ngram features,
hashes them with SHA-256 into a fixed vector, and compares cosine similarity. It needs no model download,
service, secret, process, network call, or external egress. This is one bounded Request-capture capability,
not a general corpus search or fuzzy-dedupe service.

“Committed here” and “accepted off host” are different. A pending response preserves the permanent command
identity but does not enter accepted Request totals. The protected CLI keeps that command in its encrypted
spool and retries the same key. Read [Durability](durability.md) for the acknowledgement model.

## Independent facts and derived state

Triage is `UNTRIAGED`, `ACCEPTED`, `DUPLICATE`, or `REJECTED`. Priority, accountable owner, Ticket relations,
blockers, and closure evaluations are separate append-only facts. Every change names the Request version it
observed; a stale change is refused rather than overwriting newer judgment.

The operator state is derived in this order:

1. `DONE` when the latest closure evaluation still matches all current dependencies.
2. `BLOCKED` when a current Request or required-Ticket blocker prevents the outcome.
3. `WIP` when an accepted Request has required Ticket work in progress.
4. `TRIAGED` when a disposition exists but no higher state applies.
5. `NEW` otherwise.

A later relation, blocker, proof invalidation, or canonical-Request change can invalidate an old closure
evaluation. This is why no client edits a Request status directly.

## Resemblance and explicit merge

Accepted reads expose a persisted resemblance from both Requests without altering either original. Only
accepted open same-Project Requests are capture candidates; done, duplicate, rejected, pending, or foreign-
Project Requests are excluded. An unrelated capture carries no link.

`request same <new_request_id> --expected-version <version>` is an operator-only explicit merge instruction.
The accepted persisted link determines the canonical Request; the caller cannot substitute another. It
appends DUPLICATE triage to the newer Request and immutable
merge provenance containing both Request identities and numbers, exact verbatim texts and their digests,
capture timestamps, trigger wording, Actor, command, and acceptance time. It does not edit or delete either
Request. Commander duplicate triage records the same provenance; no other path may merge a resemblance.
Pending commands do not expose merge provenance, and an accepted merge removes that pair from the open set.

## Decision briefs

The exact active blocker key `operator-decision-required` makes the accepted Request read include a complete
operator ask. Ctower derives its plain explanation, exact Request-content quote, three outcome choices and
their completeness scores, recommendation, safe default, and ready-to-send text from accepted Request facts.
Callers cannot submit or override any brief field. Requests without that blocker return
`decision_brief: null`.

The safe default is to leave the Request blocked. An answer is an accepted Ruling linked to the Request.
Pending Rulings do not change the accepted brief. After acceptance, the brief cites the Ruling and becomes
`answered`; that exact decision occurrence no longer affects derived state, while every unrelated blocker
still does. A later active decision marker opens a new brief and cannot reuse the older answer. Deactivating
the latest marker removes the brief. See [Rulings](rulings.md#answering-a-request-decision).

## Honest reads

The Phase 1 Request read is read-only, carries a Record watermark and freshness, and excludes pending
commands from accepted rows. It exposes accepted resemblance links in both directions and merge provenance
only after accepted merge. Its PostgreSQL authority query either answers every requested Project or refuses
the read; it does not yet fan out across independently fallible projection sources. The response shape names
requested, answered, and unanswered Projects so Phase 2 can add that fan-out without turning an unreachable
or stale Project into an empty count.

Phase 1 exposes this authority through generated HTTP clients and the protected seat CLI in disposable
verification tenants. Portfolio authority still requires the separately observed one-way epoch: frozen
source, reviewed mappings, signed manifest, full reconciliation, old-writer fence/removal, and a first
capture above the sealed high-water. The existing-identity browser send box, contextual Board rendering, and
partial-source epistemic fold belong to Phase 2; Slack/Hermes remains outside both until its separate security
decision and CSO gate.

See the [CLI reference](../reference/cli.md#requests) and
[HTTP API reference](../reference/http-api.md#requests) for exact commands and operations.
