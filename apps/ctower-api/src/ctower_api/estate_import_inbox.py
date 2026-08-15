"""Inbox-specific preparation and application for estate imports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

import psycopg

from ctower_api.estate_import_contracts import (
    _EstateImportPlan,
    _inbox_acknowledge_command,
    _inbox_send_command,
    _InboxImportPlan,
)
from ctower_api.estate_import_support import (
    _digest_json,
    _digest_request,
    _estate_problem,
    _inbox_batch_header,
    _manifest_projection,
    _persist_source_only_message,
    _required_text,
    _seat_for_source,
    _validate_inbox_row,
)
from ctower_kernel.inbox import InboxAcknowledgementState, PostgresInbox
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext


def prepare_inbox_batch(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    artifact: Mapping[str, object],
    batch_index: int,
    rows: Sequence[Mapping[str, object]],
    command_id: UUID,
) -> tuple[_InboxImportPlan, ...] | RecordProblem:
    """Validate and map one inbox batch before any event is appended."""

    batch = _inbox_batch_header(artifact, batch_index, len(rows), command_id)
    if isinstance(batch, RecordProblem):
        return batch
    plans: list[_InboxImportPlan] = []
    source_refs: set[str] = set()
    for row in rows:
        plan = prepare_inbox_row(connection, actor, row, command_id)
        if isinstance(plan, RecordProblem):
            return plan
        source_ref = _required_text(plan.row, "source_ref")
        if source_ref in source_refs:
            return _estate_problem(
                command_id,
                "estate-import-duplicate-source",
                "A batch contains a duplicate source reference.",
            )
        source_refs.add(source_ref)
        plans.append(plan)
    if batch.get("batch_digest") != _digest_json([_manifest_projection(plan) for plan in plans]):
        return _estate_problem(
            command_id,
            "estate-import-batch-digest-mismatch",
            "Batch rows do not match the signed batch digest.",
        )
    return tuple(plans)


def prepare_inbox_row(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    row: Mapping[str, object],
    command_id: UUID,
) -> _InboxImportPlan | RecordProblem:
    """Resolve source participants and preserve unknown identities as source-only."""

    problem = _validate_inbox_row(row, command_id)
    if problem is not None:
        return problem
    source_sender = _required_text(row, "source_sender")
    source_recipient = _required_text(row, "source_recipient")
    sender = _seat_for_source(connection, actor.tenant_id, source_sender)
    recipient = _seat_for_source(connection, actor.tenant_id, source_recipient)
    source_only = (
        sender is None or recipient is None or sender.principal_id == recipient.principal_id
    )
    command = None
    if not source_only:
        if sender is None or recipient is None:
            raise RuntimeError("mapped inbox plan lost a participant")
        command = _inbox_send_command(actor, row, sender=sender, recipient=recipient)
    return _InboxImportPlan(
        row=row,
        source_sender=source_sender,
        source_recipient=source_recipient,
        sender=sender,
        recipient=recipient,
        command=command,
        source_only=source_only,
    )


def apply_inbox_plans(
    inbox: PostgresInbox,
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    plans: Sequence[_EstateImportPlan],
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> int | RecordProblem:
    """Apply mapped inbox plans through the inbox Module Interface."""

    for plan in plans:
        if not isinstance(plan, _InboxImportPlan):
            continue
        problem = apply_inbox_plan(
            inbox,
            connection,
            actor,
            plan,
            command_id=command_id,
            now=now,
            telemetry=telemetry,
        )
        if problem is not None:
            return problem
    return len(plans)


def apply_inbox_plan(
    inbox: PostgresInbox,
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    plan: _InboxImportPlan,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> RecordProblem | None:
    """Append one mapped inbox message and its acknowledgement."""

    if plan.source_only:
        return _persist_source_only_message(connection, actor, plan, command_id, now)
    if plan.command is None:
        raise RuntimeError("mapped inbox plan has no send command")
    send = inbox.send(
        actor,
        plan.command,
        request_digest=_digest_request("inbox-send", 0, [plan.row]),
        now=now,
        telemetry=telemetry,
    )
    if isinstance(send, RecordProblem):
        return send
    state = InboxAcknowledgementState("read" if plan.row["read_state"] == "read" else "delivered")
    acknowledge = inbox.acknowledge(
        actor,
        _inbox_acknowledge_command(plan.command, state),
        request_digest=_digest_request("inbox-acknowledge", 0, [plan.row]),
        now=now,
        telemetry=telemetry,
    )
    return acknowledge if isinstance(acknowledge, RecordProblem) else None
