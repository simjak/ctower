"""Immutable bundle manifest insertion and final active-pointer CAS."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg

from ctower_kernel.catalog._postgres_read import ActiveCatalog
from ctower_kernel.catalog._postgres_revisions import RevisionState, digest_bytes
from ctower_kernel.catalog.interface import (
    BundleCheck,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
)
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def insert_activation_facts(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyBundleApply,
    bundle: CompanyBundle,
    states: tuple[RevisionState, ...],
    active: ActiveCatalog | None,
    checks: tuple[BundleCheck, ...],
    *,
    result: CompanyBundleCommandResult,
    now: datetime,
) -> None:
    _insert_lifecycle(connection, actor, states, now=now)
    bundle_revision_id = _insert_bundle_revision(
        connection,
        actor,
        command,
        bundle,
        active,
        result=result,
        now=now,
    )
    _insert_bundle_children(
        connection,
        actor.tenant_id,
        bundle_revision_id,
        bundle,
        states,
        checks,
    )
    _move_active_pointer(
        connection,
        actor,
        command,
        bundle_revision_id,
        active,
        result=result,
        now=now,
    )


def _insert_lifecycle(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    states: tuple[RevisionState, ...],
    *,
    now: datetime,
) -> None:
    for state in states:
        if not state.is_new:
            continue
        publication_event_id = cast(UUID, state.publication_event_id)
        connection.execute(
            """
            INSERT INTO catalog_component_lifecycle_facts (
                lifecycle_fact_id, component_revision_id, tenant_id, action,
                event_id, actor_principal_id, recorded_at
            ) VALUES (%s, %s, %s, 'published', %s, %s, %s)
            """,
            (
                uuid4(),
                state.revision_id,
                actor.tenant_id,
                publication_event_id,
                actor.principal_id,
                now,
            ),
        )
        if state.superseded_revision_id is not None:
            connection.execute(
                """
                INSERT INTO catalog_component_supersessions (
                    replacement_revision_id, superseded_revision_id, tenant_id,
                    event_id, actor_principal_id, recorded_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    state.revision_id,
                    state.superseded_revision_id,
                    actor.tenant_id,
                    publication_event_id,
                    actor.principal_id,
                    now,
                ),
            )


def _insert_bundle_revision(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyBundleApply,
    bundle: CompanyBundle,
    active: ActiveCatalog | None,
    *,
    result: CompanyBundleCommandResult,
    now: datetime,
) -> UUID:
    bundle_revision_id = uuid4()
    connection.execute(
        """
        INSERT INTO company_bundle_revisions (
            bundle_revision_id, tenant_id, active_version, bundle_digest, plan_digest,
            company_key, company_display_name, previous_bundle_revision_id,
            activation_event_id, actor_principal_id, client_command_id, activated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            bundle_revision_id,
            actor.tenant_id,
            result.active_version,
            digest_bytes(result.bundle_digest),
            digest_bytes(result.plan_digest),
            bundle.company.key,
            bundle.company.display_name,
            active.bundle_revision_id if active is not None else None,
            result.event_ids[-1],
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )
    return bundle_revision_id


def _insert_bundle_children(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    bundle_revision_id: UUID,
    bundle: CompanyBundle,
    states: tuple[RevisionState, ...],
    checks: tuple[BundleCheck, ...],
) -> None:
    by_reference = {state.resource.component.reference(): state for state in states}
    for ordinal, resource in enumerate(bundle.resources, start=1):
        state = by_reference[resource.component.reference()]
        connection.execute(
            """
            INSERT INTO company_bundle_members (
                bundle_revision_id, tenant_id, ordinal,
                component_revision_id, publication_event_id
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                bundle_revision_id,
                tenant_id,
                ordinal,
                state.revision_id,
                state.publication_event_id,
            ),
        )
    for assignment in bundle.assignments:
        connection.execute(
            """
            INSERT INTO company_bundle_assignments (
                bundle_revision_id, tenant_id, subject, slot, component_revision_id
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                bundle_revision_id,
                tenant_id,
                assignment.subject,
                assignment.slot,
                by_reference[assignment.component].revision_id,
            ),
        )
    for secret in bundle.secret_binding_refs:
        connection.execute(
            """
            INSERT INTO company_bundle_secret_refs (
                bundle_revision_id, tenant_id, binding_name, reference_class
            ) VALUES (%s, %s, %s, %s)
            """,
            (
                bundle_revision_id,
                tenant_id,
                secret.name,
                secret.reference_class,
            ),
        )
    for check in checks:
        connection.execute(
            """
            INSERT INTO company_bundle_checks (
                bundle_revision_id, tenant_id, check_code, status
            ) VALUES (%s, %s, %s, %s)
            """,
            (bundle_revision_id, tenant_id, check.code, check.status.value),
        )


def _move_active_pointer(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyBundleApply,
    bundle_revision_id: UUID,
    active: ActiveCatalog | None,
    *,
    result: CompanyBundleCommandResult,
    now: datetime,
) -> None:
    values = (
        bundle_revision_id,
        result.active_version,
        digest_bytes(result.bundle_digest),
        actor.principal_id,
        command.client_command_id,
        now,
    )
    if active is None:
        connection.execute(
            """
            INSERT INTO company_bundle_active (
                tenant_id, bundle_revision_id, active_version, bundle_digest,
                principal_id, client_command_id, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (actor.tenant_id, *values),
        )
        return
    moved = connection.execute(
        """
        UPDATE company_bundle_active
        SET bundle_revision_id = %s, active_version = %s, bundle_digest = %s,
            principal_id = %s, client_command_id = %s, updated_at = %s
        WHERE tenant_id = %s AND active_version = %s
        """,
        (*values, actor.tenant_id, active.active.version),
    )
    if moved.rowcount != 1:
        raise RuntimeError("locked CompanyBundle pointer CAS did not move exactly once")
