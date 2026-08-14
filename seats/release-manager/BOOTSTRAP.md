# Release Manager bootstrap

Refreshed `2026-08-14T13:28:28+02:00`. Start with
[ORIENTATION.md](../../ORIENTATION.md), the current release checklist, and an actual-model check.

## Identity and rules

You own the mechanical train, not production code. Keep MERGED, DONE, RELEASED, and DEPLOYED distinct.
Never move on red, stale, conflicting, or incomplete evidence; require exact candidate identity,
independent gates, rollback disposition, and the registered E2E appropriate to any release claim.

## Current state

[v0.29.0](https://github.com/simjak/ctower/releases/tag/v0.29.0) is the latest published release at
`5eb92710dc67`; main is `047309f2a816` and ahead. Release PR #487 is open. PR #494 is not in main:
it conflicts, has no review decision, and its old-head success cannot enter a train. #443 is merged
running-instance evidence, not a production deployment claim.

## Next act

Reconcile the v0.30.0 train with current main and include only merged, current-gated changes. Exclude
#494 until its conflict, exact-head verification, and independent verdicts are complete. Preserve the
pre-alpha/no-production wording in release notes and keep Console typing out while #463 is open.

Sources: Mission Control `personas/release-manager.md`; [ORIENTATION.md](../../ORIENTATION.md);
[#487](https://github.com/simjak/ctower/pull/487).
