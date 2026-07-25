"""RFC 8785 semantic normalization for Catalog resources and plans."""

from __future__ import annotations

import hashlib

import rfc8785

from ctower_kernel.catalog.interface import (
    BundleAction,
    BundleCheck,
    CompanyBundle,
    CompanyBundleAssignment,
    CompanyBundleResource,
    ComponentCompatibility,
    ComponentProvenance,
    ComponentReference,
    JsonValue,
    VersionedComponent,
)

__all__: tuple[str, ...] = ()


def canonical_bytes(value: JsonValue) -> bytes:
    """Encode a validated JSON value using the required semantic canonical form."""

    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, UnicodeError, ValueError) as error:
        raise ValueError("value is outside the RFC 8785 JSON domain") from error


def canonical_digest(value: JsonValue) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def normalized_bundle(bundle: CompanyBundle) -> CompanyBundle:
    """Return the deterministic export form without changing payload semantics."""

    resources = tuple(
        sorted(
            (_normalized_resource(resource) for resource in bundle.resources),
            key=_resource_sort_key,
        )
    )
    assignments = tuple(sorted(bundle.assignments, key=_assignment_sort_key))
    secrets = tuple(
        sorted(
            bundle.secret_binding_refs,
            key=lambda item: (item.name, item.reference_class),
        )
    )
    return bundle.model_copy(
        update={
            "resources": resources,
            "assignments": assignments,
            "secret_binding_refs": secrets,
        }
    )


def bundle_mapping(bundle: CompanyBundle) -> dict[str, JsonValue]:
    return normalized_bundle(bundle).model_dump(mode="json")


def bundle_digest(bundle: CompanyBundle) -> str:
    return canonical_digest(bundle_mapping(bundle))


def plan_digest(
    *,
    actions: tuple[BundleAction, ...],
    base_bundle_digest: str | None,
    base_version: int,
    checks: tuple[BundleCheck, ...],
    proposed_bundle_digest: str,
    warnings: tuple[str, ...],
) -> str:
    value: dict[str, JsonValue] = {
        "actions": [action.model_dump(mode="json") for action in actions],
        "base_bundle_digest": base_bundle_digest,
        "base_version": base_version,
        "checks": [check.model_dump(mode="json") for check in checks],
        "proposed_bundle_digest": proposed_bundle_digest,
        "warnings": list(warnings),
    }
    return canonical_digest(value)


def _normalized_resource(resource: CompanyBundleResource) -> CompanyBundleResource:
    component = resource.component
    compatibility = ComponentCompatibility(
        ctower=component.compatibility.ctower,
        requires=tuple(sorted(component.compatibility.requires, key=_reference_sort_key)),
    )
    provenance = tuple(sorted(component.provenance, key=_provenance_sort_key))
    normalized = VersionedComponent(
        **component.model_dump(
            exclude={"compatibility", "provenance"},
        ),
        compatibility=compatibility,
        provenance=provenance,
    )
    return CompanyBundleResource(component=normalized, payload=resource.payload)


def _resource_sort_key(resource: CompanyBundleResource) -> tuple[str, str, int, str]:
    component = resource.component
    return (
        component.kind.value,
        component.key,
        component.revision,
        component.content_digest,
    )


def _assignment_sort_key(
    assignment: CompanyBundleAssignment,
) -> tuple[str, str, str, str, int, str]:
    component = assignment.component
    return (
        assignment.subject,
        assignment.slot,
        component.kind.value,
        component.key,
        component.revision,
        component.content_digest,
    )


def _reference_sort_key(reference: ComponentReference) -> tuple[str, str, int, str]:
    return (
        reference.kind.value,
        reference.key,
        reference.revision,
        reference.content_digest,
    )


def _provenance_sort_key(provenance: ComponentProvenance) -> tuple[str, str, str]:
    return provenance.kind, provenance.source, provenance.digest
