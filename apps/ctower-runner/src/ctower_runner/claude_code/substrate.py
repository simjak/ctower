"""The ports the claude-code binding reads through, and the vocabulary it does not reopen.

`SupervisorPort` is D10's existing Supervisor Interface as far as this binding composes over
it — `launch`, `observe`, `deliver_input`, `terminate`, each carrying the attempt's fencing
epoch. Nothing here invents a second process-control verb.

The two ports beside it exist so harness-private reading stays behind a named boundary. The
transcript is the only place this harness states which model actually answered, because its
panes carry no model anywhere on screen; and the workspace answers only from committed refs,
so no pane text can reach an artifact slot through it.

There is deliberately no port for the credential store. This harness ships no pool, so the
config homes are ctower's own state rather than a substrate to read, and modelling them as
one would invite a second reader of a file ctower already writes.
"""

from __future__ import annotations

from typing import Protocol

from ctower_runner_sdk.attempt import AttemptPin, WorkspaceContext
from ctower_runner_sdk.guard import ExecutionPlan
from ctower_runner_sdk.refusals import Refusal

__all__ = [
    "SupervisorPort",
    "TranscriptPort",
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

    def terminate(self, attempt: AttemptPin) -> bool | Refusal:
        """Stop the pane and confirm it stopped. Disappearance is never read as success."""


class TranscriptPort(Protocol):
    """Serving truth: the session transcript under the pane's own working directory.

    The value returned is the model that answered the most recent real assistant turn, or
    `None` when no transcript can be believed. `None` is a reading, not a gap — treating an
    absent transcript as agreement with the request is how a whole harness family read its
    served model as whatever was asked for.
    """

    def served_model(self, attempt: AttemptPin) -> str | None: ...


class WorkspacePort(Protocol):
    """Committed refs and durable records. Never pane text, never session existence."""

    def dirty_paths(self, context: WorkspaceContext) -> tuple[str, ...]: ...

    def head(self, context: WorkspaceContext) -> tuple[str, bool]:
        """Return the head SHA and whether it is pushed."""

    def gate_outputs(self, context: WorkspaceContext) -> tuple[str, ...]: ...

    def status_artifact(self, context: WorkspaceContext) -> str | None: ...


class WritebackPort(Protocol):
    """The generated client, as the runner reaches it. No record-tier connection.

    `file` returns the server's answer verbatim, including a refusal: a refusal is a result
    to report, not an error to retry differently, and a stage change is a REQUEST whose
    disposition belongs to the server.
    """

    def file(
        self, attempt: AttemptPin, credential_ref: str, facts: tuple[tuple[str, str], ...]
    ) -> tuple[str, str]:
        """Return the resolved actor principal and the server's own answer."""
