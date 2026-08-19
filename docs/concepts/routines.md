# Routines

A **routine** is a versioned definition of scheduled system work. A **routine occurrence** is the saved result
of considering one scheduled time. The occurrence is durable, so a process restart or a repeated scheduler
scan cannot turn one due time into duplicate truth.

## Why routines exist

Recurring work must survive restarts, time-zone transitions, and missed schedule times. A routine revision
records its schedule, time zone, catch-up rule, concurrency rule, timeout, and immutable component references.
Migrated work-item revisions carry the immutable document ID of a registered Knowledge snapshot instead of
instruction text. The scheduler records every considered occurrence, including a skipped occurrence.

The scheduler handles missing and repeated civil times explicitly. A revision can skip missed work, coalesce it
into one latest occurrence, or enqueue a bounded number of missed occurrences, as its catch-up rule declares.

## What runs today

Ctower currently contains twelve fixed routine definitions:

- a daily synthetic four-stage check;
- a daily backup definition;
- an hourly record-anchor definition;
- four nightly review definitions for project and portfolio views;
- five activity-gated definitions covering two operator-facing report schedules, one watcher, one janitor,
  and one capacity sentinel.

The scheduler records occurrences for these definitions. The five migrated definitions append one
pointer-only Inbox work item per
fire, carrying the gate evidence and watermark plus the immutable Knowledge document ID, with no session-targeted instruction.
The item remains open until a receipt references the delivered artifact. Correcting a definition creates a new
revision and leaves older revisions, occurrences, effects, and work-item facts as history.

## Activity-gated routines

An activity gate is a small typed rule evaluated inside the scheduler before a dispatch effect or Inbox work item
is emitted. Registration is pack-driven: an authored pack fixes the routine reference, schedule, gate, delivery
shape, and revision digest. There is no general expression language, script gate, or product gate editor.

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

- **Fired** — the occurrence is `queued` and one pointer-only Inbox work item is emitted.
- **Skipped** — the occurrence is visible with outcome `skipped`, no work item is emitted, and the saved
  reason explains why the gate did not pass.
- **Degraded** — the activity read could not be established. The evaluation is recorded as `degraded`, the
  occurrence is visible as skipped, and no clean dispatch is emitted.

A work item carries the immutable Knowledge document ID, gate evidence, and delivery window; it is closed only by a receipt
naming the delivered artifact. A fire or open item is evidence that the routine fired, not evidence that external
work completed successfully.

Suppression is independent of the gate. A routine whose previous work item is still open and receiptless is
suppressed on its next fire whatever gate it carries, and the suppression fact names the blocking item. There is
no gate that exempts a routine from the one-open-item rule.

## Missed and degraded windows

Every window has one append-only alarm episode, identified by the tenant, the routine revision digest, and the
scheduled instant. The episode records typed observations and its state is read back from them; it is never
stored as an editable field.

| Observation | When it is appended |
|---|---|
| `degraded_read` | The item state could not be read completely. The episode opens degraded rather than reporting a clean no-alarm. |
| `missed_window` | The window ended with no accepted receipt. This is the one ordinary alarm, at most once per window. |
| `recovered_receipted` | A receipt was accepted while the episode was still open. The episode resolves with no ordinary alarm. |
| `escalation_unresolved` | The escalation binding did not resolve to a live seat in scope. No delivery is claimed. |

The escalation seat comes from the active routine revision, never from the caller. At alarm time it is resolved
against the registered project seats in the owning seat's project. A binding that is missing, stale (its routine
has no active revision), revoked, or in a foreign project scope appends `escalation_unresolved` with that reason
instead of the ordinary alarm; once the binding resolves again, the next scan appends the ordinary alarm.

Repeated scans, a scheduler restart, and concurrent boundary attempts add no second episode and no second
ordinary alarm. Degraded and recovery observations are not ordinary alarms and are never counted as one.

## Catch-parity during migration

When an existing host schedule is being replaced, the host schedule remains active until the registered routine
has a recorded queued occurrence and the external custodian has captured both sides of the catch-parity proof.
That fire-once evidence is needed before the old schedule may be removed.

Ctower can prove its own fire fact from the routine occurrence, Inbox work item, and receipt. It
cannot observe whether the host schedule is still active or whether it was deleted. The parity-report emitter
that would combine those two observations is admitted shim debt; a test helper is not that report. An external
custodian must confirm the host-side fact and perform the deletion. Until then, the host schedule continues to
run.

## Inspecting and retiring routines

There is no general routine editor, registration command, or session-dispatch CLI. Routine work is consumed from
the existing Inbox and closed by its typed artifact receipt.

Treat routines as scheduled system work, not as tickets edited from the Board. If a routine creates or checks
ticket work, the resulting saved ticket facts remain the source of truth.
