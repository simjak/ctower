"""The ports the codex binding reads through, and the vocabulary it does not reopen.

`SupervisorPort` is D10's existing Supervisor Interface as far as this binding composes over
it — `launch`, `observe`, `deliver_input`, `terminate`, each carrying the attempt's fencing
epoch. Nothing here invents a second process-control verb.

`RolloutPort` is this harness's serving truth. The status line does print a model, and that
model is the launch argument rendered back, so believing it would let the request corroborate
itself. What actually answered is recorded per turn in the session rollout under the config
home, and that is the only place this harness states it.

`CeremonyPort` is the whole of ctower's provided pool. This binding performs no enrolment, no
mint, no rotation and no cooldown of its own: it asks the fleet's existing tool family, which
is a year of incidents already paid for, and it guards and records what came back. A fifth
rotation implementation over the same single-use refresh chains would be a race, not a spare.
"""

from __future__ import annotations

from typing import Protocol

from ctower_runner.codex.ceremonies import CeremonyInvocation, CeremonyOutcome
from ctower_runner_sdk.attempt import AttemptPin, WorkspaceContext
from ctower_runner_sdk.guard import ExecutionPlan

__all__ = [
    "CeremonyPort",
    "RolloutPort",
    "SupervisorPort",
    "WorkspacePort",
    "WritebackPort",
]


class SupervisorPort(Protocol):
    """D10's process control. This binding composes over it and never replaces it."""

    def launch(self, plan: ExecutionPlan, attempt: AttemptPin) -> str:
        """Start the pane and return its identity."""

    def observe(self, attempt: AttemptPin, after_cursor: int) -> str | None:
        """Return captured pane text, or `None` when the substrate is unobservable."""

    def deliver_input(self, attempt: AttemptPin, text: str) -> str | None:
        """Deliver text and return the durable command record the delivery produced."""

    def terminate(self, attempt: AttemptPin) -> None:
        """Stop the pane. Disappearance is never read as success."""


class RolloutPort(Protocol):
    """Serving truth: the session rollout this attempt's config home recorded.

    `None` is a reading rather than a gap. Treating an absent rollout as agreement with the
    launch argument is how a whole harness family reported its served model as whatever it was
    asked for, and on this harness the pane looks identical either way.
    """

    def served_model(self, attempt: AttemptPin) -> str | None: ...


class CeremonyPort(Protocol):
    """The fleet's existing credential ceremonies, as this binding is allowed to ask them.

    An outcome may be a refusal the ceremony itself raised — the generation guard lives in
    `codex-rotate-fallback` where it was hardened, not in a copy of it here — and this binding
    reports that verdict rather than forming a second opinion about the same chain.
    """

    def run(self, invocation: CeremonyInvocation) -> CeremonyOutcome: ...


class WorkspacePort(Protocol):
    """Committed refs and durable records. Never pane text, never session existence."""

    def dirty_paths(self, context: WorkspaceContext) -> tuple[str, ...]: ...

    def head(self, context: WorkspaceContext) -> tuple[str, bool]:
        """Return the head SHA and whether it is pushed."""

    def gate_outputs(self, context: WorkspaceContext) -> tuple[str, ...]: ...

    def status_artifact(self, context: WorkspaceContext) -> str | None: ...


class WritebackPort(Protocol):
    """The generated client, as the runner reaches it. No record-tier connection.

    `file` returns the server's answer verbatim, including a refusal: a refusal is a result to
    report, not an error to retry differently, and a stage change is a REQUEST whose
    disposition belongs to the server.
    """

    def file(
        self, attempt: AttemptPin, credential_ref: str, facts: tuple[tuple[str, str], ...]
    ) -> tuple[str, str]:
        """Return the resolved actor principal and the server's own answer."""
