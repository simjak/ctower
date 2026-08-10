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

The repository contains seven fixed routine definitions:

- a daily synthetic four-stage check;
- a daily backup job definition;
- an hourly record-anchor job definition; and
- four nightly dream routines, one for each project view and one for the whole portfolio.

The scheduler records occurrences for the fixed maintenance definitions. Their real backup, anchor, and
synthetic effects are not all active product operations. The dream routines do emit scoped dream-dispatch
effects.

## How to use routines

There is no general routine editor or routine-list command today. Operators inspect routine health through
the control-plane health surfaces and use the exact dream commands for dream effects.

New users should treat routines as scheduled system work, not as tickets they can edit from the Board. If a
routine creates or checks ticket work, the resulting saved facts remain the source of truth.
