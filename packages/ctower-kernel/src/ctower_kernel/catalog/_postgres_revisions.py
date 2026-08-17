"""Immutable universal component revision persistence for Catalog apply."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg

from ctower_kernel.catalog.interface import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleResource,
    ComponentKind,
    ComponentReference,
)
from ctower_kernel.catalog.object_interface import StagedPayload
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RevisionState:
    resource: CompanyBundleResource
    component_id: UUID
    revision_id: UUID
    receipt: StagedPayload
    is_new: bool
    publication_event_id: UUID | None
    superseded_revision_id: UUID | None


def prepare_revisions(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyBundleApply,
    bundle: CompanyBundle,
    staged: tuple[StagedPayload, ...],
) -> tuple[RevisionState, ...] | CatalogProblem:
    receipts = {item.component: item for item in staged}
    states: list[RevisionState] = []
    for resource in bundle.resources:
        state = _inspect_revision(connection, actor, command, resource, receipts)
        if isinstance(state, CatalogProblem):
            return state
        states.append(state)
    revision_ids = {state.resource.component.reference(): state.revision_id for state in states}
    resolved: list[RevisionState] = []
    for state in states:
        component = state.resource.component
        if any(reference not in revision_ids for reference in component.compatibility.requires):
            return _problem(
                command,
                "bundle-reference-invalid",
                "A dependency is not an exact member of the proposed bundle.",
            )
        superseded_id: UUID | None = None
        if component.supersedes is not None:
            superseded_id = _resolve_reference(
                connection,
                actor.tenant_id,
                component.supersedes,
            )
            if superseded_id is None:
                return _problem(
                    command,
                    "bundle-reference-invalid",
                    "A superseded component revision is unavailable.",
                )
        resolved.append(replace(state, superseded_revision_id=superseded_id))
    return tuple(resolved)


def _inspect_revision(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyBundleApply,
    resource: CompanyBundleResource,
    receipts: dict[ComponentReference, StagedPayload],
) -> RevisionState | CatalogProblem:
    component = resource.component
    reference = component.reference()
    receipt = receipts.get(reference)
    if receipt is None:
        return _problem(
            command,
            "bundle-recovery-unavailable",
            "A staged payload receipt is missing.",
            status=503,
        )
    identity = connection.execute(
        """
        SELECT component_id FROM catalog_components
        WHERE tenant_id = %s AND kind = %s AND component_key = %s
        """,
        (actor.tenant_id, component.kind.value, component.key),
    ).fetchone()
    component_id = cast(UUID, identity["component_id"]) if identity is not None else uuid4()
    existing = connection.execute(
        """
        SELECT revision.component_revision_id, revision.content_digest,
        revision.schema_ref, revision.scope_project, revision.compatibility_ctower,
        revision.project_prefix,
        revision.payload_ref, lifecycle.event_id AS publication_event_id
        FROM catalog_component_revisions AS revision
        LEFT JOIN catalog_component_lifecycle_facts AS lifecycle
          ON lifecycle.component_revision_id = revision.component_revision_id
         AND lifecycle.tenant_id = revision.tenant_id
         AND lifecycle.action = 'published'
        WHERE revision.component_id = %s AND revision.tenant_id = %s
          AND revision.revision_number = %s
        """,
        (component_id, actor.tenant_id, component.revision),
    ).fetchone()
    if existing is not None:
        return _existing_state(
            connection,
            actor,
            command,
            resource,
            component_id,
            receipt,
            existing,
        )
    return _new_state(connection, actor, command, resource, component_id, receipt, identity)


def _existing_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyBundleApply,
    resource: CompanyBundleResource,
    component_id: UUID,
    receipt: StagedPayload,
    existing: dict[str, object],
) -> RevisionState | CatalogProblem:
    if not _revision_matches(connection, actor.tenant_id, resource, existing):
        return _problem(
            command,
            "bundle-digest-mismatch",
            "An immutable component revision already exists with different facts.",
            status=409,
        )
    publication_event = existing["publication_event_id"]
    if not isinstance(publication_event, UUID):
        return _problem(
            command,
            "bundle-reference-invalid",
            "An existing component revision lacks a publication event.",
            status=409,
        )
    return RevisionState(
        resource=resource,
        component_id=component_id,
        revision_id=cast(UUID, existing["component_revision_id"]),
        receipt=receipt,
        is_new=False,
        publication_event_id=publication_event,
        superseded_revision_id=None,
    )


def _new_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyBundleApply,
    resource: CompanyBundleResource,
    component_id: UUID,
    receipt: StagedPayload,
    identity: dict[str, object] | None,
) -> RevisionState | CatalogProblem:
    component = resource.component
    maximum = connection.execute(
        """
        SELECT max(revision_number) AS maximum
        FROM catalog_component_revisions
        WHERE component_id = %s AND tenant_id = %s
        """,
        (component_id, actor.tenant_id),
    ).fetchone()
    maximum_revision = (
        int(cast(int, maximum["maximum"]))
        if maximum is not None and maximum["maximum"] is not None
        else 0
    )
    if component.revision <= maximum_revision:
        return _problem(
            command,
            "bundle-reference-invalid",
            "A component revision regresses existing immutable history.",
            status=409,
        )
    if identity is None and component.revision != 1:
        return _problem(
            command,
            "bundle-reference-invalid",
            "A new component identity must begin at revision one.",
            status=409,
        )
    return RevisionState(
        resource=resource,
        component_id=component_id,
        revision_id=uuid4(),
        receipt=receipt,
        is_new=True,
        publication_event_id=None,
        superseded_revision_id=None,
    )


def _revision_matches(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    resource: CompanyBundleResource,
    existing: dict[str, object],
) -> bool:
    component = resource.component
    if (
        digest_text(existing["content_digest"]) != component.content_digest
        or str(existing["schema_ref"]) != component.schema_ref
        or cast(str | None, existing["scope_project"]) != component.scope.project
        or str(existing["compatibility_ctower"]) != component.compatibility.ctower
        or cast(str | None, existing["project_prefix"])
        != (str(resource.payload["prefix"]) if component.kind is ComponentKind.PROJECT else None)
        or str(existing["payload_ref"]) != component.payload_ref
    ):
        return False
    revision_id = cast(UUID, existing["component_revision_id"])
    dependencies = connection.execute(
        """
        SELECT component.kind, component.component_key, revision.revision_number,
            revision.content_digest
        FROM catalog_component_dependencies AS dependency
        JOIN catalog_component_revisions AS revision
          ON revision.component_revision_id = dependency.required_revision_id
         AND revision.tenant_id = dependency.tenant_id
        JOIN catalog_components AS component
          ON component.component_id = revision.component_id
         AND component.tenant_id = revision.tenant_id
        WHERE dependency.tenant_id = %s AND dependency.component_revision_id = %s
        ORDER BY component.kind, component.component_key, revision.revision_number
        """,
        (tenant_id, revision_id),
    ).fetchall()
    if tuple(_reference(row) for row in dependencies) != component.compatibility.requires:
        return False
    provenance = connection.execute(
        """
        SELECT provenance_kind, source, source_digest
        FROM catalog_component_provenance
        WHERE tenant_id = %s AND component_revision_id = %s
        ORDER BY ordinal
        """,
        (tenant_id, revision_id),
    ).fetchall()
    stored_provenance = tuple(
        (str(row["provenance_kind"]), str(row["source"]), digest_text(row["source_digest"]))
        for row in provenance
    )
    expected_provenance = tuple(
        (item.kind, item.source, item.digest) for item in component.provenance
    )
    if stored_provenance != expected_provenance:
        return False
    superseded = connection.execute(
        """
        SELECT old_component.kind, old_component.component_key,
            old_revision.revision_number, old_revision.content_digest
        FROM catalog_component_supersessions AS supersession
        JOIN catalog_component_revisions AS old_revision
          ON old_revision.component_revision_id = supersession.superseded_revision_id
         AND old_revision.tenant_id = supersession.tenant_id
        JOIN catalog_components AS old_component
          ON old_component.component_id = old_revision.component_id
         AND old_component.tenant_id = old_revision.tenant_id
        WHERE supersession.tenant_id = %s
          AND supersession.replacement_revision_id = %s
        """,
        (tenant_id, revision_id),
    ).fetchone()
    stored_supersedes = _reference(superseded) if superseded is not None else None
    return stored_supersedes == component.supersedes


def insert_revisions(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    states: tuple[RevisionState, ...],
    *,
    now: datetime,
) -> None:
    revision_ids = {state.resource.component.reference(): state.revision_id for state in states}
    for state in states:
        if not state.is_new:
            continue
        component = state.resource.component
        connection.execute(
            """
            INSERT INTO catalog_components (
                component_id, tenant_id, kind, component_key, created_at
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, kind, component_key) DO NOTHING
            """,
            (
                state.component_id,
                actor.tenant_id,
                component.kind.value,
                component.key,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO catalog_component_revisions (
                component_revision_id, component_id, tenant_id, revision_number,
                content_digest, schema_ref, scope_project, compatibility_ctower,
                payload_ref, project_prefix, created_by, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                state.revision_id,
                state.component_id,
                actor.tenant_id,
                component.revision,
                digest_bytes(component.content_digest),
                component.schema_ref,
                component.scope.project,
                component.compatibility.ctower,
                component.payload_ref,
                (
                    str(state.resource.payload["prefix"])
                    if component.kind is ComponentKind.PROJECT
                    else None
                ),
                actor.principal_id,
                now,
            ),
        )
        _insert_receipt(connection, actor.tenant_id, state)
        for ordinal, item in enumerate(component.provenance, start=1):
            connection.execute(
                """
                INSERT INTO catalog_component_provenance (
                    component_revision_id, tenant_id, ordinal,
                    provenance_kind, source, source_digest
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    state.revision_id,
                    actor.tenant_id,
                    ordinal,
                    item.kind,
                    item.source,
                    digest_bytes(item.digest),
                ),
            )
    for state in states:
        if not state.is_new:
            continue
        for required in state.resource.component.compatibility.requires:
            connection.execute(
                """
                INSERT INTO catalog_component_dependencies (
                    component_revision_id, required_revision_id, tenant_id
                ) VALUES (%s, %s, %s)
                """,
                (state.revision_id, revision_ids[required], actor.tenant_id),
            )


def _insert_receipt(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    state: RevisionState,
) -> None:
    receipt = state.receipt.receipt
    connection.execute(
        """
        INSERT INTO catalog_payload_receipts (
            component_revision_id, tenant_id, artifact_digest, object_key,
            object_version, ciphertext_sha256, key_reference, key_version,
            wrapped_key_sha256, uploaded_at, verified_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            state.revision_id,
            tenant_id,
            digest_bytes(receipt.artifact_digest),
            receipt.object_key,
            receipt.object_version,
            digest_bytes(receipt.ciphertext_sha256),
            receipt.key_reference,
            receipt.key_version,
            digest_bytes(receipt.wrapped_key_sha256),
            receipt.uploaded_at,
            receipt.verified_at,
        ),
    )


def _resolve_reference(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    reference: ComponentReference,
) -> UUID | None:
    row = connection.execute(
        """
        SELECT revision.component_revision_id
        FROM catalog_component_revisions AS revision
        JOIN catalog_components AS component
          ON component.component_id = revision.component_id
         AND component.tenant_id = revision.tenant_id
        WHERE revision.tenant_id = %s AND component.kind = %s
          AND component.component_key = %s AND revision.revision_number = %s
          AND revision.content_digest = %s
        """,
        (
            tenant_id,
            reference.kind.value,
            reference.key,
            reference.revision,
            digest_bytes(reference.content_digest),
        ),
    ).fetchone()
    return cast(UUID, row["component_revision_id"]) if row is not None else None


def _reference(row: dict[str, object]) -> ComponentReference:
    return ComponentReference(
        kind=ComponentKind(str(row["kind"])),
        key=str(row["component_key"]),
        revision=int(cast(int, row["revision_number"])),
        content_digest=digest_text(row["content_digest"]),
    )


def _problem(
    command: CompanyBundleApply,
    code: str,
    detail: str,
    *,
    status: int = 422,
) -> CatalogProblem:
    return CatalogProblem(
        code=code,
        detail=detail,
        status=status,
        title="Bundle refused",
        command_id=command.client_command_id,
    )


def digest_text(value: object) -> str:
    return "sha256:" + bytes(cast(bytes, value)).hex()


def digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))
