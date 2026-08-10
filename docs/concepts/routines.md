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
- four nightly dream routines, one for each project view and one for the whole portfolio; and
- five fleet-beat routines: UTC cadences for health, migration, and bh-loop monitoring, plus
  Europe/Vilnius civil-time schedules for sprint reconciliation and the operator morning digest.

The scheduler records occurrences for the fixed maintenance definitions. Their real backup, anchor, and
synthetic effects are not all active product operations. The dream routines emit scoped dream-dispatch
effects. Each fleet beat copies the full canonical Mission Control prompt into its immutable revision, then
emits that same full prompt with the occurrence. Mission Control delivery therefore cannot drift if a source
text changes after registration. A corrected digest serially replaces only the tenant's active trigger;
older revisions, occurrences, and effects remain immutable history.

## How to use routines

There is no general routine editor today. Operators inspect the registered fleet subset with
`beat-dispatch routines`, list pending immutable effects with `beat-dispatch list`, and use the exact dream
commands for dream effects. Both beat reads are operator-only. Ctower records the schedule and effect; the
external Mission Control consumer owns DIRECTOR-session injection and its append-only delivery ledger.

New users should treat routines as scheduled system work, not as tickets they can edit from the Board. If a
routine creates or checks ticket work, the resulting saved facts remain the source of truth.
