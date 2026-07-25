"""Work-owned policy for explicit durable inbound-thread intents."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.intake import (
    IntakeCommandResult,
    IntakeIntent,
    IntakePromotionCommand,
    IntakeSubmitCommand,
    IntakeTaint,
)
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__ = ["Intake"]

_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_PRIORITIES = frozenset({"P0", "P1", "P2"})
_MAX_CONTENT_LENGTH = 65536
_MAX_SOURCE_KIND_LENGTH = 64
_MAX_SOURCE_REF_LENGTH = 256
_MAX_TITLE_LENGTH = 200


class _IntakeWriter(Protocol):
    def submit_intake(
        self,
        actor: Actor,
        command: IntakeSubmitCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> IntakeCommandResult | RecordProblem: ...

    def promote_intake(
        self,
        actor: Actor,
        command: IntakePromotionCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> IntakeCommandResult | RecordProblem: ...


class Intake:
    """Authorize explicit intake semantics while Record owns the atomic write."""

    def __init__(
        self,
        writer: _IntakeWriter,
        *,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._writer = writer
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    def submit(
        self, actor: Actor, command: IntakeSubmitCommand, *, telemetry: TelemetryContext
    ) -> IntakeCommandResult | RecordProblem:
        refusal = _submit_refusal(actor, command)
        if refusal is not None:
            return refusal
        outcome = self._writer.submit_intake(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit("work.intake.submit", telemetry, outcome)
        return outcome

    def promote(
        self, actor: Actor, command: IntakePromotionCommand, *, telemetry: TelemetryContext
    ) -> IntakeCommandResult | RecordProblem:
        refusal = _promotion_refusal(actor, command)
        if refusal is not None:
            return refusal
        outcome = self._writer.promote_intake(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit("work.intake.promote", telemetry, outcome)
        return outcome

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: IntakeCommandResult | RecordProblem,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )


def _submit_refusal(actor: Actor, command: IntakeSubmitCommand) -> RecordProblem | None:
    capability = _capability_refusal(actor, command.client_command_id)
    if capability is not None:
        return capability
    if (
        _PROJECT_KEY.fullmatch(command.project_key) is None
        or not 1 <= len(command.source.kind) <= _MAX_SOURCE_KIND_LENGTH
        or not 1 <= len(command.source.ref) <= _MAX_SOURCE_REF_LENGTH
        or not 1 <= len(command.content) <= _MAX_CONTENT_LENGTH
    ):
        return _invalid(command.client_command_id, "Invalid inbound project, source, or content")
    if (command.thread_id is None) != (command.expected_thread_version is None):
        return _invalid(
            command.client_command_id,
            "Existing thread appends require an expected version; new threads forbid one",
        )
    if command.expected_thread_version is not None and command.expected_thread_version < 1:
        return _invalid(command.client_command_id, "Expected thread version must be positive")
    if command.taint is IntakeTaint.QUARANTINE_REQUIRED:
        return None
    return _intent_refusal(
        actor,
        command.client_command_id,
        command.intent,
        command.initial_custodian_id,
        command.priority,
        command.title,
        command.target_ticket_id,
        command.expected_ticket_version,
    )


def _promotion_refusal(actor: Actor, command: IntakePromotionCommand) -> RecordProblem | None:
    capability = _capability_refusal(actor, command.client_command_id)
    if capability is not None:
        return capability
    if command.expected_thread_version < 1 or command.intent is IntakeIntent.DISCUSSION:
        return _invalid(command.client_command_id, "Promotion must be actionable and versioned")
    return _intent_refusal(
        actor,
        command.client_command_id,
        command.intent,
        command.initial_custodian_id,
        command.priority,
        command.title,
        command.target_ticket_id,
        command.expected_ticket_version,
    )


def _intent_refusal(
    actor: Actor,
    command_id: UUID,
    intent: IntakeIntent,
    custodian_id: UUID | None,
    priority: str | None,
    title: str | None,
    target_id: UUID | None,
    target_version: int | None,
) -> RecordProblem | None:
    create_fields = (custodian_id, priority, title)
    if intent is IntakeIntent.DISCUSSION:
        if any(value is not None for value in (*create_fields, target_id, target_version)):
            return _invalid(command_id, "Discussion intake cannot contain ticket mutation fields")
        return None
    if intent is IntakeIntent.CREATE_TICKET:
        return _create_refusal(
            actor,
            command_id,
            custodian_id,
            priority,
            title,
            target_id,
            target_version,
        )
    return _link_refusal(
        command_id,
        custodian_id,
        priority,
        title,
        target_id,
        target_version,
    )


def _create_refusal(
    actor: Actor,
    command_id: UUID,
    custodian_id: UUID | None,
    priority: str | None,
    title: str | None,
    target_id: UUID | None,
    target_version: int | None,
) -> RecordProblem | None:
    if (
        custodian_id is None
        or priority not in _PRIORITIES
        or title is None
        or not 1 <= len(title) <= _MAX_TITLE_LENGTH
        or target_id is not None
        or target_version is not None
    ):
        return _invalid(command_id, "Create-ticket intake fields are incomplete or mixed")
    if priority == "P0" and actor.kind is not PrincipalKind.OPERATOR:
        return _unauthorized(command_id, "Only an operator may create a P0 intake ticket")
    return None


def _link_refusal(
    command_id: UUID,
    custodian_id: UUID | None,
    priority: str | None,
    title: str | None,
    target_id: UUID | None,
    target_version: int | None,
) -> RecordProblem | None:
    if (
        not isinstance(target_id, UUID)
        or target_version is None
        or target_version < 1
        or any(value is not None for value in (custodian_id, priority, title))
    ):
        return _invalid(command_id, "Link-ticket intake fields are incomplete or mixed")
    return None


def _capability_refusal(actor: Actor, command_id: UUID) -> RecordProblem | None:
    if actor.kind is PrincipalKind.MIGRATION_IMPORTER:
        return RecordProblem(
            code="migration-capability-denied",
            detail="The migration importer has no inbound intake authority.",
            status=403,
            title="Migration capability denied",
            command_id=command_id,
        )
    if actor.kind not in {PrincipalKind.OPERATOR, PrincipalKind.COMMANDER}:
        return _unauthorized(command_id, "Inbound intake requires task authority")
    return None


def _invalid(command_id: UUID, detail: str) -> RecordProblem:
    return RecordProblem(
        code="validation-error",
        detail=detail,
        status=422,
        title="Invalid intake command",
        command_id=command_id,
    )


def _unauthorized(command_id: UUID, detail: str) -> RecordProblem:
    return RecordProblem(
        code="unauthorized",
        detail=detail,
        status=403,
        title="Intake command refused",
        command_id=command_id,
    )


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()
