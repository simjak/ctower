"""The deterministic fault-injection fake: the third implementation of the same contract.

Its whole purpose is to be a binding that can be *told* to fail in each way a real substrate
has actually failed, with no clock, no randomness, and no I/O. Every fault below is a
recorded production incident: a dispatch reported while the text sat in a composer, a long
brief collapsed into a paste block that one Enter does not flush, a limit menu that matched
the generic working pattern, a lane past its context window still emitting tokens, a footer
naming a model the gateway was not serving, an auth-dead pane showing a normal footer and an
advancing timer, and a pane that simply disappeared.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from ctower_runner_sdk.attempt import AttemptPin, BriefBundle, SeatRef, WorkspaceContext
from ctower_runner_sdk.credentials import (
    EntryState,
    Lease,
    MintRequest,
    ProbeReading,
    ProbeResponse,
    exhaustion_refusal,
)
from ctower_runner_sdk.facts import (
    ArtifactSet,
    DispatchReceipt,
    Handoff,
    LivenessFact,
    ModelObservation,
    TeardownReceipt,
    WritebackFact,
    WritebackReceipt,
)
from ctower_runner_sdk.guard import DispatchBoundary, ExecutionPlan
from ctower_runner_sdk.policy import (
    classify_state,
    collect_refusal,
    dispatch_pin_refusal,
    ladder_disposition,
    serving_observation,
    teardown_receipt,
    writeback_refusal,
)
from ctower_runner_sdk.refusals import Refusal, substrate_unobservable
from ctower_runner_sdk.rotation import RotationEvent, classify_probe
from ctower_runner_sdk.seam import CollectReason, CredentialRef, TeardownOrder
from ctower_runner_sdk.spec import HarnessSpec, ProbeShape

__all__ = [
    "FAULTS",
    "FakePool",
    "FakeSubstrate",
    "Fault",
    "FaultInjectionBinding",
    "unacknowledged",
]

type Fault = Literal[
    "unacknowledged_dispatch",
    "queued_composer",
    "collapsed_paste",
    "cap_menu",
    "context_saturation",
    "model_substitution",
    "dead_auth",
    "pane_loss",
]

# The complete injected-fault matrix the conformance suite runs against every binding.
FAULTS: tuple[Fault, ...] = (
    "unacknowledged_dispatch",
    "queued_composer",
    "collapsed_paste",
    "cap_menu",
    "context_saturation",
    "model_substitution",
    "dead_auth",
    "pane_loss",
)

_UNACKNOWLEDGED: frozenset[str] = frozenset(
    {"unacknowledged_dispatch", "queued_composer", "collapsed_paste"}
)
_FAKE_PROBE = "in-process-fake"


def unacknowledged(fault: Fault, evidence: str) -> Refusal:
    """The one refusal a dispatch may end in, with the composer state that caused it."""

    return Refusal(
        name="harness-dispatch-unacknowledged",
        observed=evidence,
        meaning="the brief was delivered and never acknowledged, which is not a dispatch",
        action="clear the composer and re-deliver; no session-start fact was recorded",
        detail=(("fault", fault),),
    )


@dataclass(slots=True)
class FakeSubstrate:
    """Everything the fake observes, stated explicitly rather than discovered."""

    fault: Fault | None = None
    dirty_paths: tuple[str, ...] = ()
    pushed: bool = True
    head_sha: str = "0" * 40
    status_artifact: bool = True
    sole_work_unpushed: bool = False
    requested_model: str = "fake-model"
    served_model: str = "fake-model"
    context_used_pct: int = 10
    mutations: list[str] = field(default_factory=list)


class FaultInjectionBinding:
    """A binding with no substrate, obeying the same contract as one with a real substrate."""

    def __init__(
        self,
        spec: HarnessSpec,
        boundary: DispatchBoundary,
        substrate: FakeSubstrate,
        clock: Callable[[], datetime],
    ) -> None:
        self._spec = spec
        self._boundary = boundary
        self._substrate = substrate
        self._clock = clock

    @property
    def spec(self) -> HarnessSpec:
        return self._spec

    def spawn(
        self,
        attempt: AttemptPin,
        seat: SeatRef,
        brief: BriefBundle,
        context: WorkspaceContext,
    ) -> DispatchReceipt | Refusal:
        """Clear the guard, then return only on an observed acknowledgement."""

        mispinned = dispatch_pin_refusal(self._spec, attempt)
        if mispinned is not None:
            return mispinned
        plan = ExecutionPlan(
            harness_ref=attempt.harness_ref,
            profile_ref=attempt.profile_ref,
            composition_digest=attempt.composition_digest,
            program=_FAKE_PROBE,
            argv=(seat.seat_key, brief.digest),
            worktree_path=context.worktree_path,
        )
        decision = self._boundary.clear(plan, self._clock())
        if isinstance(decision, Refusal):
            return decision
        fault = self._substrate.fault
        if fault in _UNACKNOWLEDGED:
            return unacknowledged(_fault(fault), f"the composer still holds {brief.digest}")
        self._substrate.mutations.append(f"session-start:{attempt.attempt_id}")
        return DispatchReceipt(
            attempt_id=str(attempt.attempt_id),
            composition_digest=attempt.composition_digest,
            acknowledged_at=self._clock(),
            ack_evidence="the composer cleared after submit",
            guard_decision_id=decision.decision_id,
            durable_command_id=f"fake-{attempt.attempt_id}",
        )

    def liveness(self, attempt: AttemptPin, after_cursor: int) -> LivenessFact:
        """Classify with cap and saturation ahead of any working marker."""

        fault = self._substrate.fault
        if fault == "pane_loss":
            return LivenessFact(
                state="unknown",
                probe=substrate_unobservable(_FAKE_PROBE).name,
                observed_at=self._clock(),
                evidence=f"epoch {attempt.epoch} cursor {after_cursor}",
            )
        served, conflict = serving_observation(self._spec, self._readings())
        return LivenessFact(
            state=classify_state(
                capped=fault == "cap_menu",
                saturated=fault == "context_saturation",
                dead_auth=fault == "dead_auth",
                working_marker=True,
                pane_changed=False,
            ),
            probe=_FAKE_PROBE,
            observed_at=self._clock(),
            served_model=served,
            context_used_pct=(
                100 if fault == "context_saturation" else self._substrate.context_used_pct
            ),
            conflict=conflict,
            ladder=ladder_disposition(attempt, None if served is None else served.value),
            evidence=f"epoch {attempt.epoch}",
        )

    def collect(self, attempt: AttemptPin, reason: CollectReason) -> ArtifactSet | Refusal:
        """Derive from committed refs; an uncommitted tree names its dirty paths."""

        refusal = collect_refusal(self._substrate.dirty_paths)
        if refusal is not None:
            return refusal
        return ArtifactSet(
            branch=f"fake/{attempt.attempt_id}",
            head_sha=self._substrate.head_sha,
            pushed=self._substrate.pushed,
            gate_output_paths=(f"gate/{reason}.log",),
            status_artifact_path="status.md" if self._substrate.status_artifact else None,
            handoff=Handoff(
                done="the fake ran",
                in_progress="nothing",
                not_started="nothing",
                next_three_steps=("read the branch", "re-run the suite", "report"),
            ),
        )

    def writeback(
        self,
        attempt: AttemptPin,
        seat: SeatRef,
        seat_credential: CredentialRef,
        facts: tuple[WritebackFact, ...],
    ) -> WritebackReceipt | Refusal:
        """File as the seat, inside the three scopes, with a stage change as a request only."""

        refusal = writeback_refusal(seat_credential, seat, facts)
        if refusal is not None:
            return refusal
        self._substrate.mutations.append(f"writeback:{attempt.attempt_id}")
        return WritebackReceipt(
            actor_principal_id=seat_credential.seat_key,
            accepted=tuple(fact.kind for fact in facts if fact.scope != "transition"),
            transition_requests=tuple(fact.kind for fact in facts if fact.scope == "transition"),
            server_answer="accepted; transitions recorded as requests",
        )

    def teardown(self, attempt: AttemptPin, order: TeardownOrder) -> TeardownReceipt | Refusal:
        """Preserve the work and the continuation, in that order."""

        collected = self.collect(attempt, "checkpoint")
        return teardown_receipt(
            order,
            artifacts=None if isinstance(collected, Refusal) else collected,
            state=self.liveness(attempt, 0).state,
            sole_work_unpushed=self._substrate.sole_work_unpushed,
            basis="the fake was parked by the suite",
            expires_at=self._clock(),
            nudge_offered=True,
        )

    def _readings(self) -> tuple[ModelObservation, ...]:
        substituted = self._substrate.fault == "model_substitution"
        served = "fake-substituted-model" if substituted else self._substrate.served_model
        at = self._clock()
        return (
            ModelObservation(
                value=served, source="in_process_fake", proves="serving", observed_at=at
            ),
            ModelObservation(
                value=self._substrate.requested_model,
                source="pane_footer",
                proves="request",
                observed_at=at,
            ),
        )


class FakePool:
    """A pool with stated entries. Same Interface, same absence of a copy verb."""

    def __init__(
        self,
        entries: Sequence[EntryState],
        clock: Callable[[], datetime],
        lease_id: UUID,
        probe_shape: ProbeShape,
        profile_key: str = "fake",
    ) -> None:
        self._entries = tuple(entries)
        self._clock = clock
        self._lease_id = lease_id
        self._probe_shape = probe_shape
        self._profile_key = profile_key
        self.metered: list[str] = []

    def acquire(self, model_ref: str, tier: str) -> Lease | Refusal:
        """Fail only when EVERY entry is unselectable, never when the loudest one is."""

        entry = next((item for item in self._entries if not item.blocking_axes()), None)
        if entry is None:
            return exhaustion_refusal(self._entries)
        return Lease(
            lease_id=self._lease_id,
            harness_key="fault-injection-fake",
            profile_key=tier,
            model_ref=model_ref,
            entry=entry,
            acquired_at=self._clock(),
        )

    def meter(self, lease: Lease, observation: Mapping[str, object]) -> None:
        self.metered.append(f"{lease.lease_id}:{sorted(observation)}")

    def limits(self, profile_key: str | None = None) -> tuple[EntryState, ...]:
        """Per-entry rows with their own clocks. There is no aggregate verdict here."""

        if profile_key is not None and profile_key != self._profile_key:
            return ()
        return self._entries

    def rotate(self, reason: str) -> RotationEvent | Refusal:
        return Refusal(
            name="rotation-incomplete",
            observed=f"the fake declares no rotation engine ({reason})",
            meaning="a fake never performs a real rotation",
            action="drive rotation through a real binding's pool",
        )

    def probe(self, response: ProbeResponse) -> ProbeReading | Refusal:
        return classify_probe(self._probe_shape, response)

    def request_mint(self, identity: str | None) -> MintRequest:
        return MintRequest(
            provider_key="fake-provider",
            subscription_identity=identity,
            enactment="operator-ceremony",
        )


def _fault(fault: str | None) -> Fault:
    return next(item for item in FAULTS if item == fault)
