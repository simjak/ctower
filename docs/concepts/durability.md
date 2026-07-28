# Durability and acceptance

An API usually has two answers: it worked, or it failed. ctower has three, because there is a real state in
between — committed here, not yet safe anywhere else — and reporting it as success would be a lie.

| State | Meaning |
|---|---|
| `accepted` | The write is committed **and** acknowledged by a standby outside this process |
| `durability_pending` | The semantic result is committed here; the off-host acknowledgement has not landed |
| refused | Nothing was written |

`durability_pending` is not an error and not a maybe. The command *happened*. What has not happened is the
acknowledgement that would let you survive losing this host.

## Why this is at the API boundary

If a control plane returns `200 OK` the instant it commits locally, then every caller downstream believes
something the system cannot actually guarantee. Losing the host silently un-does work that was reported as
done, and the record you were relying on to be authoritative is the thing that was wrong.

Surfacing the pending state means a caller can decide for itself: proceed optimistically, or wait for
acceptance before triggering an external effect.

## What you see at each layer

**HTTP.** A mutation returns `201`/`200` when the write is accepted off host, and `202` when it is
committed but pending, with the description *"Semantic result committed; off-host durability acknowledgement
pending"*. A `202` carries a `Retry-After` header — an integer between 1 and 60 seconds — telling you when
to replay the same idempotency key.

**Resources.** `TicketResource` carries a required `durability_state` field, so a later read tells you
whether the fact ever reached `accepted`.

**CLI.** A pending mutation exits **`75`** and prints `"state":"queued"` with
`"reason_code":"durability_pending"`. An accepted one exits `0` with `"state":"accepted"`.

```json
{"command_id":"...","reason_code":"durability_pending","sequence":1,"state":"queued"}
```

Exit `75` does not mean accepted, and it does not mean failed. See
[the agent operating contract](../agents/operating-contract.md) for what to do next — the short version is
replay the same `--command-id`, never a new one.

## How acceptance is defined

`contracts/operations/durability-policy.schema.json` pins it exactly:

| Field | Value | Meaning |
|---|---|---|
| `mode` | `pending_only` or `cutover_rpo0` | Whether acceptance is expected at all |
| `synchronous_commit` | `remote_apply` (fixed) | Postgres must confirm the standby applied, not merely received |
| `standby_count` | `1` (fixed) | Exactly one acknowledging standby |
| `standby_application_name` | `ctower_i1_ack` (fixed) | The standby's identity is named, not inferred |
| `commit_deadline_ms` | 100–30000 | How long a commit waits for the acknowledgement |
| `retry_after_seconds` | 1–60 | What the server puts in `Retry-After` |

`remote_apply` is the strong choice: acknowledgement means applied, not just written to the standby's disk.

## Getting from pending to accepted

A ticket that returns `durability_pending` becomes `accepted` when the acknowledgement arrives and a
finalizer records it. That is a background transition, not something the caller performs. Replaying the
exact command afterwards returns the accepted result rather than creating a second ticket.

If replication stalls, writes keep returning `durability_pending` honestly for as long as the stall lasts.
The system does not fabricate acceptance to keep a graph green.

## Health reporting

`GET /health` returns a `ctower.health/v1` snapshot with a status of `HEALTHY`, `DEGRADED`, or
`STATE_UNKNOWN` across three dimensions — availability, completeness, integrity — each carrying named
contributors (`durability`, `scheduler`, `outbox`, `projection`, `backup`, `anchor`, `object`, `synthetic`)
with a watermark, a threshold, an owner, and a reason.

`STATE_UNKNOWN` is a first-class value throughout ctower. "I cannot establish this" is reported as itself
rather than being rounded down to healthy or up to broken.

## What is proven at this revision

The ordinary development configuration is **`pending_only`**: writes return `durability_pending` and stay
there. That is the expected result in the acceptance suite, not a misconfiguration.

Acknowledged durability — a real primary/standby pair reaching `accepted` — is exercised by a verifier-owned
PostgreSQL topology in the test suite. That is proof of the mechanism, not a supported deployment: there is
no operator path to configure it, no second failure domain, and no backup or restore promise. The
[Project Delivery](project-delivery.md) view says the same thing in its own words: the disaster-recovery
checkpoint is not proven.

`cutover_rpo0` is declared in the policy schema and is **not** enabled.

## Related

- [The agent operating contract](../agents/operating-contract.md) — replay rules and exit codes.
- [Project Delivery projection](project-delivery.md) — where `durability` and `recovery` are reported.
- [Current operational boundary](../operations/current-boundary.md) — what the deployment story is not.
