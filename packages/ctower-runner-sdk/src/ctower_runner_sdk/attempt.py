"""What one attempt is pinned to before anything is dispatched.

Every value here is immutable for the life of the attempt. A rotation, a profile change, or
a re-brief produces a NEW attempt with its own composition digest rather than mutating this
one — D13's active-pointer rule, applied to harnesses and credentials alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

__all__ = [
    "AttemptPin",
    "BriefBundle",
    "SeatRef",
    "WorkspaceContext",
]


@dataclass(frozen=True, slots=True)
class SeatRef:
    """A durable seat key and its crew engagement label. Never a principal.

    No caller, token claim, display name, profile, model, harness, or crew label may supply
    a seat key: fifteen tickets were once filed by one shared principal against a wrong
    project key, and the wrong key was unrefusable precisely because the principal was
    shared.
    """

    seat_key: str
    engagement_label: str
    project_key: str


@dataclass(frozen=True, slots=True)
class BriefBundle:
    """The rendered instruction, its digest, and what must be observed to believe it landed."""

    text: str
    digest: str
    ack_detail: str


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """Where the work happens and where its artifacts are derived from."""

    worktree_path: str
    branch: str
    base_ref: str


@dataclass(frozen=True, slots=True)
class AttemptPin:
    """The immutable composition one attempt runs under.

    `harness_ref` is the observed harness value carried byte-for-byte — never normalized,
    downgraded, or collapsed, because an unknown value displayed as observed is the only
    honest report. `profile_ref` is separate on purpose: the profile owns model and
    reasoning effort, and a launcher named after a model is how a phantom harness category
    is born.
    """

    attempt_id: UUID
    epoch: int
    harness_ref: str
    profile_ref: str
    spec_revision: int
    composition_digest: str
    intent_model: str = ""
    """The model this attempt was seated on, as the durable spawn intent recorded it."""

    declared_rungs: tuple[str, ...] = ()
    """The profile's declared fallback chain, pinned at spawn and never re-read later.

    Anchoring the ladder to the latest ledger row instead of the durable spawn intent is
    what once reported the *recovery* as the violation.
    """

    judgment_lane: bool = False
    """Whether this attempt signs verdicts, where the ladder's tolerance is zero.

    Read off the seat's engagement at spawn and pinned for the life of the attempt, so a
    resumed lane cannot quietly stop being a judgment lane. Switching family under the same
    author assignment does not create reviewer independence, so a rung that is the
    never-stall ladder elsewhere is a substitution here.
    """

    lease_id: UUID | None = None
    credential_identity: str | None = None
    """The selected account identity, as a reference pinned after acquisition."""

    credential_home: str | None = None
    """The selected account's config-home reference, never credential material."""

    def with_lease(
        self,
        lease_id: UUID,
        *,
        credential_identity: str | None = None,
        credential_home: str | None = None,
    ) -> AttemptPin:
        """Return the pin this attempt actually rides, credential included."""

        return AttemptPin(
            attempt_id=self.attempt_id,
            epoch=self.epoch,
            harness_ref=self.harness_ref,
            profile_ref=self.profile_ref,
            spec_revision=self.spec_revision,
            composition_digest=self.composition_digest,
            intent_model=self.intent_model,
            declared_rungs=self.declared_rungs,
            judgment_lane=self.judgment_lane,
            lease_id=lease_id,
            credential_identity=credential_identity,
            credential_home=credential_home,
        )

    def supersedes(self, other: AttemptPin) -> bool:
        """Whether this pin is a later epoch of the same attempt.

        Reconstruction after pane, tmux-server, or host loss rebuilds from ctower state and
        rejects an older epoch; a pane's disappearance is never read as success.
        """

        return self.attempt_id == other.attempt_id and self.epoch > other.epoch

    def to_mapping(self) -> dict[str, object]:
        return {
            "attempt_id": str(self.attempt_id),
            "composition_digest": self.composition_digest,
            "credential_home": self.credential_home,
            "credential_identity": self.credential_identity,
            "epoch": self.epoch,
            "declared_rungs": list(self.declared_rungs),
            "harness_ref": self.harness_ref,
            "intent_model": self.intent_model,
            "judgment_lane": self.judgment_lane,
            "lease_id": None if self.lease_id is None else str(self.lease_id),
            "profile_ref": self.profile_ref,
            "spec_revision": self.spec_revision,
        }
