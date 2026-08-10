"""Work-owned Request policy, typed commands, and PostgreSQL authority."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    RecordProblem,
    credential_scope_refusal,
)
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext
from ctower_kernel.work._request_capture_sql import capture_request
from ctower_kernel.work._request_change_sql import change_request
from ctower_kernel.work._request_read_sql import list_requests
from ctower_kernel.work._request_types import (
    RequestBlocker,
    RequestCapture,
    RequestCaptureResult,
    RequestChange,
    RequestChangeResult,
    RequestClosureEvaluation,
    RequestList,
    RequestOwner,
    RequestPriority,
    RequestRow,
    RequestTicketRelation,
    RequestTriage,
)

__all__ = [
    "PostgresRequests",
    "RequestBlocker",
    "RequestCapture",
    "RequestCaptureResult",
    "RequestChangeResult",
    "RequestClosureEvaluation",
    "RequestList",
    "RequestOwner",
    "RequestPriority",
    "RequestRow",
    "RequestTicketRelation",
    "RequestTriage",
    "Requests",
]

_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_MAX_CONTENT_LENGTH = 65536
_MAX_REASON_LENGTH = 500
_MAX_BLOCKER_KEY_LENGTH = 256


class _RequestStore(Protocol):
    def capture(
        self,
        actor: Actor,
        command: RequestCapture,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCaptureResult | RecordProblem: ...

    def list(
        self,
        actor: Actor,
        *,
        project_key: str | None,
        now: datetime,
    ) -> RequestList | RecordProblem: ...

    def change(
        self,
        actor: Actor,
        command: RequestChange,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestChangeResult | RecordProblem: ...


class Requests:
    """Authorize Request semantics while the store owns atomic SQL choreography."""

    def __init__(
        self,
        store: _RequestStore,
        *,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    def capture(
        self,
        actor: Actor,
        command: RequestCapture,
        *,
        telemetry: TelemetryContext,
    ) -> RequestCaptureResult | RecordProblem:
        refusal = _capture_refusal(actor, command)
        if refusal is not None:
            return refusal
        outcome = self._store.capture(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit("work.request.capture", telemetry, outcome)
        return outcome

    def list(
        self,
        actor: Actor,
        *,
        project_key: str | None = None,
        telemetry: TelemetryContext,
    ) -> RequestList | RecordProblem:
        if project_key is not None and _PROJECT_KEY.fullmatch(project_key) is None:
            return _invalid(None, "Request project key is invalid")
        outcome = self._store.list(actor, project_key=project_key, now=self._clock())
        self._emit("work.request.list", telemetry, outcome)
        return outcome

    def prioritize(
        self, actor: Actor, command: RequestPriority, *, telemetry: TelemetryContext
    ) -> RequestChangeResult | RecordProblem:
        return self._change(actor, command, telemetry=telemetry)

    def triage(
        self, actor: Actor, command: RequestTriage, *, telemetry: TelemetryContext
    ) -> RequestChangeResult | RecordProblem:
        return self._change(actor, command, telemetry=telemetry)

    def assign_owner(
        self, actor: Actor, command: RequestOwner, *, telemetry: TelemetryContext
    ) -> RequestChangeResult | RecordProblem:
        return self._change(actor, command, telemetry=telemetry)

    def relate_ticket(
        self, actor: Actor, command: RequestTicketRelation, *, telemetry: TelemetryContext
    ) -> RequestChangeResult | RecordProblem:
        return self._change(actor, command, telemetry=telemetry)

    def set_blocker(
        self, actor: Actor, command: RequestBlocker, *, telemetry: TelemetryContext
    ) -> RequestChangeResult | RecordProblem:
        return self._change(actor, command, telemetry=telemetry)

    def evaluate_closure(
        self, actor: Actor, command: RequestClosureEvaluation, *, telemetry: TelemetryContext
    ) -> RequestChangeResult | RecordProblem:
        return self._change(actor, command, telemetry=telemetry)

    def _change(
        self, actor: Actor, command: RequestChange, *, telemetry: TelemetryContext
    ) -> RequestChangeResult | RecordProblem:
        refusal = _change_refusal(actor, command)
        if refusal is not None:
            return refusal
        outcome = self._store.change(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit(f"work.request.{_change_operation(command)}", telemetry, outcome)
        return outcome

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: RequestCaptureResult | RequestChangeResult | RequestList | RecordProblem,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )


class PostgresRequests:
    """Persist Work-owned Request facts through the existing Record transaction."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def capture(
        self,
        actor: Actor,
        command: RequestCapture,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCaptureResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: capture_request(
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
        project_key: str | None,
        now: datetime,
    ) -> RequestList | RecordProblem:
        return list_requests(self._dsn, actor, project_key=project_key, now=now)

    def change(
        self,
        actor: Actor,
        command: RequestChange,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestChangeResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: change_request(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )


def _capture_refusal(actor: Actor, command: RequestCapture) -> RecordProblem | None:
    if actor.kind not in {PrincipalKind.OPERATOR, PrincipalKind.COMMANDER}:
        return RecordProblem(
            code="request-capture-forbidden",
            detail="The authenticated Actor cannot capture a Request.",
            status=403,
            title="Request capture forbidden",
            command_id=command.client_command_id,
        )
    scope = credential_scope_refusal(
        actor, CredentialScope.CAPTURE, command_id=command.client_command_id
    )
    if scope is not None:
        return scope
    prohibited = prohibited_data_refusal((command.text,), command_id=command.client_command_id)
    if prohibited is not None:
        return prohibited
    if (
        _PROJECT_KEY.fullmatch(command.project_key) is None
        or not 1 <= len(command.text) <= _MAX_CONTENT_LENGTH
        or command.text.strip() != command.text
    ):
        return _invalid(command.client_command_id, "Request project or text is invalid")
    return None


def _change_refusal(actor: Actor, command: RequestChange) -> RecordProblem | None:
    scope = credential_scope_refusal(
        actor, CredentialScope.TRANSITION, command_id=command.client_command_id
    )
    if scope is not None:
        return scope
    prohibited = prohibited_data_refusal(
        tuple(
            value
            for value in (getattr(command, "reason", None), getattr(command, "blocker_key", None))
            if isinstance(value, str)
        ),
        command_id=command.client_command_id,
    )
    return prohibited or _change_shape_refusal(command)


def _change_shape_refusal(command: RequestChange) -> RecordProblem | None:
    detail = _base_shape_detail(command) or _operation_shape_detail(command)
    return _invalid(command.client_command_id, detail) if detail is not None else None


def _base_shape_detail(command: RequestChange) -> str | None:
    reason = getattr(command, "reason", None)
    if command.expected_version < 1:
        return "Request version or reason is invalid"
    if isinstance(reason, str) and (
        reason.strip() != reason or not 1 <= len(reason) <= _MAX_REASON_LENGTH
    ):
        return "Request version or reason is invalid"
    return None


def _operation_shape_detail(command: RequestChange) -> str | None:
    if isinstance(command, RequestPriority) and command.priority not in {"P0", "P1", "P2"}:
        return "Request priority is invalid"
    if isinstance(command, RequestTriage):
        return _triage_shape_detail(command)
    if isinstance(command, RequestTicketRelation) and command.purpose not in {
        "required",
        "optional",
    }:
        return "Request Ticket purpose is invalid"
    if (
        isinstance(command, RequestBlocker)
        and not 1 <= len(command.blocker_key) <= _MAX_BLOCKER_KEY_LENGTH
    ):
        return "Request blocker key is invalid"
    return None


def _triage_shape_detail(command: RequestTriage) -> str | None:
    if command.disposition not in {"ACCEPTED", "DUPLICATE", "REJECTED"}:
        return "Request triage disposition is invalid"
    requires_reason = command.disposition in {"DUPLICATE", "REJECTED"}
    if requires_reason != (command.reason is not None):
        return "Request triage reason is invalid"
    if (command.disposition == "DUPLICATE") != (command.canonical_request_id is not None):
        return "Request canonical identity is invalid"
    return None


def _change_operation(command: RequestChange) -> str:
    if isinstance(command, RequestPriority):
        return "priority"
    if isinstance(command, RequestTriage):
        return "triage"
    if isinstance(command, RequestOwner):
        return "owner"
    if isinstance(command, RequestTicketRelation):
        return "ticket_relation"
    if isinstance(command, RequestBlocker):
        return "blocker"
    return "closure_evaluation"


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()


def _invalid(command_id: UUID | None, detail: str) -> RecordProblem:
    return RecordProblem(
        code="invalid-request",
        detail=detail,
        status=422,
        title="Invalid Request command",
        command_id=command_id,
    )
