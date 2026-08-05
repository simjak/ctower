"""INV-66: the Board card context set, derived at read time from real facts.

Every member is read live from its own authoritative table rather than folded
into ``board_projection_rows`` — there is no separate materialization lag to
reason about, and no product code branches on a label or attention-kind key.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.projections._project_delivery_sources_sql import (
    active_checkpoint_event_ids as _active_checkpoint_event_ids,
)
from ctower_kernel.projections.interface import (
    AppliedLabel,
    BoardDeliverySurfaceAvailability,
    BoardDeliverySurfaceState,
    ChangeReference,
    HumanWaiting,
    HumanWaitingState,
    TenantDisplayIdentity,
    TenantDisplayState,
)
from ctower_kernel.projections.project_delivery import delivery_surface_from_columns

__all__: tuple[str, ...] = ()


def tenant_display_identity(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID
) -> TenantDisplayIdentity:
    row = connection.execute(
        "SELECT name FROM tenants WHERE tenant_id = %s", (tenant_id,)
    ).fetchone()
    if row is None:
        return TenantDisplayIdentity(TenantDisplayState.UNKNOWN, missing_source="tenants")
    return TenantDisplayIdentity(TenantDisplayState.KNOWN, display_name=str(row["name"]))


def change_references_by_ticket(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_ids: tuple[UUID, ...],
) -> dict[UUID, tuple[ChangeReference, ...]]:
    if not ticket_ids:
        return {}
    rows = connection.execute(
        """
        SELECT ticket_id, repository, change_identity, reference, recorded_at
        FROM ticket_change_references
        WHERE tenant_id = %s AND ticket_id = ANY(%s)
        ORDER BY ticket_id, recorded_at
        """,
        (tenant_id, list(ticket_ids)),
    ).fetchall()
    result: dict[UUID, list[ChangeReference]] = {}
    for row in rows:
        result.setdefault(cast(UUID, row["ticket_id"]), []).append(
            ChangeReference(
                repository=str(row["repository"]),
                change_identity=str(row["change_identity"]),
                reference=str(row["reference"]),
                recorded_at=cast(datetime, row["recorded_at"]),
            )
        )
    return {ticket_id: tuple(items) for ticket_id, items in result.items()}


def applied_labels_by_ticket(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_ids: tuple[UUID, ...],
) -> dict[UUID, tuple[AppliedLabel, ...]]:
    if not ticket_ids:
        return {}
    rows = connection.execute(
        """
        SELECT applied.ticket_id, applied.label_key, member.label,
            revision.catalog_revision, applied.recorded_at AS applied_at
        FROM ticket_applied_labels AS applied
        JOIN label_vocabulary_members AS member
          ON member.label_vocabulary_revision_id = applied.label_vocabulary_revision_id
         AND member.tenant_id = applied.tenant_id
         AND member.label_key = applied.label_key
        JOIN label_vocabulary_revisions AS revision
          ON revision.label_vocabulary_revision_id = applied.label_vocabulary_revision_id
         AND revision.tenant_id = applied.tenant_id
        WHERE applied.tenant_id = %s AND applied.ticket_id = ANY(%s)
        ORDER BY applied.ticket_id, applied.recorded_at
        """,
        (tenant_id, list(ticket_ids)),
    ).fetchall()
    result: dict[UUID, list[AppliedLabel]] = {}
    for row in rows:
        result.setdefault(cast(UUID, row["ticket_id"]), []).append(
            AppliedLabel(
                label_key=str(row["label_key"]),
                label=str(row["label"]),
                vocabulary_revision=int(cast(int, row["catalog_revision"])),
                applied_at=cast(datetime, row["applied_at"]),
            )
        )
    return {ticket_id: tuple(items) for ticket_id, items in result.items()}


def human_waiting_by_ticket(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_ids: tuple[UUID, ...],
) -> dict[UUID, HumanWaiting]:
    if not ticket_ids:
        return {}
    rows = connection.execute(
        """
        SELECT DISTINCT ON (finding.subject_ticket_id)
            finding.subject_ticket_id, finding.finding_id, finding.kind_key,
            finding.reason_code
        FROM attention_need_findings AS finding
        LEFT JOIN attention_need_dispositions AS disposition
          ON disposition.finding_id = finding.finding_id
         AND disposition.tenant_id = finding.tenant_id
        WHERE finding.tenant_id = %s AND finding.subject_ticket_id = ANY(%s)
          AND finding.effective_owner = 'operator' AND disposition.disposition_id IS NULL
        ORDER BY finding.subject_ticket_id, finding.appended_at DESC
        """,
        (tenant_id, list(ticket_ids)),
    ).fetchall()
    return {
        cast(UUID, row["subject_ticket_id"]): HumanWaiting(
            HumanWaitingState.WAITING,
            finding_id=cast(UUID, row["finding_id"]),
            kind_key=str(row["kind_key"]),
            reason_code=str(row["reason_code"]),
        )
        for row in rows
    }


def delivery_surface_by_ticket(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_ids: tuple[UUID, ...],
) -> dict[UUID, BoardDeliverySurfaceAvailability]:
    if not ticket_ids:
        return {}
    active_ids = _active_checkpoint_event_ids(connection, tenant_id)
    if not active_ids:
        return {}
    rows = connection.execute(
        """
        SELECT criterion.proof_ticket_id AS ticket_id, definition.checkpoint_key,
            definition.landing_boundary, definition.non_production_environments,
            definition.externally_effective_outcome
        FROM project_delivery_exit_criteria AS criterion
        JOIN project_delivery_checkpoint_definitions AS definition
          ON definition.checkpoint_definition_id = criterion.checkpoint_definition_id
         AND definition.tenant_id = criterion.tenant_id
        WHERE criterion.tenant_id = %s AND criterion.proof_ticket_id = ANY(%s)
          AND definition.event_id = ANY(%s)
        ORDER BY criterion.proof_ticket_id, definition.checkpoint_key
        """,
        (tenant_id, list(ticket_ids), list(active_ids)),
    ).fetchall()
    result: dict[UUID, BoardDeliverySurfaceAvailability] = {}
    for row in rows:
        ticket_id = cast(UUID, row["ticket_id"])
        if ticket_id in result:
            continue  # a ticket qualifies for at most one reported checkpoint
        result[ticket_id] = BoardDeliverySurfaceAvailability(
            BoardDeliverySurfaceState.QUALIFYING_CHECKPOINT,
            checkpoint_key=str(row["checkpoint_key"]),
            declaration=delivery_surface_from_columns(
                row["landing_boundary"],
                row["non_production_environments"],
                row["externally_effective_outcome"],
            ),
        )
    return result
