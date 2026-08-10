# Requests

A **Request** is the permanent record of operator intent and its outcome. It answers “what did we ask for,
and has the outcome been proved?” A **Ticket** answers the different question “what executable work is being
done?” One Request may have no Ticket yet, or may relate to several required and optional Tickets.

## Identity and capture

Every Request has a canonical UUIDv7 identity and a tenant-wide permanent `R<number>` reference. The server
allocates both. The client supplies only an authorized project, text, and an idempotency key; it cannot claim
the submitter, owner, source, priority decision, state, relation, or acceptance.

Capture is intentionally small. It records the inbound provenance, Request, initial owner, `P2` safety
default, `UNTRIAGED` fact, command result, event, and outbox atomically. It creates no Ticket and waits for no
analysis. Replaying the same key and content returns the same Request. Reusing the key with different content
is refused.

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

## Honest reads

The Phase 1 Request read is read-only, carries a Record watermark and freshness, and excludes pending
commands from accepted rows. Its PostgreSQL authority query either answers every requested Project or
refuses the read; it does not yet fan out across independently fallible projection sources. The response
shape names requested, answered, and unanswered Projects so Phase 2 can add that fan-out without turning an
unreachable or stale Project into an empty count.

Phase 1 exposes this authority through generated HTTP clients and the protected seat CLI in disposable
verification tenants. Portfolio authority still requires the separately observed one-way epoch: frozen
source, reviewed mappings, signed manifest, full reconciliation, old-writer fence/removal, and a first
capture above the sealed high-water. The existing-identity browser send box, contextual Board rendering, and
partial-source epistemic fold belong to Phase 2; Slack/Hermes remains outside both until its separate security
decision and CSO gate.

See the [CLI reference](../reference/cli.md#requests) and
[HTTP API reference](../reference/http-api.md#requests) for exact commands and operations.
