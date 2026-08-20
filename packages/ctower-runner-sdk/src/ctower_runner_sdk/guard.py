"""The final pre-dispatch boundary: nothing runs unless the guard clears it.

INV-58 in adapter form. Every `spawn` obtains and enforces a current versioned CommandGuard
decision for the exact normalized plan, at the last point before the Supervisor is asked to
launch anything. `block` and `needs_operator` dispatch nothing. A plan that changed after
the decision, a grant that expired, a grant replayed a second time, and a caller that never
asked all fail closed, and a receipt that cannot be durably recorded first yields zero
dispatch rather than an unrecorded launch.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from ctower_runner_sdk.refusals import Refusal

__all__ = [
    "CommandGuard",
    "DispatchBoundary",
    "ExecutionPlan",
    "GuardDecision",
    "GuardVerdict",
    "ReceiptSink",
]

type GuardVerdict = Literal["allow", "block", "needs_operator"]


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """The exact normalized plan a guard decides about, and a dispatch then executes."""

    harness_ref: str
    profile_ref: str
    composition_digest: str
    program: str
    argv: tuple[str, ...]
    worktree_path: str
    credential_identity: str | None = None
    credential_home: str | None = None

    def normalized_digest(self) -> str:
        """A stable digest over every field a change to which is a different plan.

        Every field is written length-first, including each argument, so no value can forge
        a boundary between two fields. A separator character alone protected only the
        arguments: `harness_ref` and `profile_ref` arrive observed, and a newline inside one
        of them moved the boundary of the next field, so a decision obtained for one plan
        cleared a different one.
        """

        payload = _framed(
            self.harness_ref,
            self.profile_ref,
            self.composition_digest,
            self.program,
            _framed(*self.argv),
            self.worktree_path,
            _optional_frame(self.credential_identity),
            _optional_frame(self.credential_home),
        )
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class GuardDecision:
    """One versioned decision, bound to one plan digest and usable once."""

    decision_id: str
    verdict: GuardVerdict
    plan_digest: str
    guard_version: int
    expires_at: datetime


class CommandGuard(Protocol):
    """The authority that decides. An adapter enforces it and never substitutes for it."""

    def decide(self, plan: ExecutionPlan) -> GuardDecision: ...


class ReceiptSink(Protocol):
    """Durable receipt storage. A sink that cannot record is a refusal, not a warning."""

    def record(self, decision: GuardDecision, plan: ExecutionPlan) -> bool: ...


class DispatchBoundary:
    """Obtain, verify, and burn one guard decision per dispatch."""

    def __init__(self, guard: CommandGuard, receipts: ReceiptSink, guard_version: int) -> None:
        self._guard = guard
        self._receipts = receipts
        self._guard_version = guard_version
        self._burned: set[str] = set()

    def clear(self, plan: ExecutionPlan, now: datetime) -> GuardDecision | Refusal:
        """Return the decision that authorizes exactly this plan, or refuse by name."""

        decision = self._guard.decide(plan)
        invalid = self._invalidity(decision, plan, now)
        if invalid is not None:
            return invalid
        if decision.verdict != "allow":
            return _verdict_refusal(decision, plan)
        if not self._receipts.record(decision, plan):
            return Refusal(
                name="harness-receipt-undurable",
                observed="the dispatch receipt could not be recorded durably",
                meaning="a launch nobody can prove happened is worse than one that never did",
                action="restore the receipt sink; zero dispatch until a receipt lands first",
                detail=(("decision_id", decision.decision_id),),
            )
        self._burned.add(decision.decision_id)
        return decision

    def _invalidity(
        self, decision: GuardDecision, plan: ExecutionPlan, now: datetime
    ) -> Refusal | None:
        reason = self._decision_fault(decision, plan, now)
        if reason is None:
            return None
        return Refusal(
            name="harness-guard-decision-invalid",
            observed=reason,
            meaning="this decision does not authorize this dispatch",
            action="obtain a current decision for the exact normalized plan",
            detail=(("plan_digest", plan.normalized_digest()),),
        )

    def _decision_fault(
        self, decision: GuardDecision, plan: ExecutionPlan, now: datetime
    ) -> str | None:
        if decision.plan_digest != plan.normalized_digest():
            return "the decision was made about a different normalized plan"
        if decision.guard_version != self._guard_version:
            return f"the decision came from guard version {decision.guard_version}"
        if decision.expires_at <= now:
            return f"the grant expired at {decision.expires_at.isoformat()}"
        if decision.decision_id in self._burned:
            return "this grant was already used once"
        return None


def _framed(*parts: str) -> str:
    """Write each part behind its own byte length, so the sequence reads back one way."""

    return "".join(f"{len(part.encode('utf-8'))}:{part}" for part in parts)


def _optional_frame(value: str | None) -> str:
    """Frame an optional reference without conflating absence with an empty value."""

    return "0" if value is None else f"1{_framed(value)}"


def _verdict_refusal(decision: GuardDecision, plan: ExecutionPlan) -> Refusal:
    blocked = decision.verdict == "block"
    return Refusal(
        name="harness-dispatch-blocked" if blocked else "harness-dispatch-needs-operator",
        observed=f"the guard answered {decision.verdict} for this plan",
        meaning=(
            "the plan is refused outright"
            if blocked
            else "the plan needs an operator decision before it may run"
        ),
        action=(
            "change the plan and ask again"
            if blocked
            else "raise the operator ceremony; nothing dispatches meanwhile"
        ),
        detail=(("plan_digest", plan.normalized_digest()), ("program", plan.program)),
    )
