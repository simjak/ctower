# Ticket and lifecycle episode

A ticket is the permanent case file for one promised outcome. It is the only thing in ctower that never
loses its identity: not when the assignee changes, not when the model is swapped, not when the workflow
revision is migrated, not when the work is reopened a year later.

## Why identity is the primitive

If work identity lives in a session, a branch name, or a chat thread, then every question about
accountability becomes archaeology. ctower fixes identity first and derives everything else from it, so
"who owns this now?" and "did this actually pass?" have single-row answers.

`INV-06` states it directly: ticket IDs never mutate when type, department, owner, workflow, or lifecycle
episode changes.

## The ticket resource

A read of `GET /v1/tickets/{ticket_id}` returns exactly these fields — the contract forbids extras:

| Field | Type | Meaning |
|---|---|---|
| `ticket_id` | UUID | Permanent identity |
| `title` | string | Human label |
| `priority` | `P0` \| `P1` \| `P2` | Requested urgency; `P0` requires policy evidence and authority |
| `source` | `{kind, ref}` | Where the work came from; both parts are required |
| `custodian_id` | UUID | The one principal accountable right now |
| `version` | integer ≥ 1 | Aggregate version, used for optimistic concurrency |
| `created_at` | timestamp | Creation time |
| `durability_state` | `durability_pending` \| `accepted` | Whether the write is acknowledged off-host. The contract allows both; the stored column is constrained to `durability_pending`, so a read returns that — see [Durability](durability.md) |

`version` is not decoration. Every mutating command that changes the ticket carries
`--expected-version`, and a mismatch is refused as `version-conflict` with the server's `current_version`
in the problem body. See [the agent operating contract](../agents/operating-contract.md).

## Four things that are deliberately separate

Collapsing these is the mistake ctower is built to avoid:

| Fact | Answers | Where it lives |
|---|---|---|
| **Lifecycle** | Is the promised outcome open, active, waiting, or closed? | Ticket episode |
| **Workflow stage** | Which pinned stage is being evaluated? | [Workflow run](workflows.md) |
| **Board lane** | Where does this appear in the cross-ticket index? | [Board projection](board.md) |
| **Custody** | Who is accountable, right now, with no gap? | Assignment interval |

A ticket can be `blocked` on the Board while its workflow stage is `implement` and its lifecycle is
`active`. All three are true at once, and none of them overwrites another.

## Lifecycle episode

A **lifecycle episode** is one open-to-terminal interval on a ticket: an opening event, an outcome, and the
resolution, closure, or cancellation facts that ended it.

Four episode states are reachable at this revision. `ticket create` opens an episode as `open`,
`ticket admit` moves it to `active`, `ticket defer` moves it to `waiting`, and `ticket resolve` moves it to
`closed` while appending the two lifecycle facts `resolved` and `closed` in one transaction.

- `resolved` is a lifecycle fact, not an episode state, and it means exactly one thing here: the
  `proof.current@1` predicate held when resolve-close ran. Gates and a delivery contract are part of the
  specified meaning and are not evaluated — see [Proof](proof.md#verdicts-and-independence).
- `closed` means administratively complete.
- `cancelled` — meaning intentionally stopped without the promised outcome — is declared in the schema and
  read by the terminal-state checks, but **nothing writes it**. There is no cancel operation, CLI command,
  or kernel command at this revision.

Reopening does **not** rewrite history. `reopened` closes no prior record; it starts episode N+1 on the same
permanent ticket, records the reason and the prior episode, and appends that episode's initial priority
under explicit carry-forward policy. The earlier resolution evidence stays exactly as it was.

This is why "reopened" is an event and not a status: a status would imply the old outcome had been edited.

## Custody

`INV-09` requires exactly one current custodian interval — no gap, no overlap — for every actionable episode
that is not closed or cancelled.

What the transfer transaction does, in `packages/ctower-kernel/src/ctower_kernel/record/_custody_sql.py`:

- **Eligibility is enforced.** The incoming custodian must be an enabled principal of kind `commander` or
  `operator` in the same tenant. A stage executor, collaborator, reviewer, runner, model session, or
  provider handle is not one of those kinds and is refused.
- **The interval is replaced atomically.** One `UPDATE` releases the outgoing custodian's open interval and
  one `INSERT` opens the incoming custodian's, in the same transaction, and the transfer fails hard if
  exactly one interval was not released.
- **It is version-guarded and origin-guarded.** A stale `--expected-version`, a `--from-custodian-id` that
  is not the current custodian, a transfer to the principal who already holds custody, or a ticket in a
  terminal state are each refused without writing anything.
- **It appends one event.** A `CUSTODY_TRANSFERRED` event carrying `from_custodian_id`, `to_custodian_id`,
  and `reason` joins the ticket's hash-chained trail.
- **Close releases it.** Resolve-and-close releases the custodian interval in the same transaction that
  appends the `resolved` and `closed` facts.

Because of this, custody transfer is a protected command: `ticket custody transfer` requires the explicit
`--protected-transfer` flag alongside both principal IDs, and it is a different operation from an ordinary
assignment change.

!!! warning "Specified, not implemented at this revision"
    Transfer is specified to do more than move the interval: fence the outgoing Commander's reasoning
    lease, record a context handoff, and dispatch no new work until the incoming custodian has rehydrated
    it. No reasoning lease, handoff payload, or work-dispatch barrier exists in this revision — a transfer
    replaces the interval and appends its event, and that is all.

    `SPEC.md` also separates `resolved` from administrative close, so that custody survives resolution until
    a distinct close or cancellation. Here there is no separate resolve command and no cancellation command
    at all: `ticket resolve` calls one operation that appends `resolved` and `closed` together and releases
    custody in the same transaction.

## Assignments versus custody

Assignments are the working roles; custody is the accountability. The assignment kinds are
`ticket_custodian`, `current_assignee`, `stage_owner`, `reviewer_assignment`, and `runner_lease_owner`, of
which only `current_assignee`, `stage_owner`, and `reviewer_assignment` are mutable through
`ticket assign`. The CLI spells the last one `--kind reviewer`.

Assignment intervals are not bookkeeping: in the specified stage-sign-off rule the signature is derived from
the verifier's assignment interval, so an expired assignment invalidates it. See
[sign-off](proof.md#sign-off-names-exactly-one-accountable-party).

## Intents

Five commands change what the ticket is *asking for* rather than what it contains. All five map to one
operation, `POST /v1/tickets/{ticket_id}/intents`:

| Command | Meaning |
|---|---|
| `ticket admit` | Accept the ticket into active work |
| `ticket defer` | Push it out until `--review-after` (a timestamp that must carry a UTC offset) |
| `ticket block` | Open a typed blocker — one of `dependency`, `operator_action`, `policy`, `resource`, `technical` — with an owner, a resolution condition, and an explicit `--board-impact` / `--no-board-impact` choice |
| `ticket unblock` | Resolve a specific blocker with `--resolution-evidence-ref` |
| `ticket reopen` | Start a new lifecycle episode |

An intent whose precondition is not met is refused as `work-intent-unmet` rather than silently ignored.

## Relations

`ticket relation add` links tickets with one of `parent_of`, `depends_on`, `blocks`, `duplicates`,
`relates_to`, `caused_by`. Cycles are refused (`work-relation-cycle`), and a duplicate link is refused
(`work-relation-exists`) rather than quietly deduplicated.

## Reading the trail

Three reads, all `GET`, all free of side effects:

- `ticket timeline` — the ordered typed event trail.
- `ticket audit` — the paged audit events, with `--cursor` and `--limit` (max 100).
- `ticket assignments` — current and historical assignment intervals.

The audit trail is append-only and hash-chained. It is the thing you read when a claim and a projection
disagree.

## Related

- [Workflow revision and execution policy](workflows.md) — what moves the ticket between stages.
- [Proof](proof.md) — what has to be true before it can resolve.
- [CLI reference](../reference/cli.md) — every ticket command and flag.
