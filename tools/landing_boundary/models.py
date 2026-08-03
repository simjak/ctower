"""Strict typed values for the record's landing-boundary answer.

Every field below is a fact the record already derived and this reader only renders.
The document has no field for a label, a comment, an administrator merge, a re-run, a
follow-up ticket, a repository quality-gate result, a reviewer assertion, or an operator
waiver, and the models forbid unknown fields, so no bypass can be expressed to this
reader at all.  It also has no field for a branch name, a pull-request title, or a body,
so a change can never report its own evidence.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

__all__ = [
    "ChangeIdentity",
    "LandingBoundaryError",
    "PinnedWorkflow",
    "RecordSnapshot",
    "SlotRecord",
    "StageRecord",
    "TicketBinding",
    "VerdictRecord",
]

Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
StableKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9._-]*$")]
Revision = Annotated[str, StringConstraints(pattern=r"^([0-9a-f]{40}|[0-9a-f]{64})$")]
Repository = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$"),
]
PullRequestReference = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*$")]
UuidText = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$"),
]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class LandingBoundaryError(RuntimeError):
    """The landing-boundary input failed closed before any fact was reported."""


class _Payload(BaseModel):
    """Strict immutable base for every record-supplied value."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ChangeIdentity(_Payload):
    """The exact change the check is asked about, and the record must answer for."""

    repository: Repository
    pull_request_reference: PullRequestReference
    head_revision: Revision


class TicketBinding(_Payload):
    """The recorded Change fact that binds this pull request to one ticket."""

    ticket_id: UuidText
    project_key: StableKey
    candidate_digest: Digest | None


class PinnedWorkflow(_Payload):
    """The ticket's own pinned Workflow revision and its declared landing boundary."""

    graph: dict[str, object]
    graph_digest: Digest
    landing_boundary_stage: StableKey | None


class VerdictRecord(_Payload):
    """One recorded verdict bound by a slot, with the model that actually signed it."""

    verdict_id: Identifier
    verdict_class: Literal["security", "release-gating", "ordinary"]
    disposition: Literal["signed-off", "changes-requested", "unknown"]
    signer_principal: Identifier
    signing_model: Identifier
    self_reported: bool


class SlotRecord(_Payload):
    """One member of a stage instance's resolved required slot set."""

    slot_key: StableKey
    state: Literal["filled", "unfilled", "unknown"]
    validity: Literal["current", "invalidated", "expired", "revoked", "unknown"]
    bound_candidate_digest: Digest | None
    self_reported: bool
    verdicts: Annotated[tuple[VerdictRecord, ...], Field(max_length=64)]


class StageRecord(_Payload):
    """One stage instance's resolved required slot set at the source watermark."""

    stage_key: StableKey
    resolution: Literal["resolved", "unknown"]
    required_slots: Annotated[tuple[SlotRecord, ...], Field(max_length=64)]

    @model_validator(mode="after")
    def enforce_unique_slot_keys(self) -> Self:
        keys = [slot.slot_key for slot in self.required_slots]
        if len(set(keys)) != len(keys):
            raise ValueError("required slot keys must be unique within one stage")
        return self


class RecordSnapshot(_Payload):
    """The record's complete answer for one change at one source watermark."""

    schema_: Literal["ctower.landing-boundary-record/v1"] = Field(alias="schema")
    availability: Literal["available", "unavailable"]
    change: ChangeIdentity
    binding: TicketBinding | None
    workflow: PinnedWorkflow | None
    stages: Annotated[tuple[StageRecord, ...], Field(max_length=256)]

    @model_validator(mode="after")
    def enforce_unique_stage_keys(self) -> Self:
        keys = [stage.stage_key for stage in self.stages]
        if len(set(keys)) != len(keys):
            raise ValueError("stage keys must be unique within one record snapshot")
        return self
