# Routines

A **routine** is a versioned definition of scheduled system work. A **routine occurrence** is the saved result
of considering one scheduled time. The occurrence is durable, so a process restart or a repeated scheduler
scan cannot turn one due time into duplicate truth.

## Why routines exist

Recurring work must survive restarts, time-zone transitions, and missed schedule times. A routine revision
records its schedule, time zone, catch-up rule, concurrency rule, timeout, instruction, and immutable component
references. The scheduler records every considered occurrence, including a skipped occurrence.

The scheduler handles missing and repeated civil times explicitly. A revision can skip missed work, coalesce it
into one latest occurrence, or enqueue a bounded number of missed occurrences, as its catch-up rule declares.

## What runs today

Ctower currently contains seventeen fixed routine definitions:

- a daily synthetic four-stage check;
- a daily backup definition;
- an hourly record-anchor definition;
- four nightly review definitions for project and portfolio views;
- five fixed maintenance definitions; and
- five activity-gated definitions covering two operator-facing report schedules, one watcher, one janitor,
  and one capacity sentinel.

The scheduler records occurrences for these definitions. Their saved schedule and dispatch facts are product
truth; an external consumer is responsible for delivering a dispatch instruction, and delivery or completion
is not inferred from the schedule. Each dispatch copies its complete instruction into an immutable revision so
delivery cannot drift when source text changes later. Correcting a definition creates a new revision and leaves
older revisions, occurrences, and effects as history.

## Activity-gated routines

An activity gate is a small typed rule evaluated inside the scheduler before a dispatch effect is emitted.
Registration is pack-driven: an authored pack fixes the routine reference, schedule, gate, dispatch
instruction, target, and revision digest. There is no general expression language, script gate, or product gate
editor.

The activity-gate set is closed:

| Gate | When the due occurrence may fire |
|---|---|
| `always` | Every due schedule is allowed to fire. |
| `new_movement_since_watermark` | The selected activity source has new rows after the saved watermark. The first evaluation is a baseline and fires when it observes the source. |
| `open_tickets_above` | The number of nonterminal tickets is greater than the typed threshold. An optional project key limits the count to one project. |

Movement gates read either the event or ticket activity source. Ticket-count gates read tickets only. Gate
parameters are validated as typed values; arbitrary SQL, expressions, and commands are not accepted.

Every evaluation writes an append-only fact containing the gate kind, result, watermark kind and position,
observed count, detail, and evaluation time. The result has one of three meanings:

- **Fired** — the occurrence is `queued` and one immutable beat-dispatch effect is emitted.
- **Skipped** — the occurrence is visible with outcome `skipped`, no dispatch effect is emitted, and the saved
  reason explains why the gate did not pass.
- **Degraded** — the activity read could not be established. The evaluation is recorded as `degraded`, the
  occurrence is visible as skipped, and no clean dispatch is emitted.

An emitted effect carries the immutable instruction and its digest. It is evidence that the routine fired, not
evidence that an external command completed successfully.

## Catch-parity during migration

When an existing host schedule is being replaced, the host schedule remains active until the registered
routine has a recorded queued occurrence. That is the fire-once evidence needed before the old schedule may be
removed.

Ctower can prove its own fire fact from the routine occurrence and dispatch effect. It cannot observe whether
the host schedule is still active or whether it was deleted. The parity-report emitter that would combine
those two observations is admitted shim debt; a test helper is not that report. An external custodian must
confirm the host-side fact and perform the deletion. Until then, the host schedule continues to run.

## Inspecting and retiring routines

There is no general routine editor or registration command. Use the CLI reads to inspect the active definitions
and immutable effects:

```console
ctl beat-dispatch routines
ctl beat-dispatch list
```

An operator can terminally retire one exact versioned routine. Retirement removes only its active trigger and
preserves the revision, occurrences, effects, and unrelated routines. Later registration ticks and older
application binaries cannot restore the retired trigger:

```console
ctl beat-dispatch retire <routine_ref> --command-id <uuid>
```

Treat routines as scheduled system work, not as tickets edited from the Board. If a routine creates or checks
ticket work, the resulting saved ticket facts remain the source of truth.
