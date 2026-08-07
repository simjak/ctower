"""Workflow-owned review-dispatch intent persistence and readback."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import RecordProblem
from ctower_kernel.record.transaction import project_scope_refusal
from ctower_kernel.workflow import (
    ReviewDispatchConsumption,
    ReviewDispatchEffect,
    WorkflowActor,
    WorkflowMutation,
)

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ReviewDispatchInputs:
    candidate_digest: bytes
    author_principal_id: UUID
    author_model_ref: str
    repository: str
    change_identity: str
    pr_reference: str
    lenses: tuple[str, ...]


def emit_review_dispatch(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    *,
    workflow_run_id: UUID,
    workflow_version: int,
    routing_policy_ref: str,
    now: datetime,
) -> tuple[str, ...]:
    """Append one idempotent intent from current authored ticket facts."""

    inputs = _review_dispatch_inputs(connection, actor, mutation.ticket_id)
    if isinstance(inputs, tuple):
        return inputs
    effect_id = _uuid7(now)
    inserted = connection.execute(
        """
        INSERT INTO workflow_review_dispatch_effects (
            effect_id, workflow_run_id, tenant_id, ticket_id, workflow_version,
            destination_stage, candidate_digest, author_principal_id, author_model_ref,
            repository, change_identity, pr_reference, routing_policy_ref,
            reviewer_family_rule, emitted_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  'different_from_author', %s)
        ON CONFLICT (workflow_run_id, destination_stage, candidate_digest) DO NOTHING
        RETURNING effect_id
        """,
        (
            effect_id,
            workflow_run_id,
            actor.tenant_id,
            mutation.ticket_id,
            workflow_version,
            mutation.destination_stage,
            inputs.candidate_digest,
            inputs.author_principal_id,
            inputs.author_model_ref,
            inputs.repository,
            inputs.change_identity,
            inputs.pr_reference,
            routing_policy_ref,
            now,
        ),
    ).fetchone()
    if inserted is None:
        return ()
    connection.cursor().executemany(
        """
        INSERT INTO workflow_review_dispatch_lenses (
            effect_id, tenant_id, lens_key, ordinal
        ) VALUES (%s, %s, %s, %s)
        """,
        (
            (effect_id, actor.tenant_id, lens, ordinal)
            for ordinal, lens in enumerate(inputs.lenses, start=1)
        ),
    )
    return ()


def _review_dispatch_inputs(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    ticket_id: UUID,
) -> _ReviewDispatchInputs | tuple[str, ...]:
    bundle = connection.execute(
        """
        SELECT proof_id, candidate_digest, candidate_author_id
        FROM proof_bundles
        WHERE tenant_id = %s AND ticket_id = %s
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()
    if bundle is None:
        return ("proof.candidate@1",)
    lenses = tuple(
        str(row["criterion_key"])
        for row in connection.execute(
            """
            SELECT criterion_key FROM proof_criteria
            WHERE proof_id = %s AND tenant_id = %s AND requires_verdict
            ORDER BY criterion_key
            """,
            (bundle["proof_id"], actor.tenant_id),
        ).fetchall()
    )
    missing: list[str] = []
    if not lenses:
        missing.append("proof.review-lenses@1")
    change = connection.execute(
        """
        SELECT repository, change_identity, reference
        FROM ticket_change_references
        WHERE tenant_id = %s AND ticket_id = %s
        ORDER BY recorded_at DESC, change_reference_id DESC LIMIT 1
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()
    if change is None:
        missing.append("record.change-reference@1")
    session = connection.execute(
        """
        SELECT model_ref FROM ticket_work_sessions
        WHERE tenant_id = %s AND ticket_id = %s AND started_by = %s
        ORDER BY started_at DESC, session_id DESC LIMIT 1
        """,
        (actor.tenant_id, ticket_id, bundle["candidate_author_id"]),
    ).fetchone()
    if session is None:
        missing.append("record.author-session-model@1")
    if missing:
        return tuple(missing)
    if change is None or session is None:
        raise RuntimeError("complete review dispatch inputs were not retained")
    return _ReviewDispatchInputs(
        candidate_digest=bytes(cast(bytes, bundle["candidate_digest"])),
        author_principal_id=cast(UUID, bundle["candidate_author_id"]),
        author_model_ref=str(session["model_ref"]),
        repository=str(change["repository"]),
        change_identity=str(change["change_identity"]),
        pr_reference=str(change["reference"]),
        lenses=lenses,
    )


def review_dispatches(
    dsn: str, actor: WorkflowActor, ticket_id: UUID
) -> tuple[ReviewDispatchEffect, ...] | RecordProblem:
    """Read one tenant/project-scoped ticket's complete dispatch join."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        ticket = connection.execute(
            "SELECT project_key FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
            (actor.tenant_id, ticket_id),
        ).fetchone()
        if ticket is None:
            return RecordProblem(
                "tenant-scope-denied", "Ticket unavailable", 404, "Ticket unavailable"
            )
        refusal = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(str(ticket["project_key"]),),
        )
        if refusal is not None:
            return refusal
        rows = connection.execute(
            """
            SELECT effect.*, consumption.reviewer_principal_id,
                consumption.author_family, consumption.reviewer_family,
                consumption.crew_name, consumption.consumed_by, consumption.consumed_at
            FROM workflow_review_dispatch_effects AS effect
            LEFT JOIN workflow_review_dispatch_consumptions AS consumption
              ON consumption.effect_id = effect.effect_id
             AND consumption.tenant_id = effect.tenant_id
            WHERE effect.tenant_id = %s AND effect.ticket_id = %s
            ORDER BY effect.emitted_at, effect.effect_id
            """,
            (actor.tenant_id, ticket_id),
        ).fetchall()
        return tuple(_effect(connection, row) for row in rows)


def review_dispatches_complete(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    workflow_run_id: UUID,
) -> bool:
    """Require every emitted lens to have a linked reviewer verdict."""

    row = connection.execute(
        """
        SELECT NOT EXISTS (
            SELECT 1 FROM workflow_review_dispatch_effects AS effect
            WHERE effect.tenant_id = %s AND effect.workflow_run_id = %s
              AND (
                NOT EXISTS (
                    SELECT 1 FROM workflow_review_dispatch_consumptions AS consumption
                    WHERE consumption.effect_id = effect.effect_id
                      AND consumption.tenant_id = effect.tenant_id
                )
                OR EXISTS (
                    SELECT 1 FROM workflow_review_dispatch_lenses AS lens
                    WHERE lens.effect_id = effect.effect_id
                      AND lens.tenant_id = effect.tenant_id
                      AND NOT EXISTS (
                          SELECT 1
                          FROM workflow_review_dispatch_verdict_links AS link
                          JOIN proof_verdicts AS verdict ON verdict.verdict_id = link.verdict_id
                            AND verdict.tenant_id = link.tenant_id
                          WHERE link.effect_id = effect.effect_id
                            AND link.tenant_id = effect.tenant_id
                            AND verdict.criterion_key = lens.lens_key
                      )
                )
              )
        ) AS complete
        """,
        (tenant_id, workflow_run_id),
    ).fetchone()
    return row is not None and row["complete"] is True


def _effect(
    connection: psycopg.Connection[dict[str, object]], row: dict[str, object]
) -> ReviewDispatchEffect:
    effect_id = cast(UUID, row["effect_id"])
    lenses = tuple(
        str(item["lens_key"])
        for item in connection.execute(
            """
            SELECT lens_key FROM workflow_review_dispatch_lenses
            WHERE effect_id = %s AND tenant_id = %s ORDER BY ordinal
            """,
            (effect_id, row["tenant_id"]),
        ).fetchall()
    )
    verdict_ids = tuple(
        cast(UUID, item["verdict_id"])
        for item in connection.execute(
            """
            SELECT verdict_id FROM workflow_review_dispatch_verdict_links
            WHERE effect_id = %s AND tenant_id = %s ORDER BY linked_at, verdict_id
            """,
            (effect_id, row["tenant_id"]),
        ).fetchall()
    )
    consumption = (
        None
        if row["reviewer_principal_id"] is None
        else ReviewDispatchConsumption(
            reviewer_principal_id=cast(UUID, row["reviewer_principal_id"]),
            author_family=str(row["author_family"]),
            reviewer_family=str(row["reviewer_family"]),
            crew_name=str(row["crew_name"]),
            consumed_by=cast(UUID, row["consumed_by"]),
            consumed_at=cast(datetime, row["consumed_at"]),
        )
    )
    return ReviewDispatchEffect(
        effect_id=effect_id,
        workflow_run_id=cast(UUID, row["workflow_run_id"]),
        ticket_id=cast(UUID, row["ticket_id"]),
        workflow_version=int(cast(int, row["workflow_version"])),
        destination_stage=str(row["destination_stage"]),
        candidate_digest="sha256:" + bytes(cast(bytes, row["candidate_digest"])).hex(),
        author_principal_id=cast(UUID, row["author_principal_id"]),
        author_model_ref=str(row["author_model_ref"]),
        repository=str(row["repository"]),
        change_identity=str(row["change_identity"]),
        pr_reference=str(row["pr_reference"]),
        routing_policy_ref=str(row["routing_policy_ref"]),
        reviewer_family_rule=str(row["reviewer_family_rule"]),
        lenses=lenses,
        emitted_at=cast(datetime, row["emitted_at"]),
        consumption=consumption,
        verdict_ids=verdict_ids,
    )


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
