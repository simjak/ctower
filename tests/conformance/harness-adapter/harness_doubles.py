"""Deterministic doubles for the ports a binding reads through.

No clock, no randomness, no I/O, no network. Every value the suite depends on is stated
here, so a conformance failure is a statement about the binding and never about the day.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ctower_runner_sdk.attempt import AttemptPin, WorkspaceContext
from ctower_runner_sdk.fake import Fault
from ctower_runner_sdk.guard import ExecutionPlan, GuardDecision, GuardVerdict

__all__ = [
    "BASE_TIME",
    "GUARD_VERSION",
    "StepClock",
    "StubEngine",
    "StubGateway",
    "StubGuard",
    "StubReceipts",
    "StubSupervisor",
    "StubWorkspace",
    "StubWriteback",
    "SubstrateState",
    "lease_ids",
    "pool_records",
]

BASE_TIME = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
GUARD_VERSION = 3

# A value the projection allowlist must never carry out of an engine record.
_ADJACENT = "ADJACENT-VALUE-THE-ALLOWLIST-MUST-LEAVE-BEHIND"

_HOLDS_BRIEF: frozenset[str] = frozenset(
    {"unacknowledged_dispatch", "queued_composer", "collapsed_paste"}
)


class StepClock:
    """A clock that advances by exactly one second per read, and never by surprise."""

    def __init__(self, start: datetime = BASE_TIME) -> None:
        self._now = start

    def __call__(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


@dataclass(slots=True)
class SubstrateState:
    """Everything the doubles answer from, driven by one `inject` call."""

    pane: str
    fault: Fault | None = None
    brief_digest: str = ""
    dirty: tuple[str, ...] = ()
    pushed: bool = True
    head_sha: str = "1" * 40
    status_artifact: str | None = "status.md"
    gateway_model: str = "gpt-5.6-sol"
    invalidation_lag_seconds: int = 0
    mutations: list[str] = field(default_factory=list)


class StubSupervisor:
    """D10's process control, answering from stated substrate state."""

    def __init__(self, state: SubstrateState) -> None:
        self._state = state
        self.observed: list[str] = []

    def launch(self, plan: ExecutionPlan, attempt: AttemptPin) -> str:
        self._state.mutations.append(f"launch:{plan.normalized_digest()}:{attempt.epoch}")
        return f"pane-{attempt.attempt_id}"

    def observe(self, attempt: AttemptPin, after_cursor: int) -> str | None:
        self.observed.append(f"{attempt.attempt_id}@{attempt.epoch}+{after_cursor}")
        if self._state.fault == "pane_loss":
            return None
        if self._state.fault in _HOLDS_BRIEF:
            return f"{self._state.pane}\n> {self._state.brief_digest}"
        return self._state.pane

    def deliver_input(self, attempt: AttemptPin, text: str) -> str | None:
        if self._state.fault == "unacknowledged_dispatch":
            return None
        return f"cmd-{attempt.attempt_id}-{len(text)}"

    def terminate(self, attempt: AttemptPin) -> None:
        self._state.mutations.append(f"terminate:{attempt.attempt_id}")


class StubGateway:
    """Serving truth. The one source the footer cannot supply."""

    def __init__(self, state: SubstrateState) -> None:
        self._state = state
        self.asked: list[str] = []

    def served_model(self, attempt: AttemptPin) -> str | None:
        self.asked.append(str(attempt.attempt_id))
        if self._state.fault == "model_substitution":
            return "deepseek-v4-flash"
        return self._state.gateway_model


class StubEngine:
    """The harness's own credential store, including the fields beside the readable ones.

    The records carry credential-shaped keys on purpose: the projection allowlist is only
    a real control if there is something adjacent for it to leave behind.
    """

    def __init__(
        self,
        state: SubstrateState,
        records: tuple[Mapping[str, object], ...],
        profile_key: str,
    ) -> None:
        self._state = state
        self._records = records
        self._profile_key = profile_key

    def entries(self, profile_key: str) -> tuple[Mapping[str, object], ...]:
        return self._records if profile_key == self._profile_key else ()

    def observed_at(self, profile_key: str) -> datetime:
        return BASE_TIME if profile_key == self._profile_key else BASE_TIME - timedelta(days=1)

    def invalidated_at(self, profile_key: str) -> datetime:
        del profile_key
        return BASE_TIME + timedelta(seconds=self._state.invalidation_lag_seconds)


class StubWorkspace:
    """Committed refs only. Pane text can never reach an artifact slot through here."""

    def __init__(self, state: SubstrateState) -> None:
        self._state = state
        self.queried: list[str] = []

    def dirty_paths(self, context: WorkspaceContext) -> tuple[str, ...]:
        self.queried.append(f"dirty:{context.branch}")
        return self._state.dirty

    def head(self, context: WorkspaceContext) -> tuple[str, bool]:
        self.queried.append(f"head:{context.branch}")
        return self._state.head_sha, self._state.pushed

    def gate_outputs(self, context: WorkspaceContext) -> tuple[str, ...]:
        return (f"{context.branch}/just-verify.log",)

    def status_artifact(self, context: WorkspaceContext) -> str | None:
        self.queried.append(f"status:{context.branch}")
        return self._state.status_artifact


class StubWriteback:
    """The generated client, as the runner reaches it. No record-tier connection."""

    def __init__(self, state: SubstrateState) -> None:
        self._state = state

    def file(
        self, attempt: AttemptPin, credential_ref: str, facts: tuple[tuple[str, str], ...]
    ) -> tuple[str, str]:
        self._state.mutations.append(f"writeback:{attempt.attempt_id}:{len(facts)}")
        transitions = [kind for scope, kind in facts if scope == "transition"]
        answer = (
            f"accepted; {len(transitions)} transition request(s) recorded, none applied"
            if transitions
            else "accepted"
        )
        return f"principal-{credential_ref}", answer


class StubGuard:
    """A guard that answers a stated verdict for the exact plan it is shown."""

    def __init__(
        self,
        verdict: GuardVerdict = "allow",
        *,
        decision_id: str = "decision-1",
        guard_version: int = GUARD_VERSION,
        expires_at: datetime = BASE_TIME + timedelta(hours=1),
        plan_digest: str | None = None,
    ) -> None:
        self._verdict = verdict
        self._decision_id = decision_id
        self._guard_version = guard_version
        self._expires_at = expires_at
        self._plan_digest = plan_digest
        self.asked: list[str] = []

    def decide(self, plan: ExecutionPlan) -> GuardDecision:
        digest = plan.normalized_digest()
        self.asked.append(digest)
        return GuardDecision(
            decision_id=self._decision_id,
            verdict=self._verdict,
            plan_digest=self._plan_digest or digest,
            guard_version=self._guard_version,
            expires_at=self._expires_at,
        )


class StubReceipts:
    """A durable receipt sink that can be told it is unavailable."""

    def __init__(self, *, durable: bool = True) -> None:
        self._durable = durable
        self.recorded: list[str] = []

    def record(self, decision: GuardDecision, plan: ExecutionPlan) -> bool:
        if not self._durable:
            return False
        self.recorded.append(f"{decision.decision_id}:{plan.normalized_digest()}")
        return True


def pool_records(reset_at: datetime) -> tuple[Mapping[str, object], ...]:
    """Three entries: two spent, one near-full, with three distinct clocks.

    This is the shape a single-status model cannot express. The pool is not dry — it has an
    exhausted majority and one almost untouched member, and acquisition must find it. The
    two duplicate labels are deliberate: labels have twice pointed at the wrong account.
    """

    return (
        _record("seat-one@example.test", "seat-one", "capped", reset_at, 941, "a"),
        _record(
            "seat-two@example.test", "seat-one", "capped", reset_at + timedelta(hours=2), 1203, "b"
        ),
        _record(
            "seat-three@example.test",
            "seat-three",
            "available",
            reset_at + timedelta(days=3),
            4,
            "c",
        ),
    )


def _record(
    identity: str,
    label: str,
    quota_state: str,
    reset_at: datetime,
    request_count: int,
    fingerprint_seed: str,
) -> Mapping[str, object]:
    """One raw engine record, credential fields included.

    The token fields are here on purpose. A projection allowlist is only a real control if
    there is something adjacent for it to leave behind.
    """

    return {
        "provider_key": "openai-codex",
        "subscription_identity": identity,
        "entry_label": label,
        "registration_state": "enrolled",
        "auth_state": "healthy",
        "quota_state": quota_state,
        "quota_reset_at": reset_at,
        "reach_state": "ok",
        "request_count": request_count,
        "last_status_observed": "exhausted" if quota_state == "capped" else "ok",
        "secret_fingerprint": "sha256:" + fingerprint_seed * 64,
        "access_token": _ADJACENT,
        "refresh_token": _ADJACENT,
    }


def lease_ids() -> UUID:
    """A fixed lease identity, because a lease's value here is its shape."""

    return UUID("00000000-0000-4000-8000-000000000001")
