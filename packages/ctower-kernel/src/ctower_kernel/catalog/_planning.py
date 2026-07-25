"""Deterministic read-only CompanyBundle diff and plan digest."""

from __future__ import annotations

from ctower_kernel.catalog._canonical import plan_digest
from ctower_kernel.catalog._validation import validate_bundle
from ctower_kernel.catalog.interface import (
    ActiveBundle,
    BundleAction,
    BundleActionKind,
    CatalogProblem,
    CompanyBundle,
    CompanyBundlePlan,
    CompanyBundleResource,
    ComponentReference,
    SchemaCatalog,
)

__all__: tuple[str, ...] = ()


def plan_bundle(
    tenant_key: str,
    proposed: CompanyBundle,
    active: ActiveBundle | None,
    schemas: SchemaCatalog,
) -> CompanyBundlePlan | CatalogProblem:
    existing_refs = (
        tuple(resource.component.reference() for resource in active.bundle.resources)
        if active is not None
        else ()
    )
    validation = validate_bundle(
        tenant_key,
        proposed,
        schemas,
        existing_refs=existing_refs,
    )
    if isinstance(validation, CatalogProblem):
        return validation
    proposed_digest = validation.bundle_digest
    base_version = active.version if active is not None else 0
    base_digest = active.bundle_digest if active is not None else None
    if proposed_digest == base_digest:
        actions: tuple[BundleAction, ...] = ()
    else:
        planned = _resource_actions(proposed, active)
        if isinstance(planned, CatalogProblem):
            return planned
        actions = _with_assignment_and_pointer_actions(planned, proposed, active)
    digest = plan_digest(
        actions=actions,
        base_bundle_digest=base_digest,
        base_version=base_version,
        checks=validation.checks,
        proposed_bundle_digest=proposed_digest,
        warnings=validation.warnings,
    )
    return CompanyBundlePlan(
        actions=actions,
        base_bundle_digest=base_digest,
        base_version=base_version,
        checks=validation.checks,
        plan_digest=digest,
        proposed_bundle_digest=proposed_digest,
        warnings=validation.warnings,
    )


def _resource_actions(
    proposed: CompanyBundle,
    active: ActiveBundle | None,
) -> tuple[BundleAction, ...] | CatalogProblem:
    current = _by_key(active.bundle.resources) if active is not None else {}
    desired = _by_key(proposed.resources)
    actions: list[BundleAction] = []
    for key, resource in sorted(desired.items(), key=lambda item: item[0]):
        existing = current.get(key)
        if existing is None:
            actions.append(_action(BundleActionKind.CREATE, resource.component.reference()))
            continue
        if existing.component.reference() == resource.component.reference():
            actions.append(_action(BundleActionKind.REUSE_EXACT, resource.component.reference()))
            continue
        if not _is_exact_successor(existing, resource):
            return CatalogProblem(
                code="bundle-reference-invalid",
                detail="A changed component must be a higher exact superseding revision.",
                status=409,
                title="Bundle supersession refused",
            )
        actions.append(_action(BundleActionKind.SUPERSEDE, resource.component.reference()))
    for key, resource in sorted(current.items(), key=lambda item: item[0]):
        if key not in desired:
            actions.append(_action(BundleActionKind.DEPRECATE, resource.component.reference()))
    return tuple(actions)


def _with_assignment_and_pointer_actions(
    resource_actions: tuple[BundleAction, ...],
    proposed: CompanyBundle,
    active: ActiveBundle | None,
) -> tuple[BundleAction, ...]:
    actions = list(resource_actions)
    current_assignments = set(active.bundle.assignments) if active is not None else set()
    desired_assignments = set(proposed.assignments)
    changed_assignments = current_assignments.symmetric_difference(desired_assignments)
    actions.extend(
        _action(BundleActionKind.ASSIGNMENT_CHANGE, assignment.component)
        for assignment in sorted(
            changed_assignments,
            key=lambda item: (
                item.subject,
                item.slot,
                item.component.kind.value,
                item.component.key,
            ),
        )
    )
    anchor = min(
        (resource.component.reference() for resource in proposed.resources),
        key=_reference_sort_key,
    )
    actions.append(_action(BundleActionKind.POINTER_CHANGE, anchor))
    return tuple(sorted(actions, key=_action_sort_key))


def _is_exact_successor(
    existing: CompanyBundleResource,
    proposed: CompanyBundleResource,
) -> bool:
    old = existing.component.reference()
    new = proposed.component
    return new.revision > old.revision and new.supersedes == old


def _by_key(
    resources: tuple[CompanyBundleResource, ...],
) -> dict[tuple[str, str], CompanyBundleResource]:
    return {(item.component.kind.value, item.component.key): item for item in resources}


def _action(kind: BundleActionKind, reference: ComponentReference) -> BundleAction:
    return BundleAction(kind=kind, component=reference)


def _action_sort_key(action: BundleAction) -> tuple[str, str, str, int, str]:
    reference = action.component
    return (
        action.kind.value,
        reference.kind.value,
        reference.key,
        reference.revision,
        reference.content_digest,
    )


def _reference_sort_key(reference: ComponentReference) -> tuple[str, str, int, str]:
    return (
        reference.kind.value,
        reference.key,
        reference.revision,
        reference.content_digest,
    )
