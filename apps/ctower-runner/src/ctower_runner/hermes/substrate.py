"""The ports the hermes binding reads through, and the vocabulary it does not reopen.

`SupervisorPort` is D10's existing Supervisor Interface as far as this binding composes over
it — `launch`, `observe`, `deliver_input`, `terminate`, each carrying the attempt's fencing
epoch. Nothing here invents a second process-control verb.

The other three ports exist so that harness-private reading stays behind a named boundary:
the gateway log is where serving truth comes from, the engine's own credential store is
read and never written, and the workspace answers only from committed refs.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from ctower_runner_sdk.attempt import AttemptPin, WorkspaceContext
from ctower_runner_sdk.guard import ExecutionPlan

__all__ = [
    "EngineStatePort",
    "GatewayLogPort",
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
        """Deliver text and return the durable command ID the harness answered with."""

    def terminate(self, attempt: AttemptPin) -> None:
        """Stop the pane. Disappearance is never read as success."""


class GatewayLogPort(Protocol):
    """Serving truth. The footer shows what was requested; this shows what answered."""

    def served_model(self, attempt: AttemptPin) -> str | None: ...


class EngineStatePort(Protocol):
    """The harness's own credential store, read-only. One writer per file.

    `entries` returns raw records exactly as the engine keeps them — including the fields
    beside the ones worth reading — because projecting a named allowlist is the caller's
    job and hiding that would remove the control rather than satisfy it.
    """

    def entries(self, profile_key: str) -> tuple[Mapping[str, object], ...]: ...

    def observed_at(self, profile_key: str) -> datetime: ...

    def invalidated_at(self, profile_key: str) -> datetime: ...


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
