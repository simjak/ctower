"""Private replay outcome classification."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ctower_client.operations import OPERATIONS, SpoolPolicy
from ctowerctl.spool._crypto import RecordType
from ctowerctl.spool._identity import same_binding
from ctowerctl.spool._recovery import (
    AcceptedReceipt,
    CommandEnvelope,
    QuarantineReceipt,
    RecoveredRecord,
    RecoveryError,
    Session,
    command_payload,
    parse_utc,
    utc_text,
)
from ctowerctl.spool._redaction import (
    CanonicalRefusal,
    JsonObject,
    ServerRefusal,
    digest_json,
    reject_secret_material,
)

__all__ = [
    "DrainReport",
    "ReplayExecutor",
    "ReplayResponse",
    "ServerRefusal",
    "SpoolCommand",
    "drain_session",
]

_SUCCESS_MIN = 200
_SUCCESS_MAX = 300
_CLIENT_ERROR_MIN = 400
_SERVER_ERROR_MIN = 500
_TOO_MANY_REQUESTS = 429
_TEMPORARY_CLIENT_ERRORS = frozenset({408, 425})


class _BoundaryModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class SpoolCommand(_BoundaryModel):
    """Stable generated-operation identity and exact JSON request body."""

    operation_id: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9]{0,127}$")]
    path_parameters: JsonObject = Field(default_factory=dict)
    request_body: JsonObject
    command_id: UUID

    @model_validator(mode="after")
    def _deny_unspoolable_authority(self) -> SpoolCommand:
        operation = OPERATIONS.get(self.operation_id)
        if (
            operation is None
            or not operation.mutation
            or operation.spool_policy is not SpoolPolicy.ALLOWED
        ):
            raise ValueError("only generated allowlisted mutations may enter the spool")
        reject_secret_material(self.path_parameters)
        reject_secret_material(self.request_body)
        return self


class ReplayResponse(_BoundaryModel):
    """Typed transport observation used to decide a local durable transition."""

    status_code: Annotated[int, Field(ge=100, le=599)]
    command_id: UUID | None = None
    durability_state: Literal["accepted", "durability_pending"] | None = None
    response: JsonObject | None = None
    event_ids: tuple[str, ...] = ()
    acceptance_position: str | None = None
    problem_code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")] | None = None
    refusal: CanonicalRefusal = None


class ReplayExecutor(Protocol):
    """Confined generated-operation replay boundary."""

    def execute(self, command: SpoolCommand) -> ReplayResponse:
        """Invoke the generated operation with the current ephemeral credential."""


class DrainReport(_BoundaryModel):
    """Redacted ordered replay result."""

    attempted: Annotated[int, Field(ge=0)]
    accepted: Annotated[int, Field(ge=0)]
    quarantined: Annotated[int, Field(ge=0)]
    remaining_pending: Annotated[int, Field(ge=0)]
    barrier_sequence: int | None
    reason_code: str


class ReplayDecision(StrEnum):
    """Closed local transition decisions from one transport observation."""

    ACCEPT = "accept"
    KEEP_PENDING = "keep_pending"
    QUARANTINE = "quarantine"


class ResponseView(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def command_id(self) -> UUID | None: ...

    @property
    def durability_state(self) -> str | None: ...


def classify(response: ResponseView, expected_command_id: UUID) -> tuple[ReplayDecision, str]:
    """Classify without interpreting server authorization or transition policy."""

    decision = ReplayDecision.KEEP_PENDING
    reason = "ambiguous_protocol_response"
    status = response.status_code
    if status == _TOO_MANY_REQUESTS or status >= _SERVER_ERROR_MIN:
        reason = "temporary_server_response"
    elif _CLIENT_ERROR_MIN <= status < _SERVER_ERROR_MIN:
        decision = (
            ReplayDecision.KEEP_PENDING
            if status in _TEMPORARY_CLIENT_ERRORS
            else ReplayDecision.QUARANTINE
        )
        reason = (
            "temporary_server_response"
            if decision is ReplayDecision.KEEP_PENDING
            else "permanent_server_rejection"
        )
    elif _SUCCESS_MIN <= status < _SUCCESS_MAX:
        decision, reason = _success_decision(response, expected_command_id)
    return decision, reason


def drain_session(
    session: Session,
    executor: ReplayExecutor,
    credential_binding: str,
) -> DrainReport:
    """Replay globally in order and stop at the first pending or quarantine barrier."""

    if session.corrupt_records:
        raise RecoveryError("corrupt quarantine blocks normal ordered replay")
    commands = tuple(sorted(session.commands(), key=lambda item: item.stored.sequence))
    barrier = next((item for item in commands if item.stored.directory == "quarantine"), None)
    pending = tuple(item for item in commands if item.stored.directory == "pending")
    if barrier is not None and (
        not pending or barrier.stored.sequence < pending[0].stored.sequence
    ):
        return _report(
            session,
            0,
            0,
            0,
            barrier.stored.sequence,
            reason_code="quarantine_barrier",
        )
    attempted = accepted = quarantined = 0
    reason = "empty"
    for record in pending:
        payload = command_payload(record)
        binding_reason = _binding_refusal(payload, credential_binding)
        if binding_reason is not None:
            _quarantine(session, record, binding_reason, None)
            quarantined += 1
            reason = binding_reason
            break
        if datetime.now(UTC) >= parse_utc(payload.expires_at):
            _quarantine(session, record, "expired", None)
            quarantined += 1
            reason = "expired"
            break
        attempted += 1
        response = _execute(executor, payload)
        decision, reason = classify(response, UUID(payload.command_id))
        if decision is ReplayDecision.ACCEPT:
            _accept(session, record, payload, response)
            accepted += 1
            continue
        if decision is ReplayDecision.QUARANTINE:
            _quarantine(session, record, reason, response.response, refusal=response.refusal)
            quarantined += 1
        break
    return _report(
        session,
        attempted,
        accepted,
        quarantined,
        _barrier(session),
        reason_code=reason,
    )


def _binding_refusal(
    payload: CommandEnvelope,
    current_binding: str,
) -> str | None:
    if payload.credential_binding is None:
        return "credential_binding_missing"
    if not same_binding(payload.credential_binding, current_binding):
        return "credential_identity_mismatch"
    return None


def _success_decision(
    response: ResponseView,
    expected_command_id: UUID,
) -> tuple[ReplayDecision, str]:
    if response.command_id != expected_command_id:
        return ReplayDecision.KEEP_PENDING, "mismatched_success"
    if response.durability_state == "durability_pending":
        return ReplayDecision.KEEP_PENDING, "durability_pending"
    if response.durability_state == "accepted":
        return ReplayDecision.ACCEPT, "accepted"
    return ReplayDecision.KEEP_PENDING, "malformed_success"


def _execute(executor: ReplayExecutor, payload: CommandEnvelope) -> ReplayResponse:
    try:
        command = SpoolCommand(
            operation_id=payload.operation_id,
            path_parameters=payload.path_parameters,
            request_body=payload.request_body,
            command_id=UUID(payload.command_id),
        )
    except ValueError:
        return ReplayResponse(status_code=422, problem_code="operation_not_replayable")
    try:
        return executor.execute(command)
    except (ConnectionError, OSError, TimeoutError):
        return ReplayResponse(status_code=503)


def _accept(
    session: Session,
    record: RecoveredRecord,
    payload: CommandEnvelope,
    response: ReplayResponse,
) -> None:
    body = response.response
    if body is not None:
        reject_secret_material(body)
    receipt = AcceptedReceipt(
        schema_version=1,
        command_sequence=record.stored.sequence,
        command_hash=record.opened.record_hash,
        command_id=payload.command_id,
        status_code=response.status_code,
        durability_state="accepted",
        response=body,
        response_digest=digest_json({"response": body}),
        event_ids=response.event_ids,
        acceptance_position=response.acceptance_position,
        accepted_at=utc_text(datetime.now(UTC)),
    )
    session.append(RecordType.ACCEPTED_RECEIPT, "accepted", receipt)
    session.move(record, "accepted")


def _quarantine(
    session: Session,
    record: RecoveredRecord,
    reason_code: str,
    response: JsonObject | None,
    *,
    refusal: ServerRefusal | None = None,
) -> None:
    receipt = QuarantineReceipt(
        schema_version=2,
        command_sequence=record.stored.sequence,
        command_hash=record.opened.record_hash,
        reason_code=_reason_code(reason_code),
        response_digest=digest_json(response) if response is not None else None,
        quarantined_at=utc_text(datetime.now(UTC)),
        refusal=refusal,
    )
    session.append(RecordType.QUARANTINE_RECEIPT, "quarantine", receipt)
    session.move(record, "quarantine")


def _report(
    session: Session,
    attempted: int,
    accepted: int,
    quarantined: int,
    barrier_sequence: int | None,
    *,
    reason_code: str,
) -> DrainReport:
    remaining = sum(1 for item in session.commands() if item.stored.directory == "pending")
    return DrainReport(
        attempted=attempted,
        accepted=accepted,
        quarantined=quarantined,
        remaining_pending=remaining,
        barrier_sequence=barrier_sequence,
        reason_code=_reason_code(reason_code),
    )


def _barrier(session: Session) -> int | None:
    return min(
        (
            item.stored.sequence
            for item in session.commands()
            if item.stored.directory == "quarantine"
        ),
        default=None,
    )


def _reason_code(value: str) -> str:
    normalized = "".join(
        character if character.isalnum() else "_" for character in value.casefold()
    )
    normalized = "_".join(part for part in normalized.split("_") if part)
    return (normalized or "unknown")[:64]
