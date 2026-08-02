"""Real-database source fixtures for Project Delivery proof and seat carriage."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import rfc8785
from support.catalog import FileSchemas, MemoryObjectStore, actor_for, telemetry_for
from support.tenant_fixture import TenantFixture

from ctower_kernel.catalog import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    PostgresCatalog,
)
from ctower_kernel.projections import ProjectDeliveryRow

__all__ = [
    "activate_catalog_revision",
    "link_alpha_evidence_assignment",
    "seed_stageless_alpha_proof",
    "slot_reasons",
]


def slot_reasons(row: ProjectDeliveryRow) -> tuple[str, ...]:
    """Return the published reasons that name one exact slot state."""

    return tuple(
        sorted(
            reason
            for reason in row.derivation_reasons
            if reason.startswith(("slot_filled:", "slot_unfilled:", "slot_unknown:"))
        )
    )


def activate_catalog_revision(
    tenant: TenantFixture,
    prior_bundle: CompanyBundle,
    bundle: CompanyBundle,
) -> None:
    """Activate a later revision while serving exact prior payload bytes."""

    store = MemoryObjectStore()
    for resource in prior_bundle.resources:
        store.objects[resource.component.content_digest] = rfc8785.dumps(resource.payload)
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        store,
        key_reference="vault:catalog-key",
        clock=lambda: datetime.now(UTC),
    )
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem), plan
    command_id = uuid4()
    applied = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=command_id,
            bundle=bundle,
            expected_active_version=1,
            plan_digest=plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, command_id),
    )
    assert isinstance(applied, CompanyBundleCommandResult), applied


def seed_stageless_alpha_proof(
    tenant: TenantFixture,
    linked_ticket: UUID,
    stageless_ticket: UUID,
) -> None:
    """Build the real issue-178 state: established proof and no Workflow run."""

    proof_id = uuid4()
    evidence_id = uuid4()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        source = connection.execute(
            """
            SELECT bundle.candidate_digest, criterion.description,
                criterion.candidate_dependent, criterion.requires_verdict,
                evidence.artifact_digest
            FROM proof_bundles AS bundle
            JOIN proof_criteria AS criterion
              ON criterion.proof_id = bundle.proof_id
             AND criterion.tenant_id = bundle.tenant_id
             AND criterion.criterion_key = 'alpha'
            JOIN proof_evidence AS evidence
              ON evidence.proof_id = criterion.proof_id
             AND evidence.tenant_id = criterion.tenant_id
             AND evidence.criterion_key = criterion.criterion_key
            WHERE bundle.tenant_id = %s AND bundle.ticket_id = %s
            """,
            (tenant.tenant_id, linked_ticket),
        ).fetchone()
        assert source is not None
        now = datetime.now(UTC)
        connection.execute(
            """
            INSERT INTO proof_bundles (
                proof_id, ticket_id, tenant_id, version, candidate_digest,
                candidate_author_id, frozen_at
            ) VALUES (%s, %s, %s, 1, %s, %s, %s)
            """,
            (proof_id, stageless_ticket, tenant.tenant_id, source[0], tenant.commander_id, now),
        )
        connection.execute(
            """
            INSERT INTO proof_criteria (
                proof_id, tenant_id, criterion_key, description,
                candidate_dependent, requires_verdict, frozen_by,
                client_command_id, recorded_at
            ) VALUES (%s, %s, 'alpha', %s, %s, %s, %s, %s, %s)
            """,
            (
                proof_id,
                tenant.tenant_id,
                source[1],
                source[2],
                source[3],
                tenant.commander_id,
                uuid4(),
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO proof_evidence (
                evidence_id, proof_id, tenant_id, criterion_key,
                candidate_digest, artifact_digest, producer_id,
                client_command_id, recorded_at
            ) VALUES (%s, %s, %s, 'alpha', %s, %s, %s, %s, %s)
            """,
            (
                evidence_id,
                proof_id,
                tenant.tenant_id,
                source[0],
                source[4],
                tenant.commander_id,
                uuid4(),
                now,
            ),
        )


def link_alpha_evidence_assignment(tenant: TenantFixture, linked_ticket: UUID) -> None:
    """Append an Evidence-to-assignment reference; copy no signer or seat into Evidence."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        evidence = connection.execute(
            """
            SELECT evidence.evidence_id
            FROM proof_evidence AS evidence
            JOIN proof_bundles AS bundle
              ON bundle.proof_id = evidence.proof_id
             AND bundle.tenant_id = evidence.tenant_id
            WHERE bundle.tenant_id = %s AND bundle.ticket_id = %s
              AND evidence.criterion_key = 'alpha'
            """,
            (tenant.tenant_id, linked_ticket),
        ).fetchone()
        assignment = connection.execute(
            """
            SELECT assignment_kind, interval_sequence
            FROM assignment_intervals
            WHERE tenant_id = %s AND ticket_id = %s AND released_at IS NULL
            """,
            (tenant.tenant_id, linked_ticket),
        ).fetchone()
        catalog = connection.execute(
            """
            SELECT seat_catalog_revision_id
            FROM project_delivery_seat_catalog_revisions
            WHERE tenant_id = %s AND catalog_key = 'fixture.delivery-seats'
              AND catalog_revision = 1
            """,
            (tenant.tenant_id,),
        ).fetchone()
        assert evidence is not None and assignment is not None and catalog is not None
        now = datetime.now(UTC)
        connection.execute(
            """
            INSERT INTO assignment_interval_seat_facts (
                ticket_id, tenant_id, assignment_kind, interval_sequence,
                seat_catalog_revision_id, seat_key, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, 'reviewer', %s)
            """,
            (
                linked_ticket,
                tenant.tenant_id,
                assignment[0],
                assignment[1],
                catalog[0],
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO proof_evidence_verifier_assignments (
                evidence_id, tenant_id, assignment_ticket_id, assignment_kind,
                assignment_interval_sequence, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                evidence[0],
                tenant.tenant_id,
                linked_ticket,
                assignment[0],
                assignment[1],
                now,
            ),
        )
