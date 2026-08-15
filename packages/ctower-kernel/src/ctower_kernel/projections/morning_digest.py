"""Pure morning digest fold over typed Request and Ruling readings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from ctower_kernel.projections._reading import (
    ReadingState,
    SourceReading,
    UnreachedScope,
)
from ctower_kernel.projections.request_proposals import (
    ProposalSummaryInput,
    RequestMaintenanceProposalSummary,
    derive_request_maintenance_summary,
)
from ctower_kernel.projections.ticket_movement import (
    MovementCountInput,
    MovementDigestSummary,
    derive_movement_summary,
)

__all__ = [
    "DecisionBriefFact",
    "DecisionChoiceFact",
    "DigestRequestFact",
    "DigestRulingFact",
    "MorningDigest",
    "ReadingState",
    "SourceReading",
    "UnreachedScope",
    "project_morning_digest",
]

_VILNIUS = ZoneInfo("Europe/Vilnius")
_MAX_COMPLETENESS = 10
_DECISION_CHOICE_COUNT = 3


class _ResponsePayload(Protocol):
    def response_payload(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class DecisionChoiceFact:
    label: str
    outcome: str
    completeness: int

    def __post_init__(self) -> None:
        if not 0 <= self.completeness <= _MAX_COMPLETENESS:
            raise ValueError("decision choice completeness must be from 0 through 10")

    def response_payload(self) -> dict[str, object]:
        return {
            "completeness": self.completeness,
            "label": self.label,
            "outcome": self.outcome,
        }


@dataclass(frozen=True, slots=True)
class DecisionBriefFact:
    status: str
    what: str
    origin: str
    choices: tuple[DecisionChoiceFact, ...]
    recommendation: str
    safe_default: str

    def __post_init__(self) -> None:
        if self.status not in ("open", "answered"):
            raise ValueError("decision brief status must be open or answered")
        if len(self.choices) != _DECISION_CHOICE_COUNT:
            raise ValueError("decision brief must carry exactly three choices")

    def response_payload(self) -> dict[str, object]:
        return {
            "choices": [item.response_payload() for item in self.choices],
            "origin": self.origin,
            "recommendation": self.recommendation,
            "safe_default": self.safe_default,
            "what": self.what,
        }


@dataclass(frozen=True, slots=True)
class DigestRequestFact:
    """Request fields consumed by the digest; no persistence belongs here."""

    request_id: UUID
    request_number: int
    project_key: str
    state: str
    required_ticket_ids: tuple[UUID, ...]
    optional_ticket_ids: tuple[UUID, ...]
    current_proof_count: int | None
    decision_brief: DecisionBriefFact | None

    @property
    def reference(self) -> str:
        return f"R{self.request_number}"


@dataclass(frozen=True, slots=True)
class DigestRulingFact:
    """Ruling fields plus its authoritative optional Request relation."""

    ruling_id: UUID
    project_key: str
    verbatim: str
    recorded_at: datetime
    linked_request_id: UUID | None

    def __post_init__(self) -> None:
        if self.recorded_at.tzinfo is None:
            raise ValueError("Ruling recording time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class DigestDecision:
    request_id: UUID
    request_reference: str
    project_key: str
    state: ReadingState
    brief: DecisionBriefFact
    unknown_reason: str | None

    def response_payload(self) -> dict[str, object]:
        return {
            "brief": self.brief.response_payload(),
            "project_key": self.project_key,
            "request_id": str(self.request_id),
            "request_reference": self.request_reference,
            "state": self.state.value,
            "unknown_reason": self.unknown_reason,
        }


@dataclass(frozen=True, slots=True)
class DigestExecution:
    request_id: UUID
    request_reference: str
    state: str
    ticket_ids: tuple[UUID, ...]

    def response_payload(self) -> dict[str, object]:
        return {
            "request_id": str(self.request_id),
            "request_reference": self.request_reference,
            "state": self.state,
            "ticket_ids": [str(item) for item in self.ticket_ids],
        }


@dataclass(frozen=True, slots=True)
class DigestRuling:
    ruling_id: UUID
    project_key: str
    verbatim: str
    recorded_at: datetime
    state: ReadingState
    executions: tuple[DigestExecution, ...]
    unknown_reason: str | None

    def response_payload(self) -> dict[str, object]:
        return {
            "executions": [item.response_payload() for item in self.executions],
            "project_key": self.project_key,
            "recorded_at": self.recorded_at.isoformat(),
            "ruling_id": str(self.ruling_id),
            "state": self.state.value,
            "unknown_reason": self.unknown_reason,
            "verbatim": self.verbatim,
        }


@dataclass(frozen=True, slots=True)
class DigestTicketLink:
    ticket_id: UUID
    purpose: str
    href: str

    def response_payload(self) -> dict[str, object]:
        return {"href": self.href, "purpose": self.purpose, "ticket_id": str(self.ticket_id)}


@dataclass(frozen=True, slots=True)
class DigestProof:
    request_id: UUID
    request_reference: str
    project_key: str
    current_proof_count: int | None
    tickets: tuple[DigestTicketLink, ...]

    def response_payload(self) -> dict[str, object]:
        return {
            "current_proof_count": self.current_proof_count,
            "project_key": self.project_key,
            "request_id": str(self.request_id),
            "request_reference": self.request_reference,
            "tickets": [item.response_payload() for item in self.tickets],
        }


@dataclass(frozen=True, slots=True)
class DigestSection[T: _ResponsePayload]:
    state: ReadingState
    visible_count: int
    total_count: int | None
    items: tuple[T, ...]
    unreached: tuple[UnreachedScope, ...]

    def response_payload(self) -> dict[str, object]:
        return {
            "items": [item.response_payload() for item in self.items],
            "state": self.state.value,
            "total_count": self.total_count,
            "unreached": [item.response_payload() for item in self.unreached],
            "visible_count": self.visible_count,
        }


@dataclass(frozen=True, slots=True)
class MorningDigest:
    artifact_key: str
    artifact_sha256: str
    digest_date: date
    timezone: str
    observed_at: datetime
    state: ReadingState
    request_watermark: int | None
    ruling_watermark: int | None
    request_maintenance: RequestMaintenanceProposalSummary
    open_decisions: DigestSection[DigestDecision]
    yesterday_rulings: DigestSection[DigestRuling]
    proof: DigestSection[DigestProof]
    movement: MovementDigestSummary
    movement_watermark: int | None

    def response_payload(self) -> dict[str, object]:
        payload = self.content_payload()
        payload["artifact_sha256"] = self.artifact_sha256
        return payload

    def content_payload(self) -> dict[str, object]:
        return {
            "artifact_key": self.artifact_key,
            "digest_date": self.digest_date.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "open_decisions": self.open_decisions.response_payload(),
            "proof": self.proof.response_payload(),
            "request_watermark": self.request_watermark,
            "request_maintenance": self.request_maintenance.response_payload(),
            "ruling_watermark": self.ruling_watermark,
            "state": self.state.value,
            "timezone": self.timezone,
            "yesterday_rulings": self.yesterday_rulings.response_payload(),
            "movement": self.movement.response_payload(),
            "movement_watermark": self.movement_watermark,
        }

    def artifact_payload(self) -> dict[str, object]:
        """Stable content identity, excluding the time at which it was observed."""

        payload = self.content_payload()
        del payload["observed_at"]
        return payload


def project_morning_digest(
    requests: SourceReading[DigestRequestFact],
    rulings: SourceReading[DigestRulingFact],
    proposals: SourceReading[ProposalSummaryInput],
    movement: SourceReading[MovementCountInput],
    *,
    digest_date: date,
    observed_at: datetime,
) -> MorningDigest:
    """Fold independent source readings without turning absence into knowledge."""

    decisions = _decision_section(requests)
    request_index = {item.request_id: item for item in requests.rows}
    yesterday = _ruling_section(rulings, requests, request_index, digest_date)
    related_request_ids = {item.request_id for item in decisions.items}
    related_request_ids.update(
        execution.request_id for ruling in yesterday.items for execution in ruling.executions
    )
    proof = _proof_section(requests, yesterday, related_request_ids)
    proposal_summary = _proposal_summary(proposals)
    proposal_state = (
        ReadingState.UNKNOWN
        if proposal_summary.source_state == "unavailable"
        else ReadingState(proposal_summary.source_state)
    )
    movement_summary = derive_movement_summary(movement, digest_date=digest_date)
    movement_state = movement_summary.state
    state = _combined_state(
        decisions.state, yesterday.state, proof.state, proposal_state, movement_state
    )
    artifact_key = f"morning-digest:{digest_date.isoformat()}:Europe/Vilnius"
    digest = MorningDigest(
        artifact_key=artifact_key,
        artifact_sha256="",
        digest_date=digest_date,
        timezone="Europe/Vilnius",
        observed_at=observed_at,
        state=state,
        request_watermark=requests.watermark,
        ruling_watermark=rulings.watermark,
        request_maintenance=proposal_summary,
        open_decisions=decisions,
        yesterday_rulings=yesterday,
        proof=proof,
        movement=movement_summary,
        movement_watermark=movement.watermark,
    )
    return _with_artifact_digest(digest)


def _with_artifact_digest(digest: MorningDigest) -> MorningDigest:
    canonical = json.dumps(
        digest.artifact_payload(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return MorningDigest(
        artifact_key=digest.artifact_key,
        artifact_sha256=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        digest_date=digest.digest_date,
        timezone=digest.timezone,
        observed_at=digest.observed_at,
        state=digest.state,
        request_watermark=digest.request_watermark,
        ruling_watermark=digest.ruling_watermark,
        request_maintenance=digest.request_maintenance,
        open_decisions=digest.open_decisions,
        yesterday_rulings=digest.yesterday_rulings,
        proof=digest.proof,
        movement=digest.movement,
        movement_watermark=digest.movement_watermark,
    )


def _proposal_summary(
    reading: SourceReading[ProposalSummaryInput],
) -> RequestMaintenanceProposalSummary:
    unreached = tuple(f"{item.key}:{item.reason}" for item in reading.unreached)
    if reading.state is ReadingState.UNKNOWN:
        return RequestMaintenanceProposalSummary(
            tuple(
                (kind, None)
                for kind in (
                    "duplicate",
                    "completed-but-open",
                    "supersession",
                    "kill",
                    "keep",
                )
            ),
            tuple((state, None) for state in ("OPEN", "CONFIRMED", "REJECTED")),
            None,
            "unavailable",
            unreached,
        )
    return derive_request_maintenance_summary(
        reading.rows,
        watermark=reading.watermark if reading.watermark is not None else 0,
        unreached_scopes=unreached,
    )


def _decision_section(
    reading: SourceReading[DigestRequestFact],
) -> DigestSection[DigestDecision]:
    rows = tuple(
        sorted(
            (
                item
                for item in reading.rows
                if item.decision_brief is not None and item.decision_brief.status == "open"
            ),
            key=lambda item: item.request_number,
        )
    )
    decisions = tuple(_decision(item) for item in rows)
    return DigestSection(
        reading.state,
        len(decisions),
        len(decisions) if reading.state is ReadingState.COMPLETE else None,
        decisions,
        reading.unreached,
    )


def _decision(item: DigestRequestFact) -> DigestDecision:
    brief = item.decision_brief
    if brief is None or brief.status != "open":
        raise ValueError("digest decisions require an authoritative open brief")
    return DigestDecision(
        item.request_id,
        item.reference,
        item.project_key,
        ReadingState.COMPLETE,
        brief,
        None,
    )


def _ruling_section(
    rulings: SourceReading[DigestRulingFact],
    requests: SourceReading[DigestRequestFact],
    request_index: dict[UUID, DigestRequestFact],
    digest_date: date,
) -> DigestSection[DigestRuling]:
    start = datetime.combine(digest_date - timedelta(days=1), time.min, _VILNIUS)
    end = datetime.combine(digest_date, time.min, _VILNIUS)
    rows = tuple(
        sorted(
            (item for item in rulings.rows if start <= item.recorded_at.astimezone(_VILNIUS) < end),
            key=lambda item: (item.recorded_at, item.ruling_id),
        )
    )
    projected = tuple(_ruling(item, requests, request_index) for item in rows)
    state = _combined_state(rulings.state, *(item.state for item in projected))
    unreached = rulings.unreached + tuple(
        UnreachedScope(
            f"ruling:{item.ruling_id}:execution-link",
            item.unknown_reason,
        )
        for item in projected
        if item.unknown_reason is not None
    )
    return DigestSection(
        state,
        len(projected),
        len(projected) if rulings.state is ReadingState.COMPLETE else None,
        projected,
        unreached,
    )


def _ruling(
    item: DigestRulingFact,
    requests: SourceReading[DigestRequestFact],
    request_index: dict[UUID, DigestRequestFact],
) -> DigestRuling:
    if item.linked_request_id is None:
        executions: tuple[DigestExecution, ...] = ()
    elif requests.state is ReadingState.UNKNOWN:
        return _unknown_ruling(item, "request-source-unreached")
    else:
        request = request_index.get(item.linked_request_id)
        if request is None:
            reason = (
                "request-source-unreached"
                if requests.state is ReadingState.PARTIAL
                else "linked-request-not-found"
            )
            return _unknown_ruling(item, reason)
        executions = (
            DigestExecution(
                request.request_id,
                request.reference,
                request.state,
                request.required_ticket_ids + request.optional_ticket_ids,
            ),
        )
    return DigestRuling(
        item.ruling_id,
        item.project_key,
        item.verbatim,
        item.recorded_at,
        ReadingState.COMPLETE,
        executions,
        None,
    )


def _unknown_ruling(item: DigestRulingFact, reason: str) -> DigestRuling:
    return DigestRuling(
        item.ruling_id,
        item.project_key,
        item.verbatim,
        item.recorded_at,
        ReadingState.PARTIAL,
        (),
        reason,
    )


def _proof_section(
    reading: SourceReading[DigestRequestFact],
    yesterday: DigestSection[DigestRuling],
    related_request_ids: set[UUID],
) -> DigestSection[DigestProof]:
    rows = tuple(
        sorted(
            (
                item
                for item in reading.rows
                if item.request_id in related_request_ids
                and (item.required_ticket_ids or item.optional_ticket_ids)
            ),
            key=lambda item: item.request_number,
        )
    )
    proof = tuple(
        DigestProof(
            item.request_id,
            item.reference,
            item.project_key,
            item.current_proof_count,
            tuple(
                DigestTicketLink(
                    ticket_id,
                    purpose,
                    f"/v1/tickets/{ticket_id}/timeline",
                )
                for purpose, ticket_ids in (
                    ("required", item.required_ticket_ids),
                    ("optional", item.optional_ticket_ids),
                )
                for ticket_id in ticket_ids
            ),
        )
        for item in rows
    )
    incomplete = tuple(item for item in proof if item.current_proof_count is None)
    state = _combined_state(
        reading.state,
        yesterday.state,
        *(ReadingState.PARTIAL for _item in incomplete),
    )
    unreached = (
        reading.unreached
        + yesterday.unreached
        + tuple(
            UnreachedScope(f"{item.request_reference}:proof-count", "proof-count-not-recorded")
            for item in incomplete
        )
    )
    sources_complete = (
        reading.state is ReadingState.COMPLETE and yesterday.state is ReadingState.COMPLETE
    )
    return DigestSection(
        state,
        len(proof),
        len(proof) if sources_complete else None,
        proof,
        unreached,
    )


def _combined_state(*states: ReadingState) -> ReadingState:
    if states and all(item is ReadingState.COMPLETE for item in states):
        return ReadingState.COMPLETE
    if states and all(item is ReadingState.UNKNOWN for item in states):
        return ReadingState.UNKNOWN
    return ReadingState.PARTIAL
