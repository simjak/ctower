"""Executing-substrate consumption of Workflow review intents."""

from __future__ import annotations

from datetime import datetime

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.work import (
    AssignmentKind,
    ChangeAssignment,
    ConsumeReviewDispatch,
)
from ctower_kernel.work._assignments import change_assignment

__all__: tuple[str, ...] = ()


def consume_review_dispatch(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ConsumeReviewDispatch,
    *,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    effect = connection.execute(
        """
        SELECT author_principal_id, reviewer_family_rule
        FROM workflow_review_dispatch_effects
        WHERE effect_id = %s AND tenant_id = %s AND ticket_id = %s
        """,
        (command.effect_id, actor.tenant_id, command.ticket_id),
    ).fetchone()
    if effect is None:
        return _problem(command, "review-dispatch-unavailable", "Review dispatch unavailable", 404)
    consumed = connection.execute(
        """
        SELECT 1 FROM workflow_review_dispatch_consumptions
        WHERE effect_id = %s AND tenant_id = %s
        """,
        (command.effect_id, actor.tenant_id),
    ).fetchone()
    if consumed is not None:
        return _problem(
            command, "review-dispatch-already-consumed", "Review dispatch already consumed"
        )
    if command.reviewer_principal_id == effect["author_principal_id"]:
        return _problem(command, "review-dispatch-self-review", "Review author cannot review")
    if (
        effect["reviewer_family_rule"] == "different_from_author"
        and command.author_family == command.reviewer_family
    ):
        return _problem(
            command,
            "review-dispatch-family-conflict",
            "Reviewer model family must differ from author family",
        )
    assignment = ChangeAssignment(
        command.client_command_id,
        command.ticket_id,
        command.expected_version,
        command.reason,
        AssignmentKind.REVIEWER_ASSIGNMENT,
        command.reviewer_principal_id,
        f"review-dispatch:{command.effect_id}",
    )
    changed = change_assignment(connection, actor, assignment, now=now)
    if isinstance(changed, RecordProblem):
        return changed
    connection.execute(
        """
        INSERT INTO workflow_review_dispatch_consumptions (
            effect_id, tenant_id, reviewer_principal_id, author_family,
            reviewer_family, crew_name, consumed_by, consumed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            command.effect_id,
            actor.tenant_id,
            command.reviewer_principal_id,
            command.author_family,
            command.reviewer_family,
            command.crew_name,
            actor.principal_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO workflow_review_dispatch_verdict_links (
            effect_id, verdict_id, tenant_id, linked_at
        )
        SELECT effect.effect_id, verdict.verdict_id, effect.tenant_id, %s
        FROM workflow_review_dispatch_effects AS effect
        JOIN workflow_review_dispatch_lenses AS lens
          ON lens.effect_id = effect.effect_id AND lens.tenant_id = effect.tenant_id
        JOIN proof_bundles AS bundle
          ON bundle.ticket_id = effect.ticket_id AND bundle.tenant_id = effect.tenant_id
        JOIN proof_verdicts AS verdict
          ON verdict.proof_id = bundle.proof_id AND verdict.tenant_id = bundle.tenant_id
         AND verdict.criterion_key = lens.lens_key
         AND verdict.candidate_digest = effect.candidate_digest
        WHERE effect.effect_id = %s AND effect.tenant_id = %s
          AND verdict.reviewer_id = %s
        ON CONFLICT (verdict_id) DO NOTHING
        """,
        (now, command.effect_id, actor.tenant_id, command.reviewer_principal_id),
    )
    return changed


def _problem(
    command: ConsumeReviewDispatch,
    code: str,
    title: str,
    status: int = 409,
) -> RecordProblem:
    return RecordProblem(code, title, status, title, command.client_command_id)
