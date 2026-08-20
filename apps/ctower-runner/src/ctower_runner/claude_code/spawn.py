"""The wrapper's own refusal, and why a failover here is a new attempt.

This harness is launched through a generated wrapper script that `cd`s into the worktree and
`exec`s the CLI. That wrapper is a policy blind spot: a launcher spawning through a temporary
script hides the binary's name from any check that inspects the launched program's own
argument vector, so a guard written against `argv[0]` passes on every wrapper spawn. The seam
already decides on the normalized *plan* rather than on the launched process, so what this
spawn path adds is the check that makes that decision worth anything here — the attempt's
pinned composition must be the spec's own, verified before the guard is asked, because with a
wrapper in the path the pin is the only thing left that identifies what will run.

And because this harness ships no in-session fallback rung, a cross-account or cross-provider
failover cannot happen inside a running session — there is no such rung to take. It is a
checkpoint, a teardown, and a respawn that is a NEW attempt with its own pinned composition
and its own lease. What would be a hidden mid-session swap on a fallback-capable harness is,
here, a visible attempt boundary.
"""

from __future__ import annotations

from uuid import UUID

from ctower_runner_sdk.attempt import AttemptPin
from ctower_runner_sdk.credentials import Lease
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.spec import HarnessSpec

__all__ = ["failover"]


def failover(
    spec: HarnessSpec,
    attempt: AttemptPin,
    *,
    successor_id: UUID,
    lease: Lease,
    checkpointed: bool,
) -> AttemptPin | Refusal:
    """Return the successor attempt, or refuse an in-session swap by name.

    The successor is a new attempt rather than a later epoch of this one. An epoch bump is
    what a reconstruction after pane, tmux-server, or host loss produces — the same attempt,
    resumed — and a failover is the opposite claim: different credential, different
    composition, and no continuity to inherit.
    """

    if not checkpointed:
        return Refusal(
            name="harness-capability-unsupported",
            observed=(
                f"{spec.key!r} answered native_fallback="
                f"{spec.survey.native_fallback} and was asked to swap inside a live session"
            ),
            meaning="this harness declares no in-session rung, so there is nothing to switch to",
            action="checkpoint and tear the lane down, then respawn as a new attempt",
            detail=(("layer", "fallback"), ("declared_role", spec.layers.fallback)),
        )
    return AttemptPin(
        attempt_id=successor_id,
        epoch=1,
        harness_ref=attempt.harness_ref,
        profile_ref=attempt.profile_ref,
        spec_revision=spec.revision,
        composition_digest=spec.composition_digest(),
        intent_model=attempt.intent_model,
        declared_rungs=attempt.declared_rungs,
        judgment_lane=attempt.judgment_lane,
        lease_id=lease.lease_id,
    )
