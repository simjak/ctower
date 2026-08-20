"""Every implementation the one shared suite drives, built the same way.

Four subjects: the real `hermes`, `claude-code`, and `codex` bindings plus the deterministic
fault-injection fake. The suite below them never branches on which is which — that is the
whole point of the earning rule, and a suite that grew a per-binding branch would prove
nothing. Registering a subject here is the only step a new binding takes to enter it; no cell
above knows how many subjects there are, or which one it is running against.

The real bindings sit on both sides of the survey. Hermes ships both resilience layers, so
ctower configures and observes them; Claude-Code and direct-CLI Codex ship neither, so ctower
provides them. A contract proven twice on the same side of that split would not be proven at all.
"""

from __future__ import annotations

from collections.abc import Mapping
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

from ctower_runner.claude_code.binding import ClaudeCodeBinding
from ctower_runner.claude_code.corpus import CLAUDE_CODE_CORPUS
from ctower_runner.claude_code.liveness import classify_pane as classify_claude_code_pane
from ctower_runner.claude_code.pool import ClaudeCodePool, ConfigHome
from ctower_runner.claude_code.pool import ConfigHomeStore as ClaudeConfigHomeStore
from ctower_runner.claude_code.spec import (
    harness_spec_document as claude_code_spec_document,
)
from ctower_runner.codex.binding import CodexBinding
from ctower_runner.codex.ceremonies import CeremonyInvocation, CeremonyOutcome
from ctower_runner.codex.corpus import CODEX_CORPUS
from ctower_runner.codex.liveness import classify_pane as classify_codex_pane
from ctower_runner.codex.pool import CodexAccount, CodexPool
from ctower_runner.codex.pool import ConfigHomeStore as CodexConfigHomeStore
from ctower_runner.codex.spec import harness_spec_document as codex_spec_document
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

# Exactly what the cells import. A per-binding builder that no cell names is reached through
# `BUILDERS`, `DOCUMENTS`, or `subjects()` and is not part of this module's surface — which is
# why `build_hermes` is here and `build_claude_code` is not: three cells drive the hermes
# column by name, and none drives any column by name that the parametrization already covers.
__all__ = [
    "BUILDERS",
    "DOCUMENTS",
    "PROFILE_KEY",
    "SEAT_PROJECT",
    "DocumentBuilder",
    "SubjectBuilder",
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
SEAT_KEY = "engineer-t1"
_BRIEF_DIGEST = "sha256:" + "f" * 64

# The profile's own chain: codex primary, then glm, then qwen, in policy order.
_DECLARED_RUNGS: tuple[str, ...] = ("glm-5.3", "qwen3.8-max")

_HEALTHY_PANE = HERMES_CORPUS[0].sample
_FAULT_PANES: dict[str, str] = {
    "cap_menu": HERMES_CORPUS[8].sample,
    "context_saturation": HERMES_CORPUS[7].sample,
    "dead_auth": HERMES_CORPUS[10].sample,
}
_CLAUDE_ARTIFACT_DIGEST = digest_of(b"claude-code-artifact-under-test")
_CLAUDE_CONFIG_DIGEST = digest_of(b"claude-code-config-home-under-test")
_CLAUDE_HEALTHY_PANE = CLAUDE_CODE_CORPUS[0].sample
_CLAUDE_FAULT_PANES: dict[str, str] = {
    "cap_menu": CLAUDE_CODE_CORPUS[8].sample,
    "context_saturation": CLAUDE_CODE_CORPUS[10].sample,
    "dead_auth": CLAUDE_CODE_CORPUS[6].sample,
}
_CLAUDE_HOME_SLUGS: tuple[str, ...] = ("home-a", "home-b", "home-c")
_CODEX_ARTIFACT_DIGEST = digest_of(b"codex-cli-artifact-under-test")
_CODEX_CONFIG_DIGEST = digest_of(b"codex-config-home-under-test")
_CODEX_HEALTHY_PANE = CODEX_CORPUS[7].sample
_CODEX_FAULT_PANES: dict[str, str] = {
    "cap_menu": CODEX_CORPUS[6].sample,
    "context_saturation": CODEX_CORPUS[9].sample,
    "dead_auth": CODEX_CORPUS[4].sample,
}
_FAKE_STATES: dict[Fault, LivenessState] = {
    "cap_menu": "capped",
    "context_saturation": "saturated",
    "dead_auth": "dead_auth",
    "pane_loss": "unknown",
}


def hermes_document() -> dict[str, object]:
    return harness_spec_document(artifact_digest=_ARTIFACT_DIGEST, config_digest=_CONFIG_DIGEST)


def claude_code_document() -> dict[str, object]:
    """The second real binding's declaration, answered `no` on both native layers."""

    return claude_code_spec_document(
        artifact_digest=_CLAUDE_ARTIFACT_DIGEST, config_digest=_CLAUDE_CONFIG_DIGEST
    )


def codex_document() -> dict[str, object]:
    """The second real binding's declaration, answered `no` on both native layers."""

    return codex_spec_document(
        artifact_digest=_CODEX_ARTIFACT_DIGEST, config_digest=_CODEX_CONFIG_DIGEST
    )


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
    scope: str = "project-seat",
    project_key: str = SEAT_PROJECT,
    seat_key: str = SEAT_KEY,
) -> CredentialReference:
    """The seat's own credential, or exactly one axis of it made wrong."""

    return CredentialReference(scope=scope, seat_key=seat_key, project_key=project_key)


def _inputs(spec: HarnessSpec) -> DispatchInputs:
    return DispatchInputs(
        attempt=_attempt_pin(spec),
        seat=SeatRef(seat_key=SEAT_KEY, engagement_label=PROFILE_KEY, project_key=SEAT_PROJECT),
        brief=BriefBundle(
            text="read the row, build exactly its scope",
            digest=_BRIEF_DIGEST,
            ack_detail="the composer cleared",
        ),
        context=WorkspaceContext(
            worktree_path="/srv/attempt", branch="feat/attempt", base_ref="origin/main"
        ),
    )


class _PaneClassifier(Protocol):
    """One binding's own pane reader, as the control calls it."""

    def __call__(
        self, pane: str, *, saturation_percent: int, pane_changed: bool = False
    ) -> LivenessState: ...


@dataclass(slots=True)
class _PaneControl:
    """Drive a real binding by choosing which of its own captured panes it is looking at.

    Both real bindings are driven through this one control, which is what keeps a per-binding
    branch out of the suite: the corpus, the fault panes, and the classifier are that
    binding's own, and everything the cells above call is identical.
    """

    state: SubstrateState
    spec: HarnessSpec
    healthy: str
    faults: Mapping[str, str]
    cases: tuple[CorpusCase, ...]
    classifier: _PaneClassifier

    def inject(self, fault: Fault | None) -> None:
        self.state.fault = fault
        self.state.pane = self.faults.get(fault or "", self.healthy)

    def set_tree(self, *, dirty: tuple[str, ...], pushed: bool) -> None:
        self.state.dirty = dirty
        self.state.pushed = pushed

    def set_status_artifact(self, *, present: bool) -> None:
        self.state.status_artifact = "status.md" if present else None

    def mutations(self) -> tuple[str, ...]:
        return tuple(self.state.mutations)

    def corpus(self) -> tuple[CorpusCase, ...]:
        return self.cases

    def classify(self, sample: str) -> LivenessState:
        return self.classifier(sample, saturation_percent=self.spec.context_window_percent)


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
        control=_PaneControl(
            state=state,
            spec=spec,
            healthy=_HEALTHY_PANE,
            faults=_FAULT_PANES,
            cases=HERMES_CORPUS,
            classifier=classify_pane,
        ),
    )


def build_claude_code(
    *, guard: StubGuard | None = None, receipts: StubReceipts | None = None
) -> ConformanceSubject:
    """Compose the second real binding over the same deterministic ports.

    The transcript double is the same object that serves hermes its gateway log: both are a
    served-model source answering for one attempt, and what separates them is which source
    each binding DECLARED, not which double it was handed.
    """

    spec = _spec(claude_code_document())
    state = SubstrateState(
        pane=_CLAUDE_HEALTHY_PANE,
        brief_digest=_BRIEF_DIGEST,
        gateway_model=spec.probe.model_ref,
    )
    clock = StepClock()
    pool = ClaudeCodePool(spec, _claude_config_homes(), PROFILE_KEY, clock, lease_ids)
    return ConformanceSubject(
        name="claude-code",
        binding_class="real",
        binding=ClaudeCodeBinding(
            spec,
            supervisor=StubSupervisor(state),
            transcript=StubGateway(state),
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
        control=_PaneControl(
            state=state,
            spec=spec,
            healthy=_CLAUDE_HEALTHY_PANE,
            faults=_CLAUDE_FAULT_PANES,
            cases=CLAUDE_CODE_CORPUS,
            classifier=classify_claude_code_pane,
        ),
    )


def build_codex(
    *, guard: StubGuard | None = None, receipts: StubReceipts | None = None
) -> ConformanceSubject:
    """Compose the second real binding over the same deterministic ports.

    The rollout double is the same object that serves hermes its gateway log: both are a
    served-model source answering for one attempt, and what separates them is which source each
    binding DECLARED, not which double it was handed.
    """

    spec = _spec(codex_document())
    state = SubstrateState(
        pane=_CODEX_HEALTHY_PANE,
        # The double returns the text actually delivered, not a hidden digest. This keeps the
        # binding-specific ACK proof on the real non-secret marker.
        brief_digest="read the row, build exactly its scope",
        gateway_model=spec.probe.model_ref,
    )
    clock = StepClock()
    pool = CodexPool(spec, _codex_config_homes(), _StubCeremonies(), PROFILE_KEY, clock, lease_ids)
    return ConformanceSubject(
        name="codex",
        binding_class="real",
        binding=CodexBinding(
            spec,
            supervisor=StubSupervisor(state),
            rollout=StubGateway(state),
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
        control=_PaneControl(
            state=state,
            spec=spec,
            healthy=_CODEX_HEALTHY_PANE,
            faults=_CODEX_FAULT_PANES,
            cases=CODEX_CORPUS,
            classifier=classify_codex_pane,
        ),
    )


def _claude_config_homes() -> ClaudeConfigHomeStore:
    """One config home per account: the provided pool's whole topology, as data.

    The same three engine records the configure-and-observe pool observes, keyed here by
    account identity and carrying the adjacent token fields the projection must leave behind.
    The slugs are deliberately not account names — a label has pointed at the wrong account
    twice, so nothing here may be resolved by one.
    """

    records = pool_records(BASE_TIME + timedelta(hours=6))
    homes = {
        slug: ConfigHome(
            slug=slug,
            account_identity=str(record["subscription_identity"]),
            config_dir=f"/srv/claude-homes/{slug}",
            refresh_generation=1,
            entry=record,
        )
        for slug, record in zip(_CLAUDE_HOME_SLUGS, records, strict=True)
    }
    return ClaudeConfigHomeStore(homes=homes, live_slug=_CLAUDE_HOME_SLUGS[0])


class _StubCeremonies:
    """The fleet's ceremonies, as this binding is allowed to ask them. Nothing is executed.

    A ceremony reports what it installed and whether its own hook completed; its refusals are
    the ceremony's own and are exercised where they belong, in this row's acceptance suite.
    """

    def run(self, invocation: CeremonyInvocation) -> CeremonyOutcome:
        return CeremonyOutcome(
            ceremony=invocation.ceremony,
            installed_identity="seat-three@example.test",
            installed_generation=2,
            hook_completed=True,
        )


def _codex_config_homes() -> CodexConfigHomeStore:
    """One config home per account: the provided pool's whole topology, as data.

    The same three engine records the configure-and-observe pool observes, keyed here by the
    account's own decoded identity and carrying the adjacent token fields the projection must
    leave behind. Nothing is keyed by label: a label has pointed at the wrong account twice.
    """

    records = pool_records(BASE_TIME + timedelta(hours=6))
    accounts = {
        str(record["subscription_identity"]): CodexAccount(
            account_identity=str(record["subscription_identity"]),
            codex_home=f"/srv/codex-homes/{index}",
            refresh_generation=1,
            entry=record,
        )
        for index, record in enumerate(records)
    }
    live = str(records[0]["subscription_identity"])
    return CodexConfigHomeStore(accounts=accounts, live_identity=live)


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


class DocumentBuilder(Protocol):
    """One binding's authored declaration, before anything is built over it."""

    def __call__(self) -> dict[str, object]: ...


BUILDERS: tuple[tuple[str, SubjectBuilder], ...] = (
    ("hermes", build_hermes),
    ("claude-code", build_claude_code),
    ("fault-injection-fake", build_fake),
    ("codex", build_codex),
)

# The authored half of the same four subjects, for cells that vary a declaration rather than
# a substrate. A capability a binding could declare is data, and a suite that can only see
# the capabilities today's fleet happens to hold would encode that accident as law.
DOCUMENTS: tuple[tuple[str, DocumentBuilder], ...] = (
    ("hermes", hermes_document),
    ("claude-code", claude_code_document),
    ("fault-injection-fake", fake_document),
    ("codex", codex_document),
)


def subjects() -> tuple[ConformanceSubject, ...]:
    """Every implementation under test, in one tuple the whole suite parametrizes over."""

    return (build_hermes(), build_claude_code(), build_fake(), build_codex())


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
