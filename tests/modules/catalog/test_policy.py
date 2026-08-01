from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import rfc8785

from ctower_kernel.catalog import (
    ActiveBundle,
    CatalogPolicy,
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
)
from ctower_kernel.catalog.interface import (
    BundleActionKind,
    CompanyBundleResource,
    JsonValue,
)
from modules.catalog.support import FileSchemas, minimal_bundle

__all__: tuple[str, ...] = ()
_COMMAND_ID = UUID("00000000-0000-4000-8000-000000000001")
_ACTOR_ID = UUID("00000000-0000-4000-8000-000000000002")


def test_minimal_bundle_validates_and_reordering_is_semantically_stable() -> None:
    bundle = minimal_bundle()
    policy = CatalogPolicy(FileSchemas())
    reordered = bundle.model_copy(
        update={
            "resources": tuple(reversed(bundle.resources)),
            "assignments": tuple(reversed(bundle.assignments)),
            "secret_binding_refs": tuple(reversed(bundle.secret_binding_refs)),
        }
    )

    validated = policy.validate("example-company", bundle)
    reordered_validation = policy.validate("example-company", reordered)

    assert not isinstance(validated, CatalogProblem)
    assert not isinstance(reordered_validation, CatalogProblem)
    assert validated.bundle_digest == reordered_validation.bundle_digest
    assert {check.code for check in validated.checks} == {
        "compatibility.current",
        "digest.canonical",
        "reference.exact",
        "schema.closed",
        "security.secret-free",
    }


def test_plan_is_deterministic_and_exact_export_replans_with_zero_actions() -> None:
    bundle = minimal_bundle()
    policy = CatalogPolicy(FileSchemas())
    first = policy.plan("example-company", bundle, None)
    assert not isinstance(first, CatalogProblem)
    active = ActiveBundle(
        version=1,
        bundle_digest=first.proposed_bundle_digest,
        bundle=bundle,
        command_id=_COMMAND_ID,
        actor_principal_id=_ACTOR_ID,
        activated_at=datetime(2026, 7, 24, tzinfo=UTC),
        checks=first.checks,
    )

    repeated = policy.plan("example-company", bundle, active)
    reordered = policy.plan(
        "example-company",
        bundle.model_copy(update={"resources": tuple(reversed(bundle.resources))}),
        active,
    )

    assert first.actions
    assert {action.kind for action in first.actions} >= {
        BundleActionKind.CREATE,
        BundleActionKind.ASSIGNMENT_CHANGE,
    }
    assert not isinstance(repeated, CatalogProblem)
    assert not isinstance(reordered, CatalogProblem)
    assert repeated.actions == ()
    assert repeated.plan_digest == reordered.plan_digest
    assert reordered.actions == ()


def test_changed_header_produces_an_explicit_pointer_action() -> None:
    bundle = minimal_bundle()
    policy = CatalogPolicy(FileSchemas())
    initial = policy.plan("example-company", bundle, None)
    assert not isinstance(initial, CatalogProblem)
    active = ActiveBundle(
        version=1,
        bundle_digest=initial.proposed_bundle_digest,
        bundle=bundle,
        command_id=_COMMAND_ID,
        actor_principal_id=_ACTOR_ID,
        activated_at=datetime(2026, 7, 24, tzinfo=UTC),
        checks=initial.checks,
    )
    changed = bundle.model_copy(
        update={
            "company": bundle.company.model_copy(update={"display_name": "Example Company Two"})
        }
    )

    planned = policy.plan("example-company", changed, active)

    assert not isinstance(planned, CatalogProblem)
    assert {action.kind for action in planned.actions} == {
        BundleActionKind.POINTER_CHANGE,
        BundleActionKind.REUSE_EXACT,
    }


def test_requires_are_bundle_closed_while_supersedes_resolves_from_active() -> None:
    bundle = minimal_bundle()
    policy = CatalogPolicy(FileSchemas())
    initial = policy.plan("example-company", bundle, None)
    assert not isinstance(initial, CatalogProblem)
    active = ActiveBundle(
        version=1,
        bundle_digest=initial.proposed_bundle_digest,
        bundle=bundle,
        command_id=_COMMAND_ID,
        actor_principal_id=_ACTOR_ID,
        activated_at=datetime(2026, 7, 24, tzinfo=UTC),
        checks=initial.checks,
    )
    successor = _superseding_bundle(bundle, "company.trusted-delivery")

    validated = policy.validate("example-company", successor)
    planned = policy.plan("example-company", successor, active)

    assert not isinstance(validated, CatalogProblem)
    assert not isinstance(planned, CatalogProblem)
    assert BundleActionKind.SUPERSEDE in {action.kind for action in planned.actions}
    successor_active = active.model_copy(
        update={
            "version": 2,
            "bundle_digest": planned.proposed_bundle_digest,
            "bundle": successor,
        }
    )
    repeated = policy.plan("example-company", successor, successor_active)
    assert not isinstance(repeated, CatalogProblem)
    assert repeated.actions == ()
    dependency = next(
        resource for resource in bundle.resources if resource.component.key == "protected.cli"
    ).component.compatibility.requires[0]
    incomplete = successor.model_copy(
        update={
            "resources": tuple(
                resource
                for resource in successor.resources
                if resource.component.reference() != dependency
            )
        }
    )

    refused = policy.plan("example-company", incomplete, active)

    assert isinstance(refused, CatalogProblem)
    assert refused.code == "bundle-reference-invalid"


def test_activation_replans_against_the_locked_base_and_exact_plan_digest() -> None:
    bundle = minimal_bundle()
    policy = CatalogPolicy(FileSchemas())
    planned = policy.plan("example-company", bundle, None)
    assert not isinstance(planned, CatalogProblem)
    command = CompanyBundleApply(
        client_command_id=_COMMAND_ID,
        bundle=bundle,
        expected_active_version=0,
        plan_digest=planned.plan_digest,
    )

    assert policy.prepare_activation("example-company", command, None) == planned
    wrong_base = policy.prepare_activation(
        "example-company",
        command.model_copy(update={"expected_active_version": 1}),
        None,
    )
    wrong_plan = policy.prepare_activation(
        "example-company",
        command.model_copy(update={"plan_digest": "sha256:" + "0" * 64}),
        None,
    )

    assert isinstance(wrong_base, CatalogProblem)
    assert wrong_base.code == "bundle-base-conflict"
    assert isinstance(wrong_plan, CatalogProblem)
    assert wrong_plan.code == "bundle-plan-mismatch"


def test_activation_refuses_a_planned_removal_until_lifecycle_apply_exists() -> None:
    bundle = minimal_bundle()
    policy = CatalogPolicy(FileSchemas())
    initial = policy.plan("example-company", bundle, None)
    assert not isinstance(initial, CatalogProblem)
    active = ActiveBundle(
        version=1,
        bundle_digest=initial.proposed_bundle_digest,
        bundle=bundle,
        command_id=_COMMAND_ID,
        actor_principal_id=_ACTOR_ID,
        activated_at=datetime(2026, 7, 24, tzinfo=UTC),
        checks=initial.checks,
    )
    removal = bundle.model_copy(
        update={
            "resources": tuple(
                resource
                for resource in bundle.resources
                if resource.component.key != "local.process"
            )
        }
    )
    planned = policy.plan("example-company", removal, active)
    assert not isinstance(planned, CatalogProblem)
    assert BundleActionKind.DEPRECATE in {action.kind for action in planned.actions}
    command = CompanyBundleApply(
        client_command_id=_COMMAND_ID,
        bundle=removal,
        expected_active_version=1,
        plan_digest=planned.plan_digest,
    )

    refused = policy.prepare_activation("example-company", command, active)

    assert isinstance(refused, CatalogProblem)
    assert refused.code == "bundle-compatibility-refused"


def test_digest_schema_reference_compatibility_and_tenant_fail_closed() -> None:
    bundle = minimal_bundle()
    policy = CatalogPolicy(FileSchemas())
    first = bundle.resources[0]
    cases = (
        (
            _replace_resource(
                bundle,
                first.model_copy(
                    update={
                        "component": first.component.model_copy(
                            update={"content_digest": "sha256:" + "0" * 64}
                        )
                    }
                ),
            ),
            "bundle-digest-mismatch",
        ),
        (
            _replace_resource(
                bundle,
                first.model_copy(
                    update={
                        "component": first.component.model_copy(
                            update={"schema_ref": "ctower.project/v1"}
                        )
                    }
                ),
            ),
            "bundle-reference-invalid",
        ),
        (
            _replace_resource(
                bundle,
                first.model_copy(
                    update={
                        "component": first.component.model_copy(
                            update={
                                "compatibility": first.component.compatibility.model_copy(
                                    update={"ctower": ">=1.0.0"}
                                )
                            }
                        )
                    }
                ),
            ),
            "bundle-compatibility-refused",
        ),
    )

    tenant = policy.validate("other-company", bundle)
    assert isinstance(tenant, CatalogProblem)
    assert tenant.code == "bundle-grant-refused"
    for candidate, expected in cases:
        problem = policy.validate("example-company", candidate)
        assert isinstance(problem, CatalogProblem)
        assert problem.code == expected


def test_latest_and_secret_bearing_payloads_are_refused() -> None:
    bundle = minimal_bundle()
    policy = CatalogPolicy(FileSchemas())
    workflow = next(item for item in bundle.resources if item.component.kind.value == "workflow")
    latest_payload = {**workflow.payload, "note": "latest"}
    latest = _replace_payload(bundle, workflow, latest_payload)
    secret_payload = {**workflow.payload, "secret": "forbidden"}
    secret = _replace_payload(bundle, workflow, secret_payload)

    latest_problem = policy.validate("example-company", latest)
    secret_problem = policy.validate("example-company", secret)

    assert isinstance(latest_problem, CatalogProblem)
    assert latest_problem.code == "bundle-reference-invalid"
    assert isinstance(secret_problem, CatalogProblem)
    assert secret_problem.code == "bundle-schema-invalid"


def test_revoked_components_and_ambiguous_assignment_slots_are_refused() -> None:
    bundle = minimal_bundle()
    policy = CatalogPolicy(FileSchemas())
    first = bundle.resources[0]
    revoked = _replace_resource(
        bundle,
        first.model_copy(
            update={"component": first.component.model_copy(update={"lifecycle": "revoked"})}
        ),
    )
    assignment = bundle.assignments[0]
    ambiguous = bundle.model_copy(
        update={
            "assignments": (
                assignment,
                assignment.model_copy(
                    update={"component": bundle.resources[1].component.reference()}
                ),
            )
        }
    )

    revoked_problem = policy.validate("example-company", revoked)
    ambiguous_problem = policy.validate("example-company", ambiguous)

    assert isinstance(revoked_problem, CatalogProblem)
    assert revoked_problem.code == "bundle-reference-invalid"
    assert isinstance(ambiguous_problem, CatalogProblem)
    assert ambiguous_problem.code == "bundle-reference-invalid"


def test_checkpoint_set_refuses_a_duplicate_project_key_and_an_unscoped_checkpoint() -> None:
    """D3: both branches of the checkpoint-set rule refuse, and a clean set validates."""

    policy = CatalogPolicy(FileSchemas())
    clean = _with_checkpoints(
        minimal_bundle(),
        _checkpoint_resource("first", "I1.1"),
        _checkpoint_resource("second", "I1.2"),
    )
    duplicated = _with_checkpoints(
        minimal_bundle(),
        _checkpoint_resource("first", "I1.1"),
        _checkpoint_resource("second", "I1.1"),
    )
    unscoped = _with_checkpoints(
        minimal_bundle(),
        _checkpoint_resource("first", "I1.1", project=None),
    )

    assert not isinstance(policy.validate("example-company", clean), CatalogProblem)
    duplicate_problem = policy.validate("example-company", duplicated)
    unscoped_problem = policy.validate("example-company", unscoped)

    assert isinstance(duplicate_problem, CatalogProblem)
    assert duplicate_problem.code == "bundle-reference-invalid"
    assert "may occur only once" in duplicate_problem.detail
    assert isinstance(unscoped_problem, CatalogProblem)
    assert unscoped_problem.code == "bundle-grant-refused"


def test_seat_catalog_is_generic_unique_data_and_assignments_pin_exact_revision() -> None:
    policy = CatalogPolicy(FileSchemas())
    catalog = _seat_catalog_resource((("reviewer-a", "Reviewer A"), ("reviewer-b", "Reviewer B")))
    checkpoint = _checkpoint_resource("first", "audit-ready")
    criteria = cast(list[dict[str, JsonValue]], checkpoint.payload["criteria"])
    criterion = dict(criteria[0])
    criterion["assigned_seat"] = {
        "seat_key": "reviewer-a",
        "catalog_key": catalog.component.key,
        "catalog_revision": catalog.component.revision,
        "catalog_digest": catalog.component.content_digest,
    }
    checkpoint_bundle = minimal_bundle().model_copy(
        update={"resources": (*minimal_bundle().resources, checkpoint)}
    )
    checkpoint = _replace_payload(
        checkpoint_bundle,
        checkpoint,
        {**checkpoint.payload, "criteria": [criterion]},
    ).resources[-1]
    base = minimal_bundle()
    clean = base.model_copy(update={"resources": (*base.resources, catalog, checkpoint)})

    assert not isinstance(policy.validate("example-company", clean), CatalogProblem)

    missing = dict(criterion)
    missing["assigned_seat"] = {
        **dict(cast(dict[str, JsonValue], criterion["assigned_seat"])),
        "seat_key": "not-configured",
    }
    invalid_checkpoint = _replace_payload(
        clean,
        checkpoint,
        {**checkpoint.payload, "criteria": [missing]},
    ).resources[-1]
    invalid = clean.model_copy(
        update={
            "resources": tuple(
                invalid_checkpoint if item == checkpoint else item for item in clean.resources
            )
        }
    )
    invalid_problem = policy.validate("example-company", invalid)
    assert isinstance(invalid_problem, CatalogProblem)
    assert invalid_problem.code == "bundle-reference-invalid"

    duplicate = _seat_catalog_resource(
        (("reviewer-a", "First label"), ("reviewer-a", "Second label"))
    )
    duplicated = base.model_copy(update={"resources": (*base.resources, duplicate)})
    duplicate_problem = policy.validate("example-company", duplicated)
    assert isinstance(duplicate_problem, CatalogProblem)
    assert duplicate_problem.code == "bundle-reference-invalid"


def _with_checkpoints(
    bundle: CompanyBundle,
    *checkpoints: CompanyBundleResource,
) -> CompanyBundle:
    return bundle.model_copy(update={"resources": (*bundle.resources, *checkpoints)})


def _checkpoint_resource(
    component_key: str,
    checkpoint_key: str,
    *,
    project: str | None = "ctower",
) -> CompanyBundleResource:
    payload: dict[str, JsonValue] = {
        "schema": "ctower.checkpoint/v1",
        "key": f"ctower.{component_key}",
        "checkpoint_key": checkpoint_key,
        "display_name": f"Checkpoint {checkpoint_key}",
        "outcome": f"The declared {checkpoint_key} outcome is established",
        "accountable_owner": "ctower-operator",
        "criteria": [
            {
                "key": "declared-outcome",
                "description": f"Current proof for {checkpoint_key}",
                "required": True,
                "evidence_policy_refs": [],
            }
        ],
        "dependency_refs": [],
    }
    digest = "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    return CompanyBundleResource.model_validate_json(
        json.dumps(
            {
                "component": {
                    "schema": "ctower.versioned-component/v1",
                    "kind": "checkpoint",
                    "key": f"ctower.{component_key}",
                    "scope": {"tenant": "example-company", "project": project},
                    "revision": 1,
                    "content_digest": digest,
                    "schema_ref": "ctower.checkpoint/v1",
                    "lifecycle": "published",
                    "compatibility": {"ctower": ">=0.0.0,<1.0.0", "requires": []},
                    "provenance": [
                        {
                            "kind": "reviewed-contract",
                            "source": "SPEC#project-delivery-projection",
                            "digest": digest,
                        }
                    ],
                    "payload_ref": "object:" + digest,
                },
                "payload": payload,
            }
        )
    )


def _seat_catalog_resource(
    members: tuple[tuple[str, str], ...],
) -> CompanyBundleResource:
    payload: dict[str, JsonValue] = {
        "schema": "ctower.seat-catalog/v1",
        "key": "company.delivery-seats",
        "display_name": "Configured delivery seats",
        "members": [{"key": key, "label": label} for key, label in members],
    }
    digest = "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    return CompanyBundleResource.model_validate_json(
        json.dumps(
            {
                "component": {
                    "schema": "ctower.versioned-component/v1",
                    "kind": "seat_catalog",
                    "key": "company.delivery-seats",
                    "scope": {"tenant": "example-company", "project": None},
                    "revision": 1,
                    "content_digest": digest,
                    "schema_ref": "ctower.seat-catalog/v1",
                    "lifecycle": "published",
                    "compatibility": {"ctower": ">=0.0.0,<1.0.0", "requires": []},
                    "provenance": [
                        {
                            "kind": "reviewed-contract",
                            "source": "SPEC#per-slot-seat-accountability",
                            "digest": digest,
                        }
                    ],
                    "payload_ref": "object:" + digest,
                },
                "payload": payload,
            }
        )
    )


def _replace_payload(
    bundle: CompanyBundle,
    resource: CompanyBundleResource,
    payload: dict[str, JsonValue],
) -> CompanyBundle:
    digest = "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    component = resource.component.model_copy(
        update={"content_digest": digest, "payload_ref": "object:" + digest}
    )
    return _replace_resource(
        bundle,
        resource.model_copy(update={"component": component, "payload": payload}),
    )


def _replace_resource(
    bundle: CompanyBundle,
    replacement: CompanyBundleResource,
) -> CompanyBundle:
    resources = tuple(
        replacement if item.component.key == replacement.component.key else item
        for item in bundle.resources
    )
    return bundle.model_copy(update={"resources": resources})


def _superseding_bundle(bundle: CompanyBundle, key: str) -> CompanyBundle:
    resource = next(item for item in bundle.resources if item.component.key == key)
    previous = resource.component.reference()
    payload = {**resource.payload, "display_name": "Trusted delivery revision two"}
    digest = "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    component = resource.component.model_copy(
        update={
            "content_digest": digest,
            "payload_ref": "object:" + digest,
            "revision": previous.revision + 1,
            "supersedes": previous,
        }
    )
    return _replace_resource(
        bundle,
        resource.model_copy(update={"component": component, "payload": payload}),
    )
