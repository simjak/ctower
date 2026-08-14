# Routines

A **routine** is a versioned definition of work that becomes due on a schedule. A **routine occurrence** is
the saved result of one scheduled time being considered.

## Why routines exist

Recurring work must survive process restarts and clock edge cases. Ctower records the routine version, time
zone, next fire time, catch-up rule, concurrency rule, timeout, and occurrence. A duplicate scheduler scan
does not create duplicate truth.

The scheduler handles missing and repeated civil times explicitly. It can skip missed work, coalesce it
into one latest occurrence, or enqueue a bounded number of missed occurrences, as the routine declares.

## What runs today

The repository contains twelve fixed routine definitions:

- a daily synthetic four-stage check;
- a daily backup job definition;
- an hourly record-anchor job definition; and
- four nightly review routines for project and portfolio views; and
- five fixed maintenance beats for health, migration, monitoring, sprint reconciliation, and a daily
  decision digest.

The scheduler records occurrences for the fixed maintenance definitions. Their real backup, anchor, and
synthetic effects are not all active product operations. The nightly routines emit scoped dispatch effects.
Each maintenance beat copies its complete instruction into an immutable revision, then emits that same
instruction with the occurrence. Delivery therefore cannot drift if source text changes after registration.
A corrected digest serially replaces only the tenant's active trigger; older revisions, occurrences, and
effects remain immutable history.

An operator can terminally retire one exact versioned maintenance beat. Ctower appends a retirement fact and its
canonical command, event, and outbox lineage, removes only that beat's active trigger, and preserves every
revision, occurrence, effect, and unrelated trigger. Later registration ticks do not reactivate it, and a
database guard also blocks trigger inserts from an older application binary after rollback.

## How to use routines

There is no general routine editor or general retirement surface today. Operators inspect the registered
maintenance subset with `beat-dispatch routines`, list pending immutable effects with `beat-dispatch list`, retire
one exact versioned beat with `beat-dispatch retire`, and use the exact dream commands for dream effects.
All three beat commands are operator-only. Ctower records the schedule and effect; an external consumer
owns delivery into the target session and its append-only delivery ledger.

New users should treat routines as scheduled system work, not as tickets they can edit from the Board. If a
routine creates or checks ticket work, the resulting saved facts remain the source of truth.
