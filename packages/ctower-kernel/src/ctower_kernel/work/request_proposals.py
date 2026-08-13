"""Work-owned Request-maintenance proposal policy and PostgreSQL authority."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, credential_scope_refusal
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext
from ctower_kernel.work._request_proposal_append_sql import append_request_proposal
from ctower_kernel.work._request_proposal_decision_sql import (
    confirm_request_proposal,
    reject_request_proposal,
)
from ctower_kernel.work._request_proposal_read_sql import list_request_proposals
from ctower_kernel.work._request_proposal_types import (
    ProofEvidencePointer,
    RecordEventEvidencePointer,
    RequestMaintenanceProposalAppend,
    RequestMaintenanceProposalAppendResult,
    RequestMaintenanceProposalConfirm,
    RequestMaintenanceProposalDecisionResult,
    RequestMaintenanceProposalList,
    RequestMaintenanceProposalReject,
    RequestMaintenanceProposalRow,
    RequestProposalEvidencePointer,
)

__all__ = [
    "PostgresRequestProposals",
    "ProofEvidencePointer",
    "RecordEventEvidencePointer",
    "RequestMaintenanceProposalAppend",
    "RequestMaintenanceProposalAppendResult",
    "RequestMaintenanceProposalConfirm",
    "RequestMaintenanceProposalDecisionResult",
    "RequestMaintenanceProposalList",
    "RequestMaintenanceProposalReject",
    "RequestMaintenanceProposalRow",
    "RequestProposals",
]

_AMBIGUITIES = frozenset(
    {
        "evidence-conflicting-or-incomplete",
        "duplicate-uncertain",
        "supersession-unclear",
        "target-version-stale",
        "completion-unproven",
    }
)
_KINDS = frozenset({"duplicate", "completed-but-open", "supersession", "kill", "keep"})
_PROJECT = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_TEXT = 65536
_MAX_REASON = 500
_MAX_EVIDENCE = 100
_MAX_EVENT_KIND = 128


class _RequestProposalStore(Protocol):
    def append(
        self,
        actor: Actor,
        command: RequestMaintenanceProposalAppend,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalAppendResult | RecordProblem: ...

    def list(
        self,
        actor: Actor,
        *,
        proposal_id: UUID | None,
        project_key: str | None,
        kind: str | None,
        state: str | None,
        now: datetime,
    ) -> RequestMaintenanceProposalList | RecordProblem: ...

    def confirm(
        self,
        actor: Actor,
        command: RequestMaintenanceProposalConfirm,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalDecisionResult | RecordProblem: ...

    def reject(
        self,
        actor: Actor,
        command: RequestMaintenanceProposalReject,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalDecisionResult | RecordProblem: ...


class RequestProposals:
    """Validate proposal intent before the store owns atomic SQL choreography."""

    def __init__(
        self,
        store: _RequestProposalStore,
        *,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    def append(
        self,
        actor: Actor,
        command: RequestMaintenanceProposalAppend,
        *,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalAppendResult | RecordProblem:
        problem = _append_refusal(actor, command)
        if problem is not None:
            return problem
        return self._store.append(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )

    def list(
        self,
        actor: Actor,
        *,
        proposal_id: UUID | None = None,
        project_key: str | None = None,
        kind: str | None = None,
        state: str | None = None,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalList | RecordProblem:
        if project_key is not None and _PROJECT.fullmatch(project_key) is None:
            return _problem("proposal-project-invalid", "Proposal Project is invalid", 422)
        if kind is not None and kind not in _KINDS:
            return _problem("proposal-kind-invalid", "Proposal kind is invalid", 422)
        if state is not None and state not in {"OPEN", "CONFIRMED", "REJECTED"}:
            return _problem("proposal-state-invalid", "Proposal state is invalid", 422)
        outcome = self._store.list(
            actor,
            proposal_id=proposal_id,
            project_key=project_key,
            kind=kind,
            state=state,
            now=self._clock(),
        )
        self._telemetry.emit(
            "work.request-proposal.list",
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "read",
        )
        return outcome

    def confirm(
        self,
        actor: Actor,
        command: RequestMaintenanceProposalConfirm,
        *,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalDecisionResult | RecordProblem:
        problem = _decision_refusal(
            actor, command.client_command_id, command.expected_proposal_version
        )
        if problem is not None:
            return problem
        return self._store.confirm(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )

    def reject(
        self,
        actor: Actor,
        command: RequestMaintenanceProposalReject,
        *,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalDecisionResult | RecordProblem:
        problem = _decision_refusal(
            actor, command.client_command_id, command.expected_proposal_version
        )
        if (
            problem is None
            and command.reason is not None
            and not 1 <= len(command.reason) <= _MAX_REASON
        ):
            problem = _problem(
                "proposal-reason-invalid",
                "Proposal rejection reason is invalid",
                422,
                command.client_command_id,
            )
        if problem is not None:
            return problem
        return self._store.reject(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )


class PostgresRequestProposals:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def append(
        self,
        actor: Actor,
        command: RequestMaintenanceProposalAppend,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalAppendResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: append_request_proposal(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )

    def list(
        self,
        actor: Actor,
        *,
        proposal_id: UUID | None,
        project_key: str | None,
        kind: str | None,
        state: str | None,
        now: datetime,
    ) -> RequestMaintenanceProposalList | RecordProblem:
        return list_request_proposals(
            self._dsn,
            actor,
            proposal_id=proposal_id,
            project_key=project_key,
            kind=kind,
            state=state,
            now=now,
        )

    def confirm(
        self,
        actor: Actor,
        command: RequestMaintenanceProposalConfirm,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalDecisionResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: confirm_request_proposal(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )

    def reject(
        self,
        actor: Actor,
        command: RequestMaintenanceProposalReject,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestMaintenanceProposalDecisionResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: reject_request_proposal(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )


def _append_refusal(
    actor: Actor, command: RequestMaintenanceProposalAppend
) -> RecordProblem | None:
    for check in (_actor_refusal, _shape_refusal, _content_refusal):
        problem = check(actor, command)
        if problem is not None:
            return problem
    return None


def _actor_refusal(actor: Actor, command: RequestMaintenanceProposalAppend) -> RecordProblem | None:
    if actor.kind not in {PrincipalKind.OPERATOR, PrincipalKind.COMMANDER}:
        return _problem(
            "proposal-append-forbidden",
            "Actor cannot append Request-maintenance proposals",
            403,
            command.client_command_id,
        )
    scope = credential_scope_refusal(
        actor, CredentialScope.TRANSITION, command_id=command.client_command_id
    )
    if scope is not None:
        return scope
    return None


def _shape_refusal(actor: Actor, command: RequestMaintenanceProposalAppend) -> RecordProblem | None:
    del actor
    return _basic_shape_refusal(command) or _relation_shape_refusal(command)


def _basic_shape_refusal(command: RequestMaintenanceProposalAppend) -> RecordProblem | None:
    if _PROJECT.fullmatch(command.project_key) is None or command.kind not in _KINDS:
        return _problem(
            "proposal-invalid",
            "Proposal project or kind is invalid",
            422,
            command.client_command_id,
        )
    if command.basis not in {"recorded-evidence", "similarity"}:
        return _problem(
            "proposal-invalid", "Proposal basis is invalid", 422, command.client_command_id
        )
    if command.ambiguity_reason not in _AMBIGUITIES | {None}:
        return _problem(
            "proposal-invalid", "Proposal ambiguity is invalid", 422, command.client_command_id
        )
    if command.target_expected_version < 1 or command.source_record_position < 0:
        return _problem(
            "proposal-invalid",
            "Proposal version or watermark is invalid",
            422,
            command.client_command_id,
        )
    return None


def _relation_shape_refusal(command: RequestMaintenanceProposalAppend) -> RecordProblem | None:
    paired = command.kind in {"duplicate", "supersession"}
    relation_invalid = (
        not _paired_relation_valid(command) if paired else _relation_is_present(command)
    )
    if relation_invalid or (command.basis == "similarity" and command.kind != "duplicate"):
        return _problem(
            "proposal-invalid", "Proposal relation is incomplete", 422, command.client_command_id
        )
    return None


def _paired_relation_valid(command: RequestMaintenanceProposalAppend) -> bool:
    return (
        command.related_request_id is not None
        and command.related_expected_version is not None
        and command.related_expected_version >= 1
        and command.related_text is not None
        and command.related_request_id != command.target_request_id
    )


def _relation_is_present(command: RequestMaintenanceProposalAppend) -> bool:
    return any(
        value is not None
        for value in (
            command.related_request_id,
            command.related_expected_version,
            command.related_text,
        )
    )


def _content_refusal(
    actor: Actor, command: RequestMaintenanceProposalAppend
) -> RecordProblem | None:
    del actor
    texts = (command.target_text,) + (
        (command.related_text,) if command.related_text is not None else ()
    )
    prohibited = prohibited_data_refusal(texts, command_id=command.client_command_id)
    if prohibited is not None:
        return prohibited
    if any(not 1 <= len(item) <= _MAX_TEXT or "\x00" in item for item in texts):
        return _problem(
            "proposal-quote-invalid",
            "Proposal exact text is invalid",
            422,
            command.client_command_id,
        )
    if not 1 <= len(command.evidence) <= _MAX_EVIDENCE or not all(
        _evidence_valid(item) for item in command.evidence
    ):
        return _problem(
            "proposal-evidence-invalid",
            "Proposal evidence is invalid",
            422,
            command.client_command_id,
        )
    return None


def _evidence_valid(pointer: RequestProposalEvidencePointer) -> bool:
    if isinstance(pointer, RecordEventEvidencePointer):
        return (
            pointer.kind == "record-event"
            and 1 <= len(pointer.event_kind) <= _MAX_EVENT_KIND
            and _SHA256.fullmatch(pointer.event_digest) is not None
        )
    return (
        pointer.kind == "proof-evidence" and _SHA256.fullmatch(pointer.artifact_digest) is not None
    )


def _decision_refusal(
    actor: Actor, command_id: UUID, expected_version: int
) -> RecordProblem | None:
    if actor.kind is not PrincipalKind.OPERATOR:
        return _problem(
            "proposal-decision-forbidden", "Only an operator may decide a proposal", 403, command_id
        )
    scope = credential_scope_refusal(actor, CredentialScope.TRANSITION, command_id=command_id)
    if scope is not None:
        return scope
    if expected_version != 1:
        return _problem("proposal-version-conflict", "Proposal version is stale", 409, command_id)
    return None


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()


def _problem(code: str, detail: str, status: int, command_id: UUID | None = None) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=detail,
        status=status,
        title="Request proposal refused",
        command_id=command_id,
    )
