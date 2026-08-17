"""Pure strict validation for portable CompanyBundle desired state."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from ctower_kernel.catalog._canonical import bundle_digest, canonical_digest
from ctower_kernel.catalog.interface import (
    BundleCheck,
    BundleCheckStatus,
    BundleValidation,
    CatalogProblem,
    CompanyBundle,
    CompanyBundleResource,
    ComponentKind,
    ComponentLifecycle,
    ComponentReference,
    JsonValue,
    SchemaCatalog,
)

__all__: tuple[str, ...] = ()

_CURRENT_VERSION = Version("0.0.0")
_EXPECTED_SCHEMAS: dict[ComponentKind, str] = {
    ComponentKind.WORKFLOW: "ctower.workflow/v1",
    ComponentKind.EXECUTION_POLICY: "ctower.execution-policy/v1",
    ComponentKind.GATE_POLICY: "ctower.gate-policy/v1",
    ComponentKind.EVIDENCE_POLICY: "ctower.evidence-policy/v1",
    ComponentKind.GOAL: "ctower.goal/v1",
    ComponentKind.PROJECT: "ctower.project/v1",
    ComponentKind.AGENT_PROFILE: "ctower.agent-profile/v1",
    ComponentKind.PERSONA: "ctower.persona/v1",
    ComponentKind.SKILL: "ctower.skill/v1",
    ComponentKind.TOOL: "ctower.tool/v1",
    ComponentKind.CAPABILITY: "ctower.capability/v1",
    ComponentKind.ENVIRONMENT: "ctower.environment/v1",
    ComponentKind.IMAGE: "ctower.image/v1",
    ComponentKind.HARNESS: "ctower.harness/v1",
    ComponentKind.SUPERVISOR: "ctower.supervisor/v1",
    ComponentKind.TARGET: "ctower.target/v1",
    ComponentKind.WORKSPACE: "ctower.workspace/v1",
    ComponentKind.TELEMETRY: "ctower.telemetry/v1",
    ComponentKind.CADENCE_POLICY: "ctower.scheduling-policy/v1",
    ComponentKind.NOTIFICATION: "ctower.notification/v1",
    ComponentKind.INTEGRATION: "ctower.integration/v2",
    ComponentKind.SEAT_CATALOG: "ctower.seat-catalog/v1",
    ComponentKind.CHECKPOINT: "ctower.checkpoint/v1",
    ComponentKind.LABEL_VOCABULARY: "ctower.label-vocabulary/v1",
    ComponentKind.ATTENTION_KIND_CATALOG: "ctower.attention-kind-catalog/v1",
}
_ADDITIONAL_SCHEMAS: dict[ComponentKind, frozenset[str]] = {
    ComponentKind.INTEGRATION: frozenset({"ctower.integration/v3"}),
}
_FORBIDDEN_KEYS = frozenset(
    {
        "access_token",
        "credential",
        "credential_value",
        "health",
        "job",
        "lease",
        "login_session",
        "password",
        "provider_handle",
        "receipt",
        "resolved_secret",
        "runtime_handle",
        "secret",
        "secret_value",
        "session_token",
        "ticket",
        "verdict",
        "watermark",
    }
)


def validate_bundle(
    tenant_key: str,
    bundle: CompanyBundle,
    schemas: SchemaCatalog,
    *,
    existing_refs: Iterable[ComponentReference] | None = None,
) -> BundleValidation | CatalogProblem:
    """Validate without I/O or authoritative state mutation."""

    failure = _validate_identity(tenant_key, bundle)
    if failure is None:
        failure = _validate_resources(bundle, schemas)
    if failure is None:
        failure = _validate_checkpoint_set(bundle)
    if failure is None:
        failure = _validate_seat_catalog_set(bundle, existing_refs)
    if failure is None:
        failure = _validate_single_catalog_set(bundle, ComponentKind.LABEL_VOCABULARY)
    if failure is None:
        failure = _validate_single_catalog_set(bundle, ComponentKind.ATTENTION_KIND_CATALOG)
    if failure is None:
        failure = _validate_references(bundle, existing_refs)
    if failure is None:
        failure = _validate_security(bundle)
    if failure is not None:
        return failure
    return BundleValidation(
        valid=True,
        bundle_digest=bundle_digest(bundle),
        checks=(
            BundleCheck(code="schema.closed", status=BundleCheckStatus.PASSED),
            BundleCheck(code="digest.canonical", status=BundleCheckStatus.PASSED),
            BundleCheck(code="reference.exact", status=BundleCheckStatus.PASSED),
            BundleCheck(code="compatibility.current", status=BundleCheckStatus.PASSED),
            BundleCheck(code="security.secret-free", status=BundleCheckStatus.PASSED),
        ),
        warnings=(),
    )


def _validate_identity(tenant_key: str, bundle: CompanyBundle) -> CatalogProblem | None:
    if bundle.company.key != tenant_key:
        return _problem(
            "bundle-grant-refused",
            "Bundle company key does not match the authenticated tenant.",
        )
    keys: set[tuple[ComponentKind, str]] = set()
    for resource in bundle.resources:
        component = resource.component
        if component.scope.tenant != tenant_key:
            return _problem(
                "bundle-grant-refused",
                "A component scope does not match the authenticated tenant.",
            )
        key = component.kind, component.key
        if key in keys:
            return _problem(
                "bundle-reference-invalid",
                "A bundle may pin only one revision of each component key.",
            )
        keys.add(key)
    assignment_slots = tuple(
        (assignment.subject, assignment.slot) for assignment in bundle.assignments
    )
    if len(assignment_slots) != len(set(assignment_slots)):
        return _problem(
            "bundle-reference-invalid",
            "A bundle assignment subject and slot must resolve unambiguously.",
        )
    return None


def _validate_resources(bundle: CompanyBundle, schemas: SchemaCatalog) -> CatalogProblem | None:
    for resource in bundle.resources:
        problem = _validate_resource(resource, schemas)
        if problem is not None:
            return problem
    projects = tuple(
        resource
        for resource in bundle.resources
        if resource.component.kind is ComponentKind.PROJECT
    )
    project_keys = tuple(resource.component.key.split(".", 1)[0] for resource in projects)
    if len(project_keys) != len(set(project_keys)):
        return _problem(
            "bundle-reference-invalid",
            "A company bundle may name only one project component per project key.",
        )
    prefixes = tuple(str(resource.payload["prefix"]) for resource in projects)
    if len(prefixes) != len(set(prefixes)):
        return _problem(
            "bundle-reference-invalid",
            "A project display prefix may occur only once in one active company bundle.",
        )
    if any(prefix in {"CT", "R"} for prefix in prefixes):
        return _problem(
            "bundle-reference-invalid",
            "The CT and R display prefixes are reserved for other identities.",
        )
    return None


def _validate_checkpoint_set(bundle: CompanyBundle) -> CatalogProblem | None:
    checkpoints = tuple(
        resource
        for resource in bundle.resources
        if resource.component.kind is ComponentKind.CHECKPOINT
    )
    if not checkpoints:
        return None
    if any(resource.component.scope.project is None for resource in checkpoints):
        return _problem(
            "bundle-grant-refused",
            "Every checkpoint must be scoped to one project.",
        )
    identities = tuple(
        (
            resource.component.scope.project,
            str(resource.payload.get("checkpoint_key")),
        )
        for resource in checkpoints
    )
    if len(identities) != len(set(identities)):
        return _problem(
            "bundle-reference-invalid",
            "A project checkpoint key may occur only once in an active bundle.",
        )
    return _validate_checkpoint_graph(checkpoints)


def _validate_checkpoint_graph(
    checkpoints: tuple[CompanyBundleResource, ...],
) -> CatalogProblem | None:
    by_project: dict[str, dict[str, CompanyBundleResource]] = {}
    for resource in checkpoints:
        project = cast(str, resource.component.scope.project)
        reference = f"{resource.component.key}@{resource.component.revision}"
        by_project.setdefault(project, {})[reference] = resource
    for resources in by_project.values():
        remaining: dict[str, set[str]] = {}
        for reference, resource in resources.items():
            dependencies = {
                str(value) for value in cast(list[object], resource.payload["dependency_refs"])
            }
            if not dependencies <= resources.keys():
                return _problem(
                    "bundle-reference-invalid",
                    "A checkpoint dependency must resolve within its scoped project.",
                )
            remaining[reference] = dependencies
        while remaining:
            ready = {reference for reference, dependencies in remaining.items() if not dependencies}
            if not ready:
                return _problem(
                    "bundle-reference-invalid",
                    "Checkpoint dependencies must be acyclic.",
                )
            for reference in ready:
                del remaining[reference]
            for dependencies in remaining.values():
                dependencies.difference_update(ready)
    return None


def _validate_seat_catalog_set(
    bundle: CompanyBundle,
    existing_refs: Iterable[ComponentReference] | None,
) -> CatalogProblem | None:
    catalogs = tuple(
        resource
        for resource in bundle.resources
        if resource.component.kind is ComponentKind.SEAT_CATALOG
    )
    catalog_problem = _validate_seat_catalogs(catalogs)
    if catalog_problem is not None:
        return catalog_problem
    return _validate_checkpoint_seat_assignments(bundle, catalogs, existing_refs)


def _validate_seat_catalogs(
    catalogs: tuple[CompanyBundleResource, ...],
) -> CatalogProblem | None:
    if len(catalogs) > 1:
        return _problem(
            "bundle-reference-invalid",
            "An active bundle may name only one seat catalog.",
        )
    if catalogs and catalogs[0].component.scope.project is not None:
        return _problem(
            "bundle-grant-refused",
            "The tenant seat catalog must not be scoped to one project.",
        )
    for catalog in catalogs:
        members = cast(list[dict[str, object]], catalog.payload["members"])
        keys = tuple(str(member["key"]) for member in members)
        if len(keys) != len(set(keys)):
            return _problem(
                "bundle-reference-invalid",
                "A seat key may occur only once in one catalog revision.",
            )
    return None


def _validate_single_catalog_set(
    bundle: CompanyBundle, kind: ComponentKind
) -> CatalogProblem | None:
    """Label vocabulary and attention-kind catalogs are tenant-wide, like seats."""

    catalogs = tuple(resource for resource in bundle.resources if resource.component.kind is kind)
    if len(catalogs) > 1:
        return _problem(
            "bundle-reference-invalid",
            f"An active bundle may name only one {kind.value}.",
        )
    if catalogs and catalogs[0].component.scope.project is not None:
        return _problem(
            "bundle-grant-refused",
            f"The tenant {kind.value} must not be scoped to one project.",
        )
    for catalog in catalogs:
        members = cast(list[dict[str, object]], catalog.payload["members"])
        keys = tuple(str(member["key"]) for member in members)
        if len(keys) != len(set(keys)):
            return _problem(
                "bundle-reference-invalid",
                f"A {kind.value} key may occur only once in one catalog revision.",
            )
    return None


def _validate_checkpoint_seat_assignments(
    bundle: CompanyBundle,
    catalogs: tuple[CompanyBundleResource, ...],
    existing_refs: Iterable[ComponentReference] | None,
) -> CatalogProblem | None:

    existing = set(existing_refs or ())
    proposed = {resource.component.reference() for resource in catalogs}
    by_identity = {
        (resource.component.key, resource.component.revision): resource for resource in catalogs
    }
    for resource in bundle.resources:
        if resource.component.kind is not ComponentKind.CHECKPOINT:
            continue
        criteria = cast(list[dict[str, object]], resource.payload["criteria"])
        for criterion in criteria:
            assignment = criterion.get("assigned_seat")
            if not isinstance(assignment, dict):
                continue
            problem = _validate_seat_assignment(
                assignment,
                proposed=proposed,
                existing=existing,
                by_identity=by_identity,
                historical_checkpoint=resource.component.reference() in existing,
            )
            if problem is not None:
                return problem
    return None


def _validate_seat_assignment(
    assignment: dict[str, object],
    *,
    proposed: set[ComponentReference],
    existing: set[ComponentReference],
    by_identity: dict[tuple[str, int], CompanyBundleResource],
    historical_checkpoint: bool,
) -> CatalogProblem | None:
    reference = ComponentReference(
        kind=ComponentKind.SEAT_CATALOG,
        key=str(assignment["catalog_key"]),
        revision=int(cast(int, assignment["catalog_revision"])),
        content_digest=str(assignment["catalog_digest"]),
    )
    historical_pin = historical_checkpoint and reference in existing
    if reference not in proposed and not historical_pin:
        return _problem(
            "bundle-reference-invalid",
            "A new seat assignment must pin the active seat-catalog revision.",
        )
    catalog = by_identity.get((reference.key, reference.revision))
    if catalog is None:
        return None
    if catalog.component.content_digest != reference.content_digest:
        return _problem(
            "bundle-reference-invalid",
            "A seat assignment catalog digest does not match its revision.",
        )
    member_keys = {
        str(member["key"]) for member in cast(list[dict[str, object]], catalog.payload["members"])
    }
    if str(assignment["seat_key"]) not in member_keys:
        return _problem(
            "bundle-reference-invalid",
            "A seat assignment key is absent from its pinned catalog revision.",
        )
    return None


def _validate_resource(
    resource: CompanyBundleResource, schemas: SchemaCatalog
) -> CatalogProblem | None:
    if resource.component.lifecycle is not ComponentLifecycle.PUBLISHED:
        return _problem(
            "bundle-reference-invalid",
            "An active CompanyBundle may pin only published component revisions.",
        )
    contract_problem = _validate_payload_contract(resource, schemas)
    if contract_problem is not None:
        return contract_problem
    identity_problem = _validate_payload_identity(resource)
    if identity_problem is not None:
        return identity_problem
    return _validate_payload_digest_and_compatibility(resource)


def _validate_payload_contract(
    resource: CompanyBundleResource, schemas: SchemaCatalog
) -> CatalogProblem | None:
    component = resource.component
    expected_schema = _EXPECTED_SCHEMAS.get(component.kind)
    allowed_schemas = _ADDITIONAL_SCHEMAS.get(component.kind, frozenset())
    if expected_schema is None or (
        component.schema_ref != expected_schema and component.schema_ref not in allowed_schemas
    ):
        return _problem(
            "bundle-reference-invalid",
            "Component kind and schema reference do not resolve to one authored contract.",
        )
    payload_schema = schemas.schema_for(component.schema_ref)
    if payload_schema is None:
        return _problem(
            "bundle-reference-invalid",
            "Component schema reference is unavailable in the local contract catalog.",
        )
    try:
        validator = Draft202012Validator(
            cast(Mapping[str, object], payload_schema),
            format_checker=FormatChecker(),
        )
    except SchemaError:
        return _problem(
            "bundle-schema-invalid",
            "The local component contract catalog is invalid.",
            status=503,
        )
    if next(validator.iter_errors(resource.payload), None) is not None:
        return _problem(
            "bundle-schema-invalid",
            "A component payload does not satisfy its declared authored schema.",
        )
    return None


def _validate_payload_identity(
    resource: CompanyBundleResource,
) -> CatalogProblem | None:
    component = resource.component
    payload_key = resource.payload.get("key")
    if payload_key is not None and payload_key != component.key:
        return _problem(
            "bundle-reference-invalid",
            "Component envelope and payload keys differ.",
        )
    payload_schema_ref = resource.payload.get("schema")
    if payload_schema_ref != component.schema_ref:
        return _problem(
            "bundle-reference-invalid",
            "Component envelope and payload schemas differ.",
        )
    return None


def _validate_payload_digest_and_compatibility(
    resource: CompanyBundleResource,
) -> CatalogProblem | None:
    component = resource.component
    try:
        digest = canonical_digest(resource.payload)
    except ValueError:
        return _problem(
            "bundle-schema-invalid",
            "A component payload is outside the canonical JSON domain.",
        )
    if component.content_digest != digest or component.payload_ref != "object:" + digest:
        return _problem(
            "bundle-digest-mismatch",
            "Component digest or payload reference does not match canonical payload bytes.",
        )
    if not _supports_current_version(component.compatibility.ctower):
        return _problem(
            "bundle-compatibility-refused",
            "Component compatibility excludes this ctower version.",
        )
    return None


def _validate_references(
    bundle: CompanyBundle,
    existing_refs: Iterable[ComponentReference] | None,
) -> CatalogProblem | None:
    proposed_refs = {resource.component.reference() for resource in bundle.resources}
    known_refs = None if existing_refs is None else set(existing_refs)
    for resource in bundle.resources:
        if _has_invalid_dependency(resource, proposed_refs):
            return _problem(
                "bundle-reference-invalid",
                "A component dependency does not resolve to one exact digest pin.",
            )
        supersedes = resource.component.supersedes
        if supersedes is not None and not _valid_supersession(resource, supersedes, known_refs):
            return _problem(
                "bundle-reference-invalid",
                "A supersession reference is not an exact older revision of the same component.",
            )
    for assignment in bundle.assignments:
        if assignment.component not in proposed_refs:
            return _problem(
                "bundle-reference-invalid",
                "An assignment does not resolve to one exact component digest pin.",
            )
    return None


def _has_invalid_dependency(
    resource: CompanyBundleResource,
    proposed_refs: set[ComponentReference],
) -> bool:
    own_reference = resource.component.reference()
    return any(
        required not in proposed_refs or required == own_reference
        for required in resource.component.compatibility.requires
    )


def _valid_supersession(
    resource: CompanyBundleResource,
    supersedes: ComponentReference,
    known_refs: set[ComponentReference] | None,
) -> bool:
    component = resource.component
    return (
        (known_refs is None or supersedes in known_refs or component.reference() in known_refs)
        and supersedes.kind is component.kind
        and supersedes.key == component.key
        and supersedes.revision < component.revision
    )


def _validate_security(bundle: CompanyBundle) -> CatalogProblem | None:
    names = tuple(item.name for item in bundle.secret_binding_refs)
    if len(names) != len(set(names)):
        return _problem(
            "bundle-security-refused",
            "Secret binding reference names must be unique.",
        )
    if _contains_forbidden(bundle.model_dump(mode="json")):
        return _problem(
            "bundle-security-refused",
            "Bundle payload contains secret-bearing or runtime authority fields.",
        )
    if _contains_latest(bundle.model_dump(mode="json")):
        return _problem(
            "bundle-reference-invalid",
            "Mutable latest references are forbidden.",
        )
    return None


def _contains_forbidden(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(
            key.casefold() in _FORBIDDEN_KEYS or _contains_forbidden(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _contains_latest(value: JsonValue) -> bool:
    if isinstance(value, str):
        return value.casefold() == "latest" or value.casefold().endswith("@latest")
    if isinstance(value, dict):
        return any(_contains_latest(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_latest(item) for item in value)
    return False


def _supports_current_version(specifier: str) -> bool:
    try:
        return _CURRENT_VERSION in SpecifierSet(specifier)
    except (InvalidSpecifier, InvalidVersion):
        return False


def _problem(
    code: str,
    detail: str,
    *,
    status: int = 422,
) -> CatalogProblem:
    return CatalogProblem(code=code, detail=detail, status=status, title="Bundle refused")
