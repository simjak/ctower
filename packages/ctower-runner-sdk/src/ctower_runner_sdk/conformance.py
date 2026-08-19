"""The one shared conformance contract every binding is driven through.

The suite itself lives under `tests/conformance/harness-adapter/`; what lives here is the
shape a binding must offer so that ONE suite can drive it unchanged. That is the whole
earning rule: two real Adapters plus one deterministic fault-injection fake passing the same
unchanged suite. A suite that grew a per-binding branch would prove nothing, so the subject
below is deliberately narrow — a binding, its pool, one set of dispatch inputs, and a small
control surface for placing the substrate in a named condition.

`CorpusCase` is the part that cannot be faked away. Every binding ships samples of its own
substrate output with the state each one must classify to, and a real binding's samples are
captured rather than composed: the first saturation detector in this fleet matched nothing
at all because `█+` is a byte quantifier in this locale, and it would have reported a clean
fleet forever. An untested monitor pattern is not a monitor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ctower_runner_sdk.attempt import AttemptPin, BriefBundle, SeatRef, WorkspaceContext
from ctower_runner_sdk.credentials import CredentialPool
from ctower_runner_sdk.facts import LivenessState
from ctower_runner_sdk.fake import Fault
from ctower_runner_sdk.registry import BindingClass
from ctower_runner_sdk.seam import CredentialRef, HarnessBinding

__all__ = [
    "ConformanceSubject",
    "CorpusCase",
    "DispatchInputs",
    "SubstrateControl",
]


@dataclass(frozen=True, slots=True)
class CorpusCase:
    """One sample of a binding's own substrate output, and what it must classify to.

    `captured` is true only for output read verbatim off a real substrate. `provenance`
    states where it came from either way, so a composed sample can never be mistaken for a
    captured one when someone reads this corpus a year from now.
    """

    label: str
    sample: str
    expected: LivenessState
    captured: bool
    provenance: str


@dataclass(frozen=True, slots=True)
class DispatchInputs:
    """One attempt's inputs, held together so the suite drives every binding the same way."""

    attempt: AttemptPin
    seat: SeatRef
    brief: BriefBundle
    context: WorkspaceContext


class SubstrateControl(Protocol):
    """Deterministic control over one binding's substrate. No clock, no randomness."""

    def inject(self, fault: Fault | None) -> None:
        """Place the substrate in a named failure condition, or clear it."""

    def set_tree(self, *, dirty: tuple[str, ...], pushed: bool) -> None:
        """State what the worktree looks like to `collect`."""

    def set_status_artifact(self, *, present: bool) -> None:
        """State whether the seat wrote its status file. The pushed branch is the handoff."""

    def mutations(self) -> tuple[str, ...]:
        """Every durable fact this binding recorded, for zero-mutation assertions."""

    def corpus(self) -> tuple[CorpusCase, ...]:
        """This binding's own classifier corpus."""

    def classify(self, sample: str) -> LivenessState:
        """Classify one corpus sample exactly as `liveness` would."""


@dataclass(frozen=True, slots=True)
class ConformanceSubject:
    """One implementation under test, and everything the suite needs to drive it."""

    name: str
    binding_class: BindingClass
    binding: HarnessBinding
    pool: CredentialPool
    inputs: DispatchInputs
    credential: CredentialRef
    control: SubstrateControl
