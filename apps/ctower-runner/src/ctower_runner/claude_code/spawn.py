"""The wrapper's own refusal, and why a failover here is a new attempt.

This harness is launched through a generated wrapper script that `cd`s into the worktree and
`exec`s the CLI. That wrapper is a policy blind spot: a launcher spawning through a temp
script hides the binary's name from any check that inspects the launched program's own
argument vector, so a shared `argv[0]` guard silently passes every wrapper spawn. The spawn
path therefore carries its own refusal, evaluated against the plan's own declaration rather
than against what the process ends up calling itself.

And because this harness ships no in-session fallback rung, a cross-provider or cross-account
failover cannot happen inside a running session — there is no such rung to take. It is a
checkpoint, a teardown, and a respawn that is a NEW attempt with its own immutable pinned
composition. What would be a hidden mid-session swap on a fallback-capable harness is, here, a
visible attempt boundary.

SEAM INTEGRATION (CT-I1-041): `spawn_path_refusal` runs at the seam's final pre-dispatch
boundary beside the CommandGuard decision, and `AttemptComposition` folds into the attempt
pin the seam already carries.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from ctower_runner.claude_code.refusal import Refusal

__all__ = ["AttemptComposition", "SpawnPlan", "failover", "spawn_path_refusal"]


@dataclass(frozen=True, slots=True)
class SpawnPlan:
    """One dispatch plan, and what its guard decision was actually taken against."""

    program: str
    wrapper_script: str | None
    declared_harness: str
    guard_basis: Literal["declared_plan", "launched_argv"]


@dataclass(frozen=True, slots=True)
class AttemptComposition:
    """The immutable pin an attempt rides. A different account is a different attempt."""

    harness_key: str
    spec_revision: int
    artifact_digest: str
    config_digest: str
    account_slug: str

    def pin(self) -> str:
        return (
            f"{self.harness_key}@{self.spec_revision}"
            f"+{self.artifact_digest}+{self.config_digest}+{self.account_slug}"
        )


def spawn_path_refusal(plan: SpawnPlan) -> Refusal | None:
    """Refuse a plan whose only guard is a check the wrapper makes structurally blind."""

    if plan.wrapper_script is None or plan.guard_basis == "declared_plan":
        return None
    return Refusal(
        name="harness-spawn-argv-unverifiable",
        observed=f"the guard read the launched argv while {plan.wrapper_script!r} is exec'd",
        meaning="a wrapper hides the program's name, so that check passes on every spawn",
        action="guard on the plan's own declared harness and pinned digests instead",
        detail=(
            ("declared_harness", plan.declared_harness),
            ("program", plan.program),
            ("wrapper_script", plan.wrapper_script),
        ),
    )


def failover(
    composition: AttemptComposition, *, to_account_slug: str, checkpointed: bool
) -> AttemptComposition | Refusal:
    """Return the successor attempt's composition, or refuse an in-session swap by name."""

    if not checkpointed:
        return Refusal(
            name="harness-in-session-swap-refused",
            observed=f"a swap to {to_account_slug!r} was asked for inside a live session",
            meaning="this harness declares no in-session rung, so there is nothing to switch to",
            action="checkpoint and tear the lane down, then respawn as a new attempt",
            detail=(("from_account", composition.account_slug), ("to_account", to_account_slug)),
        )
    return replace(composition, account_slug=to_account_slug)
