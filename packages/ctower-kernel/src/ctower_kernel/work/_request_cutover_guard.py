"""Fail closed around the one-way Request writer authority epoch."""

from __future__ import annotations

from uuid import UUID

import psycopg

from ctower_kernel.record import RecordProblem

__all__ = ["request_mutation_epoch_refusal"]


def request_mutation_epoch_refusal(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    command_id: UUID,
) -> RecordProblem | None:
    row = connection.execute(
        """
        SELECT fact.state, fact.recorded_by, fact.command_id,
               confirmation.acceptance_position,
               EXISTS (
                   SELECT 1 FROM request_native_capture_fences AS fence
                   WHERE fence.tenant_id = %s
               ) AS pre_epoch_fenced
        FROM (VALUES (1)) AS singleton(value)
        LEFT JOIN LATERAL (
            SELECT candidate.state, candidate.recorded_by, candidate.command_id,
                   candidate.tenant_id
            FROM request_cutover_epoch_facts AS candidate
            WHERE candidate.tenant_id = %s
            ORDER BY candidate.sequence DESC LIMIT 1
        ) AS fact ON true
        LEFT JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = fact.tenant_id
         AND confirmation.principal_id = fact.recorded_by
         AND confirmation.client_command_id = fact.command_id
        """,
        (tenant_id, tenant_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Request epoch guard did not return its singleton row")
    if row["state"] is None and not bool(row["pre_epoch_fenced"]):
        return None
    if row["state"] is None:
        return RecordProblem(
            code="migration-import-finalization-refused",
            detail="Native Request mutation is fenced until the legacy ledger cutover completes.",
            status=409,
            title="Request authority epoch required",
            command_id=command_id,
        )
    if row["state"] == "prepared":
        return RecordProblem(
            code="migration-import-finalization-refused",
            detail="Native Request mutation is fenced while the signed import epoch is prepared.",
            status=409,
            title="Request authority epoch in progress",
            command_id=command_id,
        )
    if row["state"] == "completed" and row["acceptance_position"] is None:
        return RecordProblem(
            code="durability_pending",
            detail="The completed Request authority epoch is not yet accepted off host.",
            status=409,
            title="Request authority epoch durability pending",
            command_id=command_id,
        )
    return None
