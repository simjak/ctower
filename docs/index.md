# ctower

ctower is a control plane for work that outlives the thing doing it.

An agent's terminal dies mid-task. A model session hits its context limit and is replaced. A laptop goes to
sleep, a container is evicted, a vendor API times out. When the state of the work lives inside the process
doing the work, the process ending takes the answers with it: who owns this, how far did it get, and is the
claim that it passed actually true?

ctower holds those facts outside the worker, in a database behind one authenticated, idempotent, append-only
write path. The worker becomes replaceable. The record does not.

!!! warning "Pre-alpha: read this before you plan anything"
    Version `0.0.0`. There is **no supported installation, deployment, published package, or hosted
    service**, no browser UI, and no runner. What exists is a tested development slice plus its verification
    gates. See [What you can and cannot do today](#what-you-can-and-cannot-do-today).

## The problem it solves

Three failures, in order of how much they cost:

1. **Lost custody.** Work is assigned to a session, not a principal. When the session disappears nobody is
   accountable, and nobody can tell whether the work is stalled or finished.
2. **Unverifiable claims.** A worker reports "done". The report is prose. Nothing binds that claim to the
   exact artifact it was made about, so a later change silently invalidates it and no one notices.
3. **Untracked side effects.** A command is dispatched to merge, deploy, or send. The dispatch is recorded
   as if it were the outcome. When the external system disagrees, the record is already wrong.

ctower answers each with a durable fact rather than a convention: one accountable custodian interval per
ticket, evidence bound to an exact candidate digest, and desired state reconciled against observed state.

## The core model

Five things, in the order work moves through them:

```text
  intake            ticket             workflow            proof            projections
 ┌────────┐      ┌──────────┐      ┌────────────┐     ┌────────────┐     ┌─────────────┐
 │ inbound│─────>│ permanent│─────>│ pinned     │────>│ criteria + │────>│ Board       │
 │ thread │ promo│ identity │ start│ stage graph│ gate│ evidence + │ fold│ Project     │
 │        │ -tion│ + custody│      │ + policies │     │ verdict    │     │ Delivery    │
 └────────┘      └──────────┘      └────────────┘     └────────────┘     └─────────────┘
   shipped          shipped            shipped            shipped            shipped
```

- A **[ticket](concepts/tickets.md)** is the permanent case file for one promised outcome. Its ID never
  changes. Exactly one custodian is accountable at any moment. Its Kanban status and its workflow stage are
  separate facts, so "blocked" and "in the design stage" can both be true.
- A **[workflow revision](concepts/workflows.md)** is an immutable stage graph, and an **execution policy**
  says who may execute or review within it. Both are versioned *data* loaded from a pack. The engine has no
  built-in engineering stages: the software factory is one workflow package, not the product.
- **[Proof](concepts/proof.md)** is what makes "done" checkable. Criteria are frozen against a candidate
  digest, evidence is bound to that same digest, and an *independent* principal records the verdict — the
  author cannot pass their own work. Change the candidate and the evidence that depended on it stops
  counting. At this revision current proof is what the move into the final stage requires, and what
  resolving and closing a ticket require; every stage carrying its own proof requirement, expressed as typed
  evidence *slots*, is required by `SPEC.md` and not implemented (see
  [Proof](concepts/proof.md#typed-evidence-slots)).
- **[Projections](concepts/board.md)** — the Board and [Project Delivery](concepts/project-delivery.md) —
  are read-only folds of those facts, carrying their own watermark and freshness so a stale read announces
  itself instead of lying.
- **[Durability](concepts/durability.md)** is explicit at the API boundary. A write that is committed here
  but not yet acknowledged on another host says exactly that — "committed, acknowledgement pending" — rather
  than reporting a success it cannot guarantee.

Inbound threads are implemented: an authenticated caller can submit an inbound event and promote it into a
linked ticket, and re-sending the same promotion returns the same ticket instead of a second one. Tickets
can still be created directly. What does **not** exist is anything that feeds intake automatically — no
email, chat, or webhook connector — so in practice something has to call it. Everything else in that chain
runs in the development slice.

## What you can and cannot do today

| You want to | Today |
|---|---|
| Read the design and the contracts | Yes — `SPEC.md`, `contracts/`, and this site |
| Verify a checkout end to end | Yes — [`just check` and `just verify`](quickstart.md) |
| Watch a ticket go capture → resolved/closed against real PostgreSQL | Yes, inside the acceptance gate — see the [Quickstart](quickstart.md) |
| Call the HTTP API or drive `ctowerctl` against your own instance | Not yet — no supported way to stand an instance up from this revision |
| Install, deploy, or host ctower | No |
| Use a browser UI, a runner, or a remote agent adapter | No — browser work starts at a later planned stage, which the roadmap calls `CT-I2-005` / I2.4 |
| Put real tenants, credentials, or work into it | No |

Nothing here is a stability promise: the HTTP surface is a development contract, not a supported external
API, and there is no compatibility guarantee between revisions.

## Where to go next

- **[Quickstart](quickstart.md)** — clone, verify, and watch a first ticket run the full four-stage
  lifecycle.
- **[Concepts](concepts/index.md)** — the vocabulary the contracts, CLI, and audit trail actually use.
- **[Reference](reference/cli.md)** — every CLI command and HTTP operation, derived from the authored
  contracts.
- **[For agents](agents/operating-contract.md)** — idempotency, expected-version, exit codes, and how to
  read a refusal instead of retrying blindly.
- **[Advanced and internals](internals.md)** — the engineering record: delivery state, verification
  evidence, operational boundaries, specification, and decision log.
