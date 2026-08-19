"""Every implementation the one shared suite drives, built the same way.

Two subjects today: the real `hermes` binding and the deterministic fault-injection fake.
The suite below them never branches on which is which — that is the whole point of the
earning rule, and a suite that grew a per-binding branch would prove nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from harness_doubles import (
    BASE_TIME,
    GUARD_VERSION,
    StepClock,
    StubEngine,
    StubGateway,
    StubGuard,
    StubReceipts,
    StubSupervisor,
    StubWorkspace,
    StubWriteback,
    SubstrateState,
    lease_ids,
    pool_records,
)

from ctower_runner.hermes.binding import HermesBinding
from ctower_runner.hermes.corpus import HERMES_CORPUS
from ctower_runner.hermes.liveness import classify_pane
from ctower_runner.hermes.pool import HermesPool
from ctower_runner.hermes.spec import (
    HERMES_SATURATION_PERCENT,
    digest_of,
    harness_spec_document,
)
from ctower_runner_sdk.attempt import AttemptPin, BriefBundle, SeatRef, WorkspaceContext
from ctower_runner_sdk.conformance import ConformanceSubject, CorpusCase, DispatchInputs
from ctower_runner_sdk.credentials import EntryState, project_entry
from ctower_runner_sdk.facts import LivenessState
from ctower_runner_sdk.fake import FakePool, FakeSubstrate, Fault, FaultInjectionBinding
from ctower_runner_sdk.guard import DispatchBoundary
from ctower_runner_sdk.registry import HarnessRegistry
from ctower_runner_sdk.seam import CredentialReference
from ctower_runner_sdk.spec import HarnessSpec, parse_harness_spec

__all__ = [
    "BUILDERS",
    "PROFILE_KEY",
    "SEAT_PROJECT",
    "SubjectBuilder",
    "build_fake",
    "build_hermes",
    "fake_document",
    "hermes_document",
    "judgment_inputs",
    "registered_registry",
    "seat_credential",
    "subjects",
]

_ARTIFACT_DIGEST = digest_of(b"hermes-artifact-under-test")
_CONFIG_DIGEST = digest_of(b"hermes-profile-config-under-test")
PROFILE_KEY = "engineer"
SEAT_PROJECT = "ctower"
_BRIEF_DIGEST = "sha256:" + "f" * 64

# The profile's own chain: codex primary, then glm, then qwen, in policy order.
_DECLARED_RUNGS: tuple[str, ...] = ("glm-5.3", "qwen3.8-max")

_HEALTHY_PANE = HERMES_CORPUS[0].sample
_FAULT_PANES: dict[str, str] = {
    "cap_menu": HERMES_CORPUS[8].sample,
    "context_saturation": HERMES_CORPUS[7].sample,
    "dead_auth": HERMES_CORPUS[10].sample,
}
_FAKE_STATES: dict[Fault, LivenessState] = {
    "cap_menu": "capped",
    "context_saturation": "saturated",
    "dead_auth": "dead_auth",
    "pane_loss": "unknown",
}


def hermes_document() -> dict[str, object]:
    return harness_spec_document(artifact_digest=_ARTIFACT_DIGEST, config_digest=_CONFIG_DIGEST)


def fake_document() -> dict[str, object]:
    """The fake declares neither native layer, so ctower provides both for it."""

    document = hermes_document()
    document.update(
        {
            "key": "fault-injection-fake",
            "input_protocol": {"kind": "in_process_fake", "submit_separately": False},
            "output_protocol": {"kind": "in_process_fake"},
            "capabilities": ["CHECKPOINT", "PARK", "REAP", "POOL_OBSERVE"],
            "ack_predicate": {"kind": "in_process_fake", "detail": "the fake acknowledges"},
            "liveness_sources": [
                {"fact": "served_model", "source": "in_process_fake", "proves": "serving"},
                {"fact": "served_model", "source": "pane_footer", "proves": "request"},
            ],
            "probe": {
                "product": "in-process",
                "endpoint": "/fake",
                "model_ref": "fake-model",
                "workload_shape": "representative",
                "classified_on": "response_body",
            },
            "pool": {"cache_invalidation_hook": "in-process-reset", "providers": ["fake-provider"]},
            "survey": {
                "native_pool": False,
                "native_fallback": False,
                "config_surface": "account_file",
                "identity_proof": "account_file",
                "reset_semantics": "unknown",
                "rotation_cache": "config_home_respawn",
                "subagent_inheritance": "separate",
                "egress_topology": "per_entry",
            },
            "layers": {"pool": "provide", "fallback": "provide"},
        }
    )
    return document


def registered_registry() -> HarnessRegistry:
    """A registry holding exactly the implementations that exist today."""

    registry = HarnessRegistry()
    registry.register(hermes_document(), "real")
    registry.register(fake_document(), "fault_injection_fake")
    return registry


def _attempt_pin(spec: HarnessSpec, *, epoch: int = 1, judgment_lane: bool = False) -> AttemptPin:
    """One attempt, with its durable spawn intent and declared ladder pinned at spawn."""

    return AttemptPin(
        attempt_id=UUID("00000000-0000-4000-8000-00000000000a"),
        epoch=epoch,
        harness_ref=spec.key,
        profile_ref=PROFILE_KEY,
        spec_revision=spec.revision,
        composition_digest=spec.composition_digest(),
        intent_model=spec.probe.model_ref,
        declared_rungs=_DECLARED_RUNGS,
        judgment_lane=judgment_lane,
    )


def seat_credential(
    scope: str = "project-seat", project_key: str = SEAT_PROJECT
) -> CredentialReference:
    return CredentialReference(scope=scope, seat_key="engineer-t1", project_key=project_key)


def _inputs(spec: HarnessSpec) -> DispatchInputs:
    return DispatchInputs(
        attempt=_attempt_pin(spec),
        seat=SeatRef(
            seat_key="engineer-t1", engagement_label=PROFILE_KEY, project_key=SEAT_PROJECT
        ),
        brief=BriefBundle(
            text="read the row, build exactly its scope",
            digest=_BRIEF_DIGEST,
            ack_detail="the composer cleared",
        ),
        context=WorkspaceContext(
            worktree_path="/srv/attempt", branch="feat/attempt", base_ref="origin/main"
        ),
    )


@dataclass(slots=True)
class _HermesControl:
    """Drive the real binding by choosing which captured pane it is looking at."""

    state: SubstrateState
    spec: HarnessSpec

    def inject(self, fault: Fault | None) -> None:
        self.state.fault = fault
        self.state.pane = _FAULT_PANES.get(fault or "", _HEALTHY_PANE)

    def set_tree(self, *, dirty: tuple[str, ...], pushed: bool) -> None:
        self.state.dirty = dirty
        self.state.pushed = pushed

    def set_status_artifact(self, *, present: bool) -> None:
        self.state.status_artifact = "status.md" if present else None

    def mutations(self) -> tuple[str, ...]:
        return tuple(self.state.mutations)

    def corpus(self) -> tuple[CorpusCase, ...]:
        return HERMES_CORPUS

    def classify(self, sample: str) -> LivenessState:
        return classify_pane(sample, saturation_percent=self.spec.context_window_percent)


@dataclass(slots=True)
class _FakeControl:
    """Drive the fake by naming the fault; it has no substrate to look at."""

    substrate: FakeSubstrate

    def inject(self, fault: Fault | None) -> None:
        self.substrate.fault = fault

    def set_tree(self, *, dirty: tuple[str, ...], pushed: bool) -> None:
        self.substrate.dirty_paths = dirty
        self.substrate.pushed = pushed
        self.substrate.sole_work_unpushed = not pushed

    def set_status_artifact(self, *, present: bool) -> None:
        self.substrate.status_artifact = present

    def mutations(self) -> tuple[str, ...]:
        return tuple(self.substrate.mutations)

    def corpus(self) -> tuple[CorpusCase, ...]:
        return tuple(
            CorpusCase(
                label=f"injected {fault}",
                sample=fault,
                expected=state,
                captured=False,
                provenance="in-process fault injection; this binding has no substrate to capture",
            )
            for fault, state in sorted(_FAKE_STATES.items())
        )

    def classify(self, sample: str) -> LivenessState:
        fault = _fault(sample)
        previous = self.substrate.fault
        try:
            self.inject(fault)
            return _FAKE_STATES[fault]
        finally:
            self.substrate.fault = previous


def judgment_inputs(spec: HarnessSpec) -> DispatchInputs:
    """The same inputs, seated on a lane whose tolerance for a rung is zero."""

    base = _inputs(spec)
    return DispatchInputs(
        attempt=_attempt_pin(spec, judgment_lane=True),
        seat=base.seat,
        brief=base.brief,
        context=base.context,
    )


def build_hermes(
    *, guard: StubGuard | None = None, receipts: StubReceipts | None = None
) -> ConformanceSubject:
    """Compose the real binding over deterministic ports."""

    spec = _spec(hermes_document())
    state = SubstrateState(pane=_HEALTHY_PANE, brief_digest=_BRIEF_DIGEST)
    clock = StepClock()
    engine = StubEngine(state, pool_records(BASE_TIME + timedelta(hours=6)), PROFILE_KEY)
    pool = HermesPool(spec, engine, PROFILE_KEY, clock, lease_ids)
    supervisor = StubSupervisor(state)
    return ConformanceSubject(
        name="hermes",
        binding_class="real",
        binding=HermesBinding(
            spec,
            supervisor=supervisor,
            gateway=StubGateway(state),
            workspace=StubWorkspace(state),
            writeback_port=StubWriteback(state),
            pool=pool,
            boundary=DispatchBoundary(
                guard or StubGuard(), receipts or StubReceipts(), GUARD_VERSION
            ),
            clock=clock,
        ),
        pool=pool,
        inputs=_inputs(spec),
        credential=seat_credential(),
        control=_HermesControl(state=state, spec=spec),
    )


def build_fake(
    *, guard: StubGuard | None = None, receipts: StubReceipts | None = None
) -> ConformanceSubject:
    """Compose the deterministic fake over the same seam."""

    spec = _spec(fake_document())
    substrate = FakeSubstrate()
    clock = StepClock()
    pool = FakePool(
        _fake_entries(),
        clock,
        UUID("00000000-0000-4000-8000-00000000000b"),
        spec.probe,
        profile_key=PROFILE_KEY,
    )
    return ConformanceSubject(
        name="fault-injection-fake",
        binding_class="fault_injection_fake",
        binding=FaultInjectionBinding(
            spec,
            DispatchBoundary(guard or StubGuard(), receipts or StubReceipts(), GUARD_VERSION),
            substrate,
            clock,
        ),
        pool=pool,
        inputs=_inputs(spec),
        credential=seat_credential(),
        control=_FakeControl(substrate=substrate),
    )


class SubjectBuilder(Protocol):
    """How the suite builds one implementation, with the guard and sink it wants."""

    def __call__(
        self, *, guard: StubGuard | None = None, receipts: StubReceipts | None = None
    ) -> ConformanceSubject: ...


BUILDERS: tuple[tuple[str, SubjectBuilder], ...] = (
    ("hermes", build_hermes),
    ("fault-injection-fake", build_fake),
)


def subjects() -> tuple[ConformanceSubject, ...]:
    """Every implementation under test, in one tuple the whole suite parametrizes over."""

    return (build_hermes(), build_fake())


def _fake_entries() -> tuple[EntryState, ...]:
    return tuple(project_entry(record) for record in pool_records(BASE_TIME + timedelta(hours=6)))


def _spec(document: dict[str, object]) -> HarnessSpec:
    parsed = parse_harness_spec(document)
    if not isinstance(parsed, HarnessSpec):
        raise TypeError(f"the authored spec did not parse: {parsed.to_mapping()}")
    return parsed


def _fault(sample: str) -> Fault:
    return next(fault for fault in _FAKE_STATES if fault == sample)


SATURATION_PERCENT = HERMES_SATURATION_PERCENT
