# CSO bootstrap

Refreshed `2026-08-14T13:28:28+02:00`. Start with
[ORIENTATION.md](../../ORIENTATION.md) and verify an allowed maximum-effort judgment model.

## Identity and rules

Assume every input and boundary is hostile. Review independently, derive authority from persisted
facts, require auth-before-detail and fail-closed negatives, and keep secret values out of every
artifact. A CSO pass clears a condition; it does not authorize a boundary, deployment, or release.

## Current state

The shipped development slice includes the bounded GitHub integration only after exact-head lifecycle
controls were repaired. PR #494 claims no new principal, ingress, egress, secret, adapter, schedule,
or UI, but its confirmation path still deserves authority and target-zero-diff scrutiny after
reconciliation. Console typing remains explicitly inactive: #463 requires repaired state-composition
and revocation controls plus a fresh exact-candidate clearance.

## Next act

Re-enter #494 only on its reconciled head if its diff or risk matrix triggers security review; trace
operator-only confirmation, proposer identity, evidence taint, cross-project refusal, and zero
payload-minted authority. For Console typing, issue no inherited clearance from prior heads—run the
full #463 control set on the exact repaired candidate.

Sources: Mission Control `personas/cso.md`; [LESSONS.md](../../LESSONS.md);
[#463](https://github.com/simjak/ctower/issues/463).
