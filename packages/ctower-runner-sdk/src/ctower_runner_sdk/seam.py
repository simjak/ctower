"""The five verbs, composed over the existing Supervisor Interface.

D10 already owns process control — `probe`, `launch`, `observe`, `deliver_input`,
`interrupt`, `terminate`, `snapshot`, `adopt` — and that vocabulary is not reopened here. A
second process-control vocabulary at the harness layer would be the two-authorities-for-one-
fact mistake this repository refuses everywhere else. What this layer adds is what a *seat*
needs in order to be briefed, believed, collected from, and credited: `launch` cannot report
that the pane it started is serving a different model, and `probe` cannot report that a lane
is alive but past its context window and therefore no longer trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ctower_runner_sdk.attempt import AttemptPin, BriefBundle, SeatRef, WorkspaceContext
from ctower_runner_sdk.facts import (
    ArtifactSet,
    DispatchReceipt,
    LivenessFact,
    TeardownReceipt,
    WritebackFact,
    WritebackReceipt,
)
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.spec import HarnessSpec

__all__ = [
    "SEAM_VERBS",
    "CollectReason",
    "CredentialRef",
    "CredentialReference",
    "HarnessBinding",
    "TeardownOrder",
]

type CollectReason = Literal["terminal", "checkpoint", "park", "forensic"]
type TeardownOrder = Literal["checkpoint", "park", "reap"]

# Exactly five. A sixth verb here would be the credential pool, and the pool is a sibling
# Interface resolved at `spawn` instead.
SEAM_VERBS: tuple[str, ...] = ("spawn", "liveness", "collect", "writeback", "teardown")


class CredentialRef(Protocol):
    """A reference to one seat's own project-seat credential. Never a value.

    `scope` exists so an adapter presented with an operator or commander credential refuses
    rather than using it: an adapter holding one is a design failure, not a convenience.
    """

    @property
    def scope(self) -> str: ...

    @property
    def seat_key(self) -> str: ...

    @property
    def project_key(self) -> str: ...


@dataclass(frozen=True, slots=True)
class CredentialReference:
    """A named reference to a credential the adapter never holds the value of.

    `scope` is carried so a credential wider than one seat can be refused on sight rather
    than used and regretted.
    """

    scope: str
    seat_key: str
    project_key: str


class HarnessBinding(Protocol):
    """One harness, bound. Harness-private observation never leaves this object."""

    @property
    def spec(self) -> HarnessSpec: ...

    def spawn(
        self,
        attempt: AttemptPin,
        seat: SeatRef,
        brief: BriefBundle,
        context: WorkspaceContext,
    ) -> DispatchReceipt | Refusal:
        """Launch, deliver, and return only once the declared ACK predicate is observed."""

    def liveness(self, attempt: AttemptPin, after_cursor: int) -> LivenessFact:
        """Classify the lane. Never a boolean, and never `alive` by default."""

    def collect(self, attempt: AttemptPin, reason: CollectReason) -> ArtifactSet | Refusal:
        """Derive artifacts from committed refs and durable records only."""

    def writeback(
        self,
        attempt: AttemptPin,
        seat: SeatRef,
        seat_credential: CredentialRef,
        facts: tuple[WritebackFact, ...],
    ) -> WritebackReceipt | Refusal:
        """File every fact as the seat, inside `capture`, `transition`, and `evidence`.

        The seat and its credential are two independent inputs on purpose. Deriving the
        seat from the credential would make `project-scope-denied` unreachable, which is
        exactly the shape that let fifteen tickets be filed under a wrong project key: with
        nothing to check the claim against, the server has nothing to refuse.
        """

    def teardown(self, attempt: AttemptPin, order: TeardownOrder) -> TeardownReceipt | Refusal:
        """Stop the lane in a way that preserves both the work and the continuation."""
