"""Tenant-scoped reconstruction of immutable Catalog and CompanyBundle facts."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

import psycopg

from ctower_kernel.catalog.interface import (
    ActiveBundle,
    BundleCheck,
    BundleCheckStatus,
    CompanyBundle,
    CompanyBundleAssignment,
    CompanyBundleResource,
    CompanyIdentity,
    ComponentCompatibility,
    ComponentKind,
    ComponentLifecycle,
    ComponentProvenance,
    ComponentReference,
    ComponentScope,
    JsonValue,
    SecretBindingReference,
    VersionedComponent,
)
from ctower_kernel.catalog.object_interface import CatalogObjectError
from ctower_kernel.objects import ObjectIntegrityError, ObjectStore, StoredObject, verify_digest

__all__: tuple[str, ...] = ()

type _ReferenceClass = Literal["os-credential", "vault-path", "runtime-binding"]


@dataclass(frozen=True, slots=True)
class ActiveCatalog:
    bundle_revision_id: UUID
    active: ActiveBundle


def tenant_key(connection: psycopg.Connection[dict[str, object]], tenant_id: UUID) -> str | None:
    row = connection.execute(
        "SELECT slug FROM tenants WHERE tenant_id = %s",
        (tenant_id,),
    ).fetchone()
    return str(row["slug"]) if row is not None else None


def load_active_catalog(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    tenant_slug: str,
    store: ObjectStore,
) -> ActiveCatalog | None:
    header = connection.execute(
        """
        SELECT active.bundle_revision_id, active.active_version, active.bundle_digest,
            revision.company_key, revision.company_display_name,
            revision.actor_principal_id, revision.client_command_id, revision.activated_at
        FROM company_bundle_active AS active
        JOIN company_bundle_revisions AS revision
          ON revision.bundle_revision_id = active.bundle_revision_id
         AND revision.tenant_id = active.tenant_id
        WHERE active.tenant_id = %s
        """,
        (tenant_id,),
    ).fetchone()
    if header is None:
        return None
    bundle_revision_id = cast(UUID, header["bundle_revision_id"])
    resources, references = _resources(
        connection,
        tenant_id,
        tenant_slug,
        bundle_revision_id,
        store,
    )
    assignments = _assignments(connection, tenant_id, bundle_revision_id, references)
    secrets = _secret_refs(connection, tenant_id, bundle_revision_id)
    checks = _checks(connection, tenant_id, bundle_revision_id)
    bundle = CompanyBundle(
        schema="ctower.company-bundle/v1",
        company=CompanyIdentity(
            key=str(header["company_key"]),
            display_name=str(header["company_display_name"]),
        ),
        resources=resources,
        assignments=assignments,
        secret_binding_refs=secrets,
    )
    return ActiveCatalog(
        bundle_revision_id=bundle_revision_id,
        active=ActiveBundle(
            version=int(cast(int, header["active_version"])),
            bundle_digest=_digest(header["bundle_digest"]),
            bundle=bundle,
            command_id=cast(UUID, header["client_command_id"]),
            actor_principal_id=cast(UUID, header["actor_principal_id"]),
            activated_at=cast(datetime, header["activated_at"]),
            checks=checks,
        ),
    )


def _resources(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    tenant_slug: str,
    bundle_revision_id: UUID,
    store: ObjectStore,
) -> tuple[
    tuple[CompanyBundleResource, ...],
    dict[UUID, ComponentReference],
]:
    rows = connection.execute(
        """
        SELECT member.ordinal, revision.component_revision_id, component.kind,
            component.component_key, revision.revision_number, revision.content_digest,
            revision.schema_ref, revision.scope_project, revision.compatibility_ctower,
            revision.payload_ref, receipt.object_key, receipt.object_version,
            receipt.ciphertext_sha256, receipt.key_reference, receipt.key_version,
            receipt.wrapped_key_sha256, receipt.uploaded_at, receipt.verified_at,
            old_component.kind AS superseded_kind,
            old_component.component_key AS superseded_key,
            old_revision.revision_number AS superseded_revision,
            old_revision.content_digest AS superseded_digest
        FROM company_bundle_members AS member
        JOIN catalog_component_revisions AS revision
          ON revision.component_revision_id = member.component_revision_id
         AND revision.tenant_id = member.tenant_id
        JOIN catalog_components AS component
          ON component.component_id = revision.component_id
         AND component.tenant_id = revision.tenant_id
        JOIN catalog_payload_receipts AS receipt
          ON receipt.component_revision_id = revision.component_revision_id
         AND receipt.tenant_id = revision.tenant_id
        LEFT JOIN catalog_component_supersessions AS supersession
          ON supersession.replacement_revision_id = revision.component_revision_id
         AND supersession.tenant_id = revision.tenant_id
        LEFT JOIN catalog_component_revisions AS old_revision
          ON old_revision.component_revision_id = supersession.superseded_revision_id
         AND old_revision.tenant_id = supersession.tenant_id
        LEFT JOIN catalog_components AS old_component
          ON old_component.component_id = old_revision.component_id
         AND old_component.tenant_id = old_revision.tenant_id
        WHERE member.tenant_id = %s AND member.bundle_revision_id = %s
        ORDER BY member.ordinal
        """,
        (tenant_id, bundle_revision_id),
    ).fetchall()
    revision_ids = tuple(cast(UUID, row["component_revision_id"]) for row in rows)
    dependencies = _dependencies(connection, tenant_id, revision_ids)
    provenance = _provenance(connection, tenant_id, revision_ids)
    resources: list[CompanyBundleResource] = []
    references: dict[UUID, ComponentReference] = {}
    for row in rows:
        revision_id = cast(UUID, row["component_revision_id"])
        reference = _reference(row)
        references[revision_id] = reference
        receipt = _receipt(row, reference.content_digest)
        payload = _payload(store, tenant_id, receipt)
        component = VersionedComponent(
            schema="ctower.versioned-component/v1",
            kind=reference.kind,
            key=reference.key,
            scope=ComponentScope(
                tenant=tenant_slug,
                project=cast(str | None, row["scope_project"]),
            ),
            revision=reference.revision,
            content_digest=reference.content_digest,
            schema_ref=str(row["schema_ref"]),
            lifecycle=ComponentLifecycle.PUBLISHED,
            compatibility=ComponentCompatibility(
                ctower=str(row["compatibility_ctower"]),
                requires=dependencies[revision_id],
            ),
            provenance=provenance[revision_id],
            supersedes=_superseded_reference(row),
            payload_ref=str(row["payload_ref"]),
        )
        resources.append(CompanyBundleResource(component=component, payload=payload))
    return tuple(resources), references


def _dependencies(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision_ids: tuple[UUID, ...],
) -> defaultdict[UUID, tuple[ComponentReference, ...]]:
    grouped: defaultdict[UUID, list[ComponentReference]] = defaultdict(list)
    if revision_ids:
        rows = connection.execute(
            """
            SELECT dependency.component_revision_id, component.kind,
                component.component_key, revision.revision_number, revision.content_digest
            FROM catalog_component_dependencies AS dependency
            JOIN catalog_component_revisions AS revision
              ON revision.component_revision_id = dependency.required_revision_id
             AND revision.tenant_id = dependency.tenant_id
            JOIN catalog_components AS component
              ON component.component_id = revision.component_id
             AND component.tenant_id = revision.tenant_id
            WHERE dependency.tenant_id = %s
              AND dependency.component_revision_id = ANY(%s)
            ORDER BY component.kind, component.component_key, revision.revision_number
            """,
            (tenant_id, list(revision_ids)),
        ).fetchall()
        for row in rows:
            grouped[cast(UUID, row["component_revision_id"])].append(_reference(row))
    return defaultdict(tuple, {key: tuple(value) for key, value in grouped.items()})


def _provenance(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision_ids: tuple[UUID, ...],
) -> defaultdict[UUID, tuple[ComponentProvenance, ...]]:
    grouped: defaultdict[UUID, list[ComponentProvenance]] = defaultdict(list)
    if revision_ids:
        rows = connection.execute(
            """
            SELECT component_revision_id, provenance_kind, source, source_digest
            FROM catalog_component_provenance
            WHERE tenant_id = %s AND component_revision_id = ANY(%s)
            ORDER BY component_revision_id, ordinal
            """,
            (tenant_id, list(revision_ids)),
        ).fetchall()
        for row in rows:
            grouped[cast(UUID, row["component_revision_id"])].append(
                ComponentProvenance(
                    kind=str(row["provenance_kind"]),
                    source=str(row["source"]),
                    digest=_digest(row["source_digest"]),
                )
            )
    return defaultdict(tuple, {key: tuple(value) for key, value in grouped.items()})


def _assignments(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    bundle_revision_id: UUID,
    references: dict[UUID, ComponentReference],
) -> tuple[CompanyBundleAssignment, ...]:
    rows = connection.execute(
        """
        SELECT subject, slot, component_revision_id
        FROM company_bundle_assignments
        WHERE tenant_id = %s AND bundle_revision_id = %s
        ORDER BY subject, slot
        """,
        (tenant_id, bundle_revision_id),
    ).fetchall()
    return tuple(
        CompanyBundleAssignment(
            subject=str(row["subject"]),
            slot=str(row["slot"]),
            component=references[cast(UUID, row["component_revision_id"])],
        )
        for row in rows
    )


def _secret_refs(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    bundle_revision_id: UUID,
) -> tuple[SecretBindingReference, ...]:
    rows = connection.execute(
        """
        SELECT binding_name, reference_class
        FROM company_bundle_secret_refs
        WHERE tenant_id = %s AND bundle_revision_id = %s
        ORDER BY binding_name
        """,
        (tenant_id, bundle_revision_id),
    ).fetchall()
    return tuple(
        SecretBindingReference(
            name=str(row["binding_name"]),
            reference_class=cast(_ReferenceClass, row["reference_class"]),
        )
        for row in rows
    )


def _checks(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    bundle_revision_id: UUID,
) -> tuple[BundleCheck, ...]:
    rows = connection.execute(
        """
        SELECT check_code, status FROM company_bundle_checks
        WHERE tenant_id = %s AND bundle_revision_id = %s
        ORDER BY check_code
        """,
        (tenant_id, bundle_revision_id),
    ).fetchall()
    return tuple(
        BundleCheck(
            code=str(row["check_code"]),
            status=BundleCheckStatus(str(row["status"])),
        )
        for row in rows
    )


def _reference(row: dict[str, object]) -> ComponentReference:
    return ComponentReference(
        kind=ComponentKind(str(row["kind"])),
        key=str(row["component_key"]),
        revision=int(cast(int, row["revision_number"])),
        content_digest=_digest(row["content_digest"]),
    )


def _superseded_reference(row: dict[str, object]) -> ComponentReference | None:
    if row.get("superseded_kind") is None:
        return None
    return ComponentReference(
        kind=ComponentKind(str(row["superseded_kind"])),
        key=str(row["superseded_key"]),
        revision=int(cast(int, row["superseded_revision"])),
        content_digest=_digest(row["superseded_digest"]),
    )


def _receipt(row: dict[str, object], artifact_digest: str) -> StoredObject:
    return StoredObject(
        artifact_digest=artifact_digest,
        object_key=str(row["object_key"]),
        object_version=str(row["object_version"]),
        ciphertext_sha256=_digest(row["ciphertext_sha256"]),
        key_reference=str(row["key_reference"]),
        key_version=str(row["key_version"]),
        wrapped_key_sha256=_digest(row["wrapped_key_sha256"]),
        uploaded_at=cast(datetime, row["uploaded_at"]),
        verified_at=cast(datetime, row["verified_at"]),
    )


def _payload(store: ObjectStore, tenant_id: UUID, receipt: StoredObject) -> dict[str, JsonValue]:
    try:
        content = store.read_verified(tenant_id, receipt)
        verify_digest(content, receipt.artifact_digest)
        value = json.loads(content)
    except (ObjectIntegrityError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        raise CatalogObjectError("active Catalog payload read failed closed") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CatalogObjectError("active Catalog payload is not a JSON object")
    return cast(dict[str, JsonValue], value)


def _digest(value: object) -> str:
    return "sha256:" + bytes(cast(bytes, value)).hex()
