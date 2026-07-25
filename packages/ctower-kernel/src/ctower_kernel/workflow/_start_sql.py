"""Explicit immutable Workflow/policy start pin persistence."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import RecordProblem
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.workflow import (
    ActivityClass,
    Workflow,
    WorkflowActor,
    WorkflowReceipt,
    WorkflowStart,
)
from ctower_kernel.workflow._event_sql import append_change

__all__: tuple[str, ...] = ()


def start_workflow(
    dsn: str,
    evaluator: Workflow,
    actor: WorkflowActor,
    command: WorkflowStart,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> WorkflowReceipt | RecordProblem:
    """Start only an open current episode with one exact immutable snapshot."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id, command.client_command_id, request_digest
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _receipt(existing)
        pending = transaction.require_durable_subjects(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (("ticket", command.ticket_id),),
            now=now,
        )
        if pending is not None:
            return pending
        decision = evaluator.validate_start(command, tenant_id=actor.tenant_id)
        if not decision.accepted:
            problem = _problem(command, decision.reason, "Workflow pin refused")
            transaction.refuse(
                actor.tenant_id,
                actor.principal_id,
                command.client_command_id,
                request_digest,
                problem,
                now=now,
            )
            return problem
        outcome = _commit_start(
            connection,
            actor,
            command,
            decision.initial_stage,
            decision.activity_class,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        if isinstance(outcome, RecordProblem):
            transaction.refuse(
                actor.tenant_id,
                actor.principal_id,
                command.client_command_id,
                request_digest,
                outcome,
                now=now,
            )
        return outcome


def _commit_start(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    command: WorkflowStart,
    initial_stage: str | None,
    activity: ActivityClass | None,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> WorkflowReceipt | RecordProblem:
    episode = _current_episode(connection, actor, command)
    if isinstance(episode, RecordProblem):
        return episode
    current_version = _run_version(connection, actor, command.ticket_id, episode)
    if current_version is not None:
        return _problem(
            command,
            "workflow-already-started",
            "Current episode already has a Workflow pin",
            current_version=current_version,
        )
    if activity is None or initial_stage is None:
        raise RuntimeError("accepted Workflow start lacks initial metadata")
    run_id = _uuid7(now)
    _insert_run(connection, actor, command, run_id, episode, initial_stage, activity, now)
    receipt = WorkflowReceipt(
        command.client_command_id,
        (),
        run_id,
        command.ticket_id,
        command.workflow_ref,
        initial_stage,
        activity,
        1,
    )
    committed = append_change(
        connection,
        actor,
        command.client_command_id,
        receipt,
        operation="start",
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    _insert_start_fact(connection, actor, committed, now)
    return committed


def _insert_start_fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    receipt: WorkflowReceipt,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO workflow_start_facts (
            event_id, tenant_id, workflow_run_id, ticket_id, activity_class, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            receipt.event_ids[0],
            actor.tenant_id,
            receipt.workflow_run_id,
            receipt.ticket_id,
            receipt.activity_class.value,
            now,
        ),
    )


def _current_episode(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    command: WorkflowStart,
) -> int | RecordProblem:
    ticket = connection.execute(
        "SELECT current_episode FROM tickets WHERE tenant_id = %s AND ticket_id = %s FOR UPDATE",
        (actor.tenant_id, command.ticket_id),
    ).fetchone()
    if ticket is None:
        return _problem(command, "tenant-scope-denied", "Ticket unavailable", status=404)
    return int(cast(int, ticket["current_episode"]))


def _run_version(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    ticket_id: UUID,
    episode: int,
) -> int | None:
    run = connection.execute(
        "SELECT version FROM workflow_runs "
        "WHERE tenant_id = %s AND ticket_id = %s AND episode_number = %s FOR UPDATE",
        (actor.tenant_id, ticket_id, episode),
    ).fetchone()
    return int(cast(int, run["version"])) if run is not None else None


def _insert_run(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    command: WorkflowStart,
    run_id: UUID,
    episode: int,
    initial_stage: str,
    activity: ActivityClass,
    now: datetime,
) -> None:
    key, revision = command.workflow_ref.rsplit("@", 1)
    connection.execute(
        """
        INSERT INTO workflow_runs (
            workflow_run_id, ticket_id, tenant_id, workflow_key, workflow_revision,
            initial_stage, current_stage, activity_class, version, created_at,
            episode_number, workflow_digest, execution_policy_ref,
            execution_policy_digest, gate_policy_ref, gate_policy_digest,
            evidence_policy_ref, evidence_policy_digest, started_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, 1, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            run_id,
            command.ticket_id,
            actor.tenant_id,
            key,
            int(revision),
            initial_stage,
            initial_stage,
            activity.value,
            now,
            episode,
            _digest(command.workflow_digest),
            command.execution_policy_ref,
            _digest(command.execution_policy_digest),
            command.gate_policy_ref,
            _digest(command.gate_policy_digest),
            command.evidence_policy_ref,
            _digest(command.evidence_policy_digest),
            actor.principal_id,
        ),
    )


def _receipt(payload: dict[str, object]) -> WorkflowReceipt:
    return WorkflowReceipt(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        workflow_run_id=UUID(str(payload["workflow_run_id"])),
        ticket_id=UUID(str(payload["ticket_id"])),
        workflow_ref=str(payload["workflow_ref"]),
        stage=str(payload["stage"]),
        activity_class=ActivityClass(str(payload["activity_class"])),
        version=int(cast(int, payload["version"])),
    )


def _digest(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _problem(
    command: WorkflowStart,
    code: str,
    title: str,
    *,
    status: int = 409,
    current_version: int | None = None,
) -> RecordProblem:
    return RecordProblem(code, title, status, title, command.client_command_id, current_version)


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
