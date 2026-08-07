"""Record-owned SQL for explicit native-inbox promotion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.inbox._events import _promotion_event
from ctower_kernel.inbox.models import (
    InboxPromotionCommand,
    InboxPromotionOutcome,
    InboxPromotionResult,
)
from ctower_kernel.record import Actor, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.events import event_digest
from ctower_kernel.record.ticket_creation import (
    TicketCreationIds,
    initial_custody_project,
    insert_ticket_state,
    new_ticket_creation_ids,
    ticket_created_commit,
)
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    project_mutation_refusal,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_MAX_TITLE_LENGTH = 200


@dataclass(frozen=True, slots=True)
class _PromotionPlan:
    outcome: InboxPromotionOutcome
    project_key: str | None
    ticket_command: TicketCommand | None
    ticket_ids: TicketCreationIds | None
    ticket_id: UUID
    thread: dict[str, object]


def promote_thread(
    dsn: str,
    actor: Actor,
    command: InboxPromotionCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> InboxPromotionResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _result_from_payload(replay)
        project = _creation_project(connection, actor, command)
        if isinstance(project, RecordProblem):
            return _refuse(transaction, actor, command, request_digest, project, now)
        prepared = _prepare_promotion(
            connection,
            actor,
            command,
            project,
            now=now,
        )
        if isinstance(prepared, RecordProblem):
            return _refuse(transaction, actor, command, request_digest, prepared, now)
        durable = transaction.require_durable_subjects(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (("inbox_thread", command.thread_id), ("ticket", prepared.ticket_id)),
            now=now,
        )
        if durable is not None:
            return durable
        return _commit_promotion(
            connection,
            transaction,
            actor,
            command,
            prepared,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _creation_project(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxPromotionCommand,
) -> str | RecordProblem | None:
    if command.ticket_id is not None:
        return None
    return initial_custody_project(
        connection,
        actor,
        command.client_command_id,
        actor.principal_id,
    )


def _prepare_promotion(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxPromotionCommand,
    project_key: str | None,
    *,
    now: datetime,
) -> _PromotionPlan | RecordProblem:
    thread = _lock_thread(connection, actor.tenant_id, command.thread_id)
    problem = _thread_problem(connection, actor, command, thread)
    if problem is not None:
        return problem
    locked = cast(dict[str, object], thread)
    if command.ticket_id is not None:
        return _prepare_link(
            connection,
            actor,
            command,
            locked,
        )
    if project_key is None:
        raise RuntimeError("create-ticket promotion has no custody project")
    return _prepare_create(
        connection,
        actor,
        command,
        locked,
        project_key,
        now=now,
    )


def _prepare_link(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxPromotionCommand,
    thread: dict[str, object],
) -> _PromotionPlan | RecordProblem:
    ticket_id = cast(UUID, command.ticket_id)
    problem = project_mutation_refusal(
        connection,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        command_id=command.client_command_id,
        ticket_ids=(ticket_id,),
    )
    if problem is not None:
        return problem
    if not _ticket_exists(connection, actor.tenant_id, ticket_id):
        return _unavailable(command.client_command_id)
    return _PromotionPlan(InboxPromotionOutcome.TICKET_LINKED, None, None, None, ticket_id, thread)


def _prepare_create(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxPromotionCommand,
    thread: dict[str, object],
    project_key: str,
    *,
    now: datetime,
) -> _PromotionPlan | RecordProblem:
    title = _thread_head(connection, actor.tenant_id, command.thread_id)
    if title is None or not 1 <= len(title) <= _MAX_TITLE_LENGTH:
        return _problem(
            command.client_command_id,
            "inbox-thread-head-invalid",
            422,
            "The inbox thread head cannot be used as a ticket title.",
        )
    problem = project_mutation_refusal(
        connection,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        command_id=command.client_command_id,
        project_keys=(project_key,),
    )
    if problem is not None:
        return problem
    identifiers = new_ticket_creation_ids(now)
    ticket_command = TicketCommand(
        client_command_id=command.client_command_id,
        initial_custodian_id=actor.principal_id,
        priority="P2",
        project_key=project_key,
        source=SourceReference("inbox", f"thread:{command.thread_id}"),
        title=title,
    )
    return _PromotionPlan(
        InboxPromotionOutcome.TICKET_CREATED,
        project_key,
        ticket_command,
        identifiers,
        identifiers.ticket,
        thread,
    )


def _commit_promotion(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: InboxPromotionCommand,
    plan: _PromotionPlan,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> InboxPromotionResult:
    current = int(cast(int, plan.thread["version"]))
    event, outbox_id = _promotion_event(
        actor,
        command,
        plan.ticket_id,
        current + 1,
        bytes(cast(bytes, plan.thread["last_event_hash"])),
        request_digest,
        now,
        telemetry,
    )
    commits = [EventCommit(event, outbox_id)]
    if plan.ticket_command is not None and plan.ticket_ids is not None:
        if plan.project_key is None:
            raise RuntimeError("ticket creation plan has no project")
        insert_ticket_state(
            connection,
            actor,
            plan.ticket_command,
            project_key=plan.project_key,
            identifiers=plan.ticket_ids,
            now=now,
        )
        commits.append(
            ticket_created_commit(
                actor,
                plan.ticket_command,
                plan.ticket_ids,
                project_key=plan.project_key,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )
    result = InboxPromotionResult(
        command.client_command_id,
        tuple(item.event.event_id for item in commits),
        plan.outcome,
        command.thread_id,
        event.sequence,
        plan.ticket_id,
    )
    transaction.commit_batch(
        tuple(commits),
        response_body=result.response_payload(),
        status_code=200,
        telemetry=telemetry,
        now=now,
        subjects=(("inbox_thread", command.thread_id), ("ticket", plan.ticket_id)),
    )
    _persist_link(connection, actor, command, result, event_digest(event), current, now=now)
    return result


def _persist_link(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxPromotionCommand,
    result: InboxPromotionResult,
    final_hash: bytes,
    expected_version: int,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        UPDATE inbox_threads SET version = %s, last_event_hash = %s
        WHERE tenant_id = %s AND thread_id = %s AND version = %s
        """,
        (result.thread_version, final_hash, actor.tenant_id, command.thread_id, expected_version),
    )
    connection.execute(
        """
        INSERT INTO inbox_ticket_links (
            thread_id, tenant_id, ticket_id, event_id, promoted_by, promoted_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            command.thread_id,
            actor.tenant_id,
            result.ticket_id,
            result.event_ids[0],
            actor.principal_id,
            now,
        ),
    )


def _thread_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxPromotionCommand,
    thread: dict[str, object] | None,
) -> RecordProblem | None:
    if thread is None or actor.principal_id not in {
        thread.get("participant_a_id"),
        thread.get("participant_b_id"),
    }:
        return _unavailable(command.client_command_id)
    if (
        connection.execute(
            "SELECT 1 FROM inbox_ticket_links WHERE tenant_id = %s AND thread_id = %s",
            (actor.tenant_id, command.thread_id),
        ).fetchone()
        is not None
    ):
        return _problem(
            command.client_command_id,
            "inbox-already-promoted",
            409,
            "The inbox thread is already linked to a ticket.",
        )
    return None


def _lock_thread(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, thread_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        "SELECT * FROM inbox_threads WHERE tenant_id = %s AND thread_id = %s FOR UPDATE",
        (tenant_id, thread_id),
    ).fetchone()


def _thread_head(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, thread_id: UUID
) -> str | None:
    row = connection.execute(
        """
        SELECT content FROM inbox_messages
        WHERE tenant_id = %s AND thread_id = %s
        ORDER BY position LIMIT 1
        """,
        (tenant_id, thread_id),
    ).fetchone()
    return str(row["content"]) if row is not None else None


def _ticket_exists(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, ticket_id: UUID
) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
            (tenant_id, ticket_id),
        ).fetchone()
        is not None
    )


def _result_from_payload(payload: dict[str, object]) -> InboxPromotionResult:
    return InboxPromotionResult(
        UUID(str(payload["command_id"])),
        tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        InboxPromotionOutcome(str(payload["outcome"])),
        UUID(str(payload["thread_id"])),
        int(cast(int, payload["thread_version"])),
        UUID(str(payload["ticket_id"])),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: InboxPromotionCommand,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _unavailable(command_id: UUID) -> RecordProblem:
    return _problem(
        command_id,
        "tenant-scope-denied",
        404,
        "The requested inbox thread or ticket is unavailable in the authenticated scope.",
    )


def _problem(command_id: UUID, code: str, status: int, detail: str) -> RecordProblem:
    return RecordProblem(code, detail, status, "Inbox promotion refused", command_id)
