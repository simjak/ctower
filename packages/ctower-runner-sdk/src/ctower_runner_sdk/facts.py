"""The typed facts that cross the seam. Harness-private shapes never do.

A binding may read a pane, a footer, a transcript, or a gateway log; none of those shapes
leaves it. What leaves is a fact with its own evidence pointer and the probe that produced
it, so no kernel, reporter, projection, CLI, or Board path ever parses a harness-private
format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

__all__ = [
    "NOT_WORKING",
    "ArtifactSet",
    "DispatchReceipt",
    "Handoff",
    "LivenessFact",
    "LivenessState",
    "ModelObservation",
    "TeardownReceipt",
    "WritebackFact",
    "WritebackReceipt",
]

type LivenessState = Literal[
    "working", "idle", "queued_stuck", "saturated", "capped", "dead_auth", "unknown"
]

# Saturated and capped are not slow; they are not working. The floor exists to guarantee
# trustworthy throughput rather than motion, and a lane past its window cannot be trusted
# to still hold the evidence it cites.
NOT_WORKING: frozenset[str] = frozenset(
    {"idle", "queued_stuck", "saturated", "capped", "dead_auth", "unknown"}
)


@dataclass(frozen=True, slots=True)
class ModelObservation:
    """A served-model reading, with the source that produced it and what that source proves."""

    value: str
    source: str
    proves: Literal["serving", "request", "observation"]
    observed_at: datetime

    def is_serving_truth(self) -> bool:
        """A source that proves only the request is a conflict, never serving truth."""

        return self.proves == "serving"


@dataclass(frozen=True, slots=True)
class LivenessFact:
    """One observation. Never a boolean, and never `alive` by default."""

    state: LivenessState
    probe: str
    observed_at: datetime
    served_model: ModelObservation | None = None
    context_used_pct: int | None = None
    conflict: str | None = None
    ladder: str = "as_intended"
    """Whether a served model is the never-stall ladder or a real substitution."""

    evidence: str = ""

    def counts_as_working(self) -> bool:
        return self.state not in NOT_WORKING

    def to_mapping(self) -> dict[str, object]:
        model = self.served_model
        return {
            "conflict": self.conflict,
            "context_used_pct": self.context_used_pct,
            "evidence": self.evidence,
            "ladder": self.ladder,
            "observed_at": self.observed_at.isoformat(),
            "probe": self.probe,
            "served_model": None if model is None else model.value,
            "served_model_source": None if model is None else model.source,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class DispatchReceipt:
    """Proof that the brief was acknowledged, not merely delivered."""

    attempt_id: str
    composition_digest: str
    acknowledged_at: datetime
    ack_evidence: str
    guard_decision_id: str
    durable_command_id: str | None = None


@dataclass(frozen=True, slots=True)
class Handoff:
    """The four sections a successor needs, and the reason none of them is optional."""

    done: str
    in_progress: str
    not_started: str
    next_three_steps: tuple[str, str, str]

    def sections(self) -> tuple[str, ...]:
        return ("done", "in_progress", "not_started", "next_three_steps")


@dataclass(frozen=True, slots=True)
class ArtifactSet:
    """What a run produced, derived from committed refs and durable records only."""

    branch: str
    head_sha: str
    pushed: bool
    gate_output_paths: tuple[str, ...]
    status_artifact_path: str | None
    handoff: Handoff | None = None

    def is_complete(self) -> bool:
        """A pushed branch is the handoff. A status file is a courtesy, not a requirement."""

        return self.pushed and bool(self.head_sha)


@dataclass(frozen=True, slots=True)
class WritebackFact:
    """One fact a seat files as itself, inside one of the three exhaustive scopes."""

    scope: Literal["capture", "transition", "evidence"]
    kind: str
    payload: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class WritebackReceipt:
    """The server's answer, reported verbatim. A refusal is a result, not a retry cue."""

    actor_principal_id: str
    accepted: tuple[str, ...]
    transition_requests: tuple[str, ...]
    server_answer: str


@dataclass(frozen=True, slots=True)
class TeardownReceipt:
    """What the lane stopped with, and what remains true after it stopped."""

    order: Literal["checkpoint", "park", "reap"]
    artifacts: ArtifactSet | None
    basis: str | None = None
    expires_at: datetime | None = None
    nudge_offered: bool = False
