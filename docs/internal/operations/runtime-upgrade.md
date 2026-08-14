# Runtime upgrade ordering

## The rule (named, binding): runtime serves only after its migrations

A runtime build may be **installed** at any time, but it may **serve** only once the database
generation carries every migration that build's code paths assume. Redeploy-before-migrate is
forbidden for any build whose code reads schema objects introduced by its own pending migrations.

**The failure that proved it (2026-08-03, live, zero data harm):** runtime `528d38b2` (carrying
the seat-credential work) was activated on a generation-0035 database. Protected reads failed
immediately — `psycopg.errors.UndefinedTable: relation "seat_credential_issuances" does not
exist` (a 0039 table, read unconditionally by the credential-authentication path at serve time).
The executor's post-restart verification caught it before any mutation; the runtime rolled back
to its secured predecessor and live verified healthy. The attempt is archived at
`development-archives/20260803T210409Z-runtime-upgrade-live-248`.

## The proven sequence (migrate-then-serve)

1. **Swap, do not serve.** Stop the API and worker. Apply the runtime replacement (atomic
   exchange). The predecessor stays on disk as the instant rollback target.
2. **Checkpoint first, prove it restorable.** A fresh checkpoint via the product's own verb,
   restore-verified on a disposable instance, **before any mutation**. Not provably restorable
   stops the sequence.
3. Any recorded-state repair the runbook for this upgrade requires (refusal-guarded: verify the
   expected pre-state; any surprise stops).
4. **Rehearsal gate:** `tools/ctower-upgrade-rehearsal` must exit 0 against live-now.
5. `database-up` through the pending set, using the **new** runtime's tooling, still not serving.
6. **Start serving, then verify the serve path itself:** protected reads (the exact class step 1
   of the failed attempt caught), every board route, one real read+write round-trip, replication,
   finalizer health.
7. Any failure after step 2: restore the checkpoint, reactivate the predecessor runtime, verify
   live matches the pre-sequence state, page P0.

## gh#259: the rule is mechanical, not only procedural

Schema-coupled code paths refuse by name instead of throwing `UndefinedTable` from a protected
read. `record/_credential_sql.py`'s `actor_for_credential`, `issue_seat_credential`, and
`revoke_seat_credential` each probe the schema (one zero-privilege `to_regclass` catalog lookup,
cached per dsn once confirmed — never a per-request query storm) and return the typed
`credential-authentication-unavailable: requires generation >= 0039` refusal in place of the
2026-08-03 failure, on every generation short of 0039.

An earlier version of this section named a `tools/ctower-upgrade-rehearsal` harness as the
intended home for the serve-on-old-schema case; that tool was never committed to this
repository. This repository's own catch is instead a committed migration-contract test,
`tests/modules/migration/test_credential_generation_gate.py`, which ledgers a disposable database
through the pre-0039 generation and proves all three entry points above refuse by name rather
than propagate `UndefinedTable`. Step 4's rehearsal gate is a separate, externally-owned check
against a live-now database; it is unchanged by gh#259.
