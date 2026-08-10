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
               confirmation.acceptance_position
        FROM request_cutover_epoch_facts AS fact
        LEFT JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = fact.tenant_id
         AND confirmation.principal_id = fact.recorded_by
         AND confirmation.client_command_id = fact.command_id
        WHERE fact.tenant_id = %s
        ORDER BY fact.sequence DESC LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()
    if row is None:
        return None
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
    if row["state"] == "quarantined":
        return RecordProblem(
            code="migration-import-finalization-refused",
            detail="Request mutation remains fenced because the import epoch is quarantined.",
            status=409,
            title="Request authority epoch quarantined",
            command_id=command_id,
        )
    return None
