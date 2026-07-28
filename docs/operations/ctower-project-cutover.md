# ctower-project development cutover

This page separates the currently implemented I1.7A visibility boundary from later authority changes.

## I1.7A — contracts and read-only visibility

I1.7A provides strict cutover-health and compact Project Delivery reads. The Project Delivery row keeps
I1.7 visibly `blocked` with degraded confidence while CP3-D is unproven. Its migration command spellings are
authenticated, online-only, unspoolable refusal stubs. They do not freeze, export, import, reconcile,
prepare, commit, or verify a real cutover.

The existing file-based coordination store this project runs on remains the writable ctower-project source
throughout I1.7A.

## I1.7B — import and fence (not implemented)

I1.7B will own reviewed source selection, deterministic double export, exact alias mapping, restricted
idempotent import, reconciliation, and the permanent scope-aware legacy fence. It must not ingest
credentials, accounting, production authority/effects, incidents, client data, irreplaceable artifacts, or
another project's work.

## I1.7C — development epoch and dogfood (not implemented)

I1.7C will commit the point-of-no-return development epoch for the reviewed reconstructible cohort and run
the first post-epoch API/CLI dogfood target. After commit, rollback means a compatible ctower
build/restore or explicit read-only/spool mode; legacy mutation never resumes.

Development success cannot remove `CP3_D_NOT_PROVEN` or establish accepted-record RPO 0. Disaster-safe
promotion requires the separate CP3-D external acknowledgement, key recovery, isolated destructive restore,
and measured RPO/RTO evidence.
