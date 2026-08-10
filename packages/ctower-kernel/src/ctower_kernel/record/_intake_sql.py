"""Record-owned atomic inbound-thread persistence and exact replay."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record._intake_apply_sql import (
    apply_action_state as _apply_action_state,
)
from ctower_kernel.record._intake_apply_sql import (
    insert_inbound_event as _insert_inbound_event,
)
from ctower_kernel.record._intake_command_sql import (
    IntakeAction as _Action,
)
from ctower_kernel.record._intake_command_sql import (
    IntakeThreadState as _ThreadState,
)
from ctower_kernel.record._intake_command_sql import _SubmitIds
from ctower_kernel.record._intake_command_sql import (
    advance_thread as _advance_thread,
)
from ctower_kernel.record._intake_command_sql import (
    event_ids as _event_ids,
)
from ctower_kernel.record._intake_command_sql import (
    lock_inbound_for_promotion as _lock_inbound_for_promotion,
)
from ctower_kernel.record._intake_command_sql import (
    refuse as _refuse,
)
from ctower_kernel.record._intake_command_sql import (
    resolve_inbound_for_promotion as _resolve_inbound_for_promotion,
)
from ctower_kernel.record._intake_command_sql import (
    result_from_payload as _result_from_payload,
)
from ctower_kernel.record._intake_command_sql import (
    scope_problem as _scope_problem,
)
from ctower_kernel.record._intake_command_sql import (
    subjects as _subjects,
)
from ctower_kernel.record._intake_command_sql import (
    uuid7 as _uuid7,
)
from ctower_kernel.record._intake_event_sql import (
    promotion_commits as _promotion_commits,
)
from ctower_kernel.record._intake_event_sql import (
    submit_commits as _submit_commits,
)
from ctower_kernel.record._intake_state_sql import (
    initial_custody_problem as _initial_custody_problem,
)
from ctower_kernel.record._intake_state_sql import (
    insert_new_thread as _insert_new_thread,
)
from ctower_kernel.record._intake_state_sql import (
    lock_thread as _lock_thread,
)
from ctower_kernel.record._intake_state_sql import (
    prepare_action as _prepare_action,
)
from ctower_kernel.record._intake_state_sql import (
    project_available as _project_available,
)
from ctower_kernel.record._intake_state_sql import (
    reserve_source_alias as _reserve_source_alias,
)
from ctower_kernel.record.intake import (
    InboundSource,
    IntakeCommandResult,
    IntakeIntent,
    IntakeOutcome,
    IntakePromotionCommand,
    IntakeSubmitCommand,
    IntakeTaint,
)
from ctower_kernel.record.ticket_creation import TicketCreationIds, new_ticket_creation_ids
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

type _SubmitPreparation = tuple[_SubmitIds, _ThreadState, _Action]
type _PromotionPreparation = tuple[dict[str, object], UUID, _Action]


def submit_intake(
    dsn: str,
    actor: Actor,
    command: IntakeSubmitCommand,
    *,
    request_digest: bytes,
    policy_refusal: RecordProblem | None = None,
    now: datetime,
    telemetry: TelemetryContext,
) -> IntakeCommandResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        prepared = _prepare_submit(
            connection,
            transaction,
            actor,
            command,
            request_digest=request_digest,
            policy_refusal=policy_refusal,
            now=now,
        )
        if not isinstance(prepared, tuple):
            return prepared
        identifiers, state, action = prepared
        return _commit_submit(
            connection,
            transaction,
            actor,
            command,
            identifiers,
            state,
            action,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def promote_intake(
    dsn: str,
    actor: Actor,
    command: IntakePromotionCommand,
    *,
    request_digest: bytes,
    policy_refusal: RecordProblem | None = None,
    now: datetime,
    telemetry: TelemetryContext,
) -> IntakeCommandResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        prepared = _prepare_promotion(
            connection,
            transaction,
            actor,
            command,
            request_digest=request_digest,
            policy_refusal=policy_refusal,
            now=now,
        )
        if not isinstance(prepared, tuple):
            return prepared
        inbound, thread_id, action = prepared
        return _commit_promotion(
            connection,
            transaction,
            actor,
            command,
            inbound,
            thread_id,
            action,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _prepare_submit(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: IntakeSubmitCommand,
    *,
    request_digest: bytes,
    policy_refusal: RecordProblem | None,
    now: datetime,
) -> _SubmitPreparation | IntakeCommandResult | RecordProblem:
    replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
    if replay is not None:
        return replay if isinstance(replay, RecordProblem) else _result_from_payload(replay)
    if policy_refusal is not None:
        return _refuse(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            policy_refusal,
            now,
        )
    custody_problem = _initial_custody_problem(connection, actor, command)
    if custody_problem is not None:
        return _refuse(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            custody_problem,
            now,
        )
    identifiers = _submit_ids(command, now)
    durable = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        _subjects(
            identifiers.thread,
            identifiers.inbound_event,
            identifiers.ticket_subject,
            identifiers.request,
        ),
        now=now,
    )
    if durable is not None:
        return durable
    return _prepare_submit_after_durability(
        connection,
        transaction,
        actor,
        command,
        identifiers,
        request_digest=request_digest,
        now=now,
    )


def _prepare_submit_after_durability(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: IntakeSubmitCommand,
    identifiers: _SubmitIds,
    *,
    request_digest: bytes,
    now: datetime,
) -> _SubmitPreparation | RecordProblem:
    if not _project_available(connection, actor, command.project_key):
        scope = _scope_problem(command.client_command_id)
        return _refuse(transaction, actor, command.client_command_id, request_digest, scope, now)
    alias_problem = _reserve_source_alias(connection, actor, command, identifiers.thread)
    if alias_problem is not None:
        return _refuse(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            alias_problem,
            now,
        )
    state = _lock_thread(connection, actor, command, identifiers.thread)
    if isinstance(state, RecordProblem):
        return _refuse(transaction, actor, command.client_command_id, request_digest, state, now)
    request_ids = (
        None
        if identifiers.request is None or identifiers.request_event is None
        else (identifiers.request, identifiers.request_event)
    )
    action = _prepare_action(
        connection,
        actor,
        command,
        ticket_ids=identifiers.ticket,
        request_ids=request_ids,
        now=now,
    )
    if not isinstance(action, RecordProblem):
        return identifiers, state, action
    return _refuse(
        transaction,
        actor,
        command.client_command_id,
        request_digest,
        action,
        now,
    )


def _commit_submit(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: IntakeSubmitCommand,
    identifiers: _SubmitIds,
    state: _ThreadState,
    action: _Action,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> IntakeCommandResult:
    inbound_outbox_id = _uuid7(now)
    result = _submit_result(command, state, identifiers.inbound_event, action)
    _insert_new_thread(connection, actor, command, state, now=now)
    _insert_inbound_event(connection, actor, command, state, result, now=now)
    _apply_action_state(
        connection,
        actor,
        command.client_command_id,
        action,
        result,
        content=command.content,
        promoted=False,
        now=now,
    )
    if not state.is_new:
        _advance_thread(connection, actor.tenant_id, identifiers.thread, state.version - 1)
    commits = _submit_commits(
        actor,
        command,
        state,
        result,
        action,
        identifiers.inbound_event,
        inbound_outbox_id,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    transaction.commit_batch(
        commits,
        response_body=result.response_payload(),
        status_code=201,
        telemetry=telemetry,
        now=now,
        subjects=_subjects(
            identifiers.thread,
            identifiers.inbound_event,
            action.ticket_id,
            action.request_id,
        ),
    )
    return result


def _prepare_promotion(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: IntakePromotionCommand,
    *,
    request_digest: bytes,
    policy_refusal: RecordProblem | None,
    now: datetime,
) -> _PromotionPreparation | IntakeCommandResult | RecordProblem:
    replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
    if replay is not None:
        return replay if isinstance(replay, RecordProblem) else _result_from_payload(replay)
    if policy_refusal is not None:
        return _refuse(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            policy_refusal,
            now,
        )
    custody_problem = _initial_custody_problem(connection, actor, command)
    if custody_problem is not None:
        return _refuse(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            custody_problem,
            now,
        )
    resolved = _resolve_inbound_for_promotion(connection, actor, command)
    if isinstance(resolved, RecordProblem):
        return _refuse(transaction, actor, command.client_command_id, request_digest, resolved, now)
    ticket_ids = _new_ticket_ids(command.intent, now)
    request_ids = _new_request_ids(command.intent, now)
    ticket_subject = ticket_ids.ticket if ticket_ids is not None else command.target_ticket_id
    durable = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        _subjects(
            resolved,
            command.inbound_event_id,
            ticket_subject,
            None if request_ids is None else request_ids[0],
        ),
        now=now,
    )
    if durable is not None:
        return durable
    return _prepare_promotion_after_durability(
        connection,
        transaction,
        actor,
        command,
        resolved,
        ticket_ids,
        request_ids,
        request_digest=request_digest,
        now=now,
    )


def _prepare_promotion_after_durability(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: IntakePromotionCommand,
    resolved: UUID,
    ticket_ids: TicketCreationIds | None,
    request_ids: tuple[UUID, UUID] | None,
    *,
    request_digest: bytes,
    now: datetime,
) -> _PromotionPreparation | RecordProblem:
    inbound = _lock_inbound_for_promotion(connection, actor, command)
    if isinstance(inbound, RecordProblem):
        return _refuse(transaction, actor, command.client_command_id, request_digest, inbound, now)
    thread_id = cast(UUID, inbound["thread_id"])
    if thread_id != resolved:
        raise RuntimeError("immutable inbound event changed thread ownership")
    if not _project_available(connection, actor, str(inbound["project_key"])):
        problem = _scope_problem(command.client_command_id)
        return _refuse(transaction, actor, command.client_command_id, request_digest, problem, now)
    action = _prepare_action(
        connection,
        actor,
        command,
        project_key=str(inbound["project_key"]),
        source=InboundSource(str(inbound["source_kind"]), str(inbound["source_ref"])),
        ticket_ids=ticket_ids,
        request_ids=request_ids,
        now=now,
    )
    if not isinstance(action, RecordProblem):
        return inbound, thread_id, action
    return _refuse(
        transaction,
        actor,
        command.client_command_id,
        request_digest,
        action,
        now,
    )


def _commit_promotion(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: IntakePromotionCommand,
    inbound: dict[str, object],
    thread_id: UUID,
    action: _Action,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> IntakeCommandResult:
    event_id, outbox_id = _uuid7(now), _uuid7(now)
    source = InboundSource(str(inbound["source_kind"]), str(inbound["source_ref"]))
    result = IntakeCommandResult(
        command_id=command.client_command_id,
        event_ids=_event_ids(event_id, action),
        inbound_event_id=command.inbound_event_id,
        outcome=action.outcome,
        project_key=str(inbound["project_key"]),
        source=source,
        thread_id=thread_id,
        thread_version=command.expected_thread_version + 1,
        ticket_id=action.ticket_id,
        ticket_version=action.ticket_version,
        request_id=action.request_id,
        request_number=action.request_number,
    )
    _apply_action_state(
        connection,
        actor,
        command.client_command_id,
        action,
        result,
        content=str(inbound["content"]),
        promoted=True,
        now=now,
    )
    _advance_thread(connection, actor.tenant_id, thread_id, command.expected_thread_version)
    commits = _promotion_commits(
        actor,
        command,
        inbound,
        result,
        action,
        event_id,
        outbox_id,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    transaction.commit_batch(
        commits,
        response_body=result.response_payload(),
        status_code=200,
        telemetry=telemetry,
        now=now,
        subjects=_subjects(
            thread_id,
            command.inbound_event_id,
            action.ticket_id,
            action.request_id,
        ),
    )
    return result


def _submit_result(
    command: IntakeSubmitCommand,
    state: _ThreadState,
    inbound_event_id: UUID,
    action: _Action,
) -> IntakeCommandResult:
    return IntakeCommandResult(
        command_id=command.client_command_id,
        event_ids=_event_ids(inbound_event_id, action),
        inbound_event_id=inbound_event_id,
        outcome=action.outcome,
        project_key=command.project_key,
        source=command.source,
        thread_id=state.thread_id,
        thread_version=state.version,
        ticket_id=action.ticket_id,
        ticket_version=action.ticket_version,
        request_id=action.request_id,
        request_number=action.request_number,
        quarantine_reason=(
            "structural-taint:quarantine_required"
            if action.outcome is IntakeOutcome.QUARANTINED
            else None
        ),
    )


def _submit_ids(command: IntakeSubmitCommand, now: datetime) -> _SubmitIds:
    ticket_ids = (
        _new_ticket_ids(command.intent, now)
        if command.taint is not IntakeTaint.QUARANTINE_REQUIRED
        else None
    )
    ticket_subject = ticket_ids.ticket if ticket_ids is not None else command.target_ticket_id
    return _SubmitIds(
        thread=command.thread_id or _uuid7(now),
        inbound_event=_uuid7(now),
        ticket=ticket_ids,
        ticket_subject=ticket_subject,
        request=(
            _uuid7(now)
            if command.intent is IntakeIntent.CREATE_REQUEST
            and command.taint is not IntakeTaint.QUARANTINE_REQUIRED
            else None
        ),
        request_event=(
            _uuid7(now)
            if command.intent is IntakeIntent.CREATE_REQUEST
            and command.taint is not IntakeTaint.QUARANTINE_REQUIRED
            else None
        ),
    )


def _new_ticket_ids(intent: IntakeIntent, now: datetime) -> TicketCreationIds | None:
    return new_ticket_creation_ids(now) if intent is IntakeIntent.CREATE_TICKET else None


def _new_request_ids(intent: IntakeIntent, now: datetime) -> tuple[UUID, UUID] | None:
    return (_uuid7(now), _uuid7(now)) if intent is IntakeIntent.CREATE_REQUEST else None
