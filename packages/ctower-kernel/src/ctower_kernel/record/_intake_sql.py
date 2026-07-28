"""Record-owned atomic inbound-thread persistence and exact replay."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import (
    Actor,
    RecordProblem,
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
from ctower_kernel.record._ticket_sql import _insert_ticket_state, _TicketIds
from ctower_kernel.record.intake import (
    InboundSource,
    IntakeCommandResult,
    IntakeIntent,
    IntakeOutcome,
    IntakePromotionCommand,
    IntakeSubmitCommand,
    IntakeTaint,
)
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["promote_intake", "submit_intake"]


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
    action = _prepare_action(connection, actor, command, ticket_ids=identifiers.ticket)
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
        subjects=_subjects(identifiers.thread, identifiers.inbound_event, action.ticket_id),
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
    resolved = _resolve_inbound_for_promotion(connection, actor, command)
    if isinstance(resolved, RecordProblem):
        return _refuse(transaction, actor, command.client_command_id, request_digest, resolved, now)
    ticket_ids = _new_ticket_ids(command.intent, now)
    ticket_subject = ticket_ids.ticket if ticket_ids is not None else command.target_ticket_id
    durable = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        _subjects(resolved, command.inbound_event_id, ticket_subject),
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
        request_digest=request_digest,
        now=now,
    )


def _prepare_promotion_after_durability(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: IntakePromotionCommand,
    resolved: UUID,
    ticket_ids: _TicketIds | None,
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
    )
    _apply_action_state(
        connection,
        actor,
        command.client_command_id,
        action,
        result,
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
        subjects=_subjects(thread_id, command.inbound_event_id, action.ticket_id),
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
    )


def _new_ticket_ids(intent: IntakeIntent, now: datetime) -> _TicketIds | None:
    if intent is not IntakeIntent.CREATE_TICKET:
        return None
    return _TicketIds(*(_uuid7(now) for _ in range(3)))


def _insert_inbound_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand,
    state: _ThreadState,
    result: IntakeCommandResult,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO inbound_events (
            inbound_event_id, tenant_id, thread_id, position, source_kind, source_ref,
            content, content_digest, taint, initial_intent, initial_outcome,
            recorded_by, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.inbound_event_id,
            actor.tenant_id,
            state.thread_id,
            state.next_position,
            command.source.kind,
            command.source.ref,
            command.content,
            hashlib.sha256(command.content.encode()).digest(),
            command.taint.value,
            command.intent.value,
            result.outcome.value,
            actor.principal_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO inbound_source_aliases (
            tenant_id, source_kind, source_ref, inbound_event_id, thread_id,
            project_key, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor.tenant_id,
            command.source.kind,
            command.source.ref,
            result.inbound_event_id,
            state.thread_id,
            command.project_key,
            now,
        ),
    )
    if result.outcome is IntakeOutcome.QUARANTINED:
        connection.execute(
            """
            INSERT INTO inbound_quarantines (
                inbound_event_id, tenant_id, reason, recorded_by, recorded_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                result.inbound_event_id,
                actor.tenant_id,
                result.quarantine_reason,
                actor.principal_id,
                now,
            ),
        )


def _apply_action_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    action: _Action,
    result: IntakeCommandResult,
    *,
    promoted: bool,
    now: datetime,
) -> None:
    if action.ticket_command is not None and action.ticket_ids is not None:
        _insert_ticket_state(
            connection, actor, action.ticket_command, identifiers=action.ticket_ids, now=now
        )
        connection.execute(
            """
            INSERT INTO ticket_project_bindings (
                ticket_id, tenant_id, project_key, run_id, source_namespace,
                immutable_source_id, bound_at, inbound_event_id
            ) VALUES (%s, %s, %s, NULL, NULL, NULL, %s, %s)
            """,
            (
                action.ticket_ids.ticket,
                actor.tenant_id,
                result.project_key,
                now,
                result.inbound_event_id,
            ),
        )
    if action.ticket_id is None:
        return
    link_kind = (
        "promotion_create"
        if promoted and action.outcome is IntakeOutcome.TICKET_CREATED
        else "promotion_link"
        if promoted
        else "initial_create"
        if action.outcome is IntakeOutcome.TICKET_CREATED
        else "initial_link"
    )
    connection.execute(
        """
        INSERT INTO inbound_ticket_links (
            inbound_event_id, tenant_id, thread_id, ticket_id, link_kind,
            command_id, linked_by, linked_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.inbound_event_id,
            actor.tenant_id,
            result.thread_id,
            action.ticket_id,
            link_kind,
            command_id,
            actor.principal_id,
            now,
        ),
    )
