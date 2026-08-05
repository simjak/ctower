"""Small public Interface for universal Catalog and CompanyBundle authority."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

__all__ = [
    "ActiveBundle",
    "BundleAction",
    "BundleActionKind",
    "BundleCheck",
    "BundleCheckStatus",
    "BundleValidation",
    "CatalogProblem",
    "CompanyBundle",
    "CompanyBundleApply",
    "CompanyBundleAssignment",
    "CompanyBundleCommandResult",
    "CompanyBundleExport",
    "CompanyBundlePlan",
    "CompanyBundleResource",
    "CompanyIdentity",
    "ComponentCompatibility",
    "ComponentKind",
    "ComponentProvenance",
    "ComponentReference",
    "ComponentScope",
    "JsonValue",
    "SchemaCatalog",
    "SecretBindingReference",
    "VersionedComponent",
]

type JsonValue = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
type Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
type ComponentKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9.-]{2,127}$")]
type ComponentSchema = Annotated[
    str, StringConstraints(pattern=r"^ctower\.[a-z][a-z0-9.-]*/v[1-9][0-9]*$")
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=False,
    )


class ComponentKind(StrEnum):
    WORKFLOW = "workflow"
    EXECUTION_POLICY = "execution_policy"
    GATE_POLICY = "gate_policy"
    EVIDENCE_POLICY = "evidence_policy"
    GOAL = "goal"
    PROJECT = "project"
    AGENT_PROFILE = "agent_profile"
    PERSONA = "persona"
    SKILL = "skill"
    TOOL = "tool"
    CAPABILITY = "capability"
    ENVIRONMENT = "environment"
    IMAGE = "image"
    HARNESS = "harness"
    SUPERVISOR = "supervisor"
    TARGET = "target"
    WORKSPACE = "workspace"
    TELEMETRY = "telemetry"
    PLACEMENT_POLICY = "placement_policy"
    EXTENSION = "extension"
    CADENCE_POLICY = "cadence_policy"
    NOTIFICATION = "notification"
    INTEGRATION = "integration"
    ADAPTER = "adapter"
    SEAT_CATALOG = "seat_catalog"
    CHECKPOINT = "checkpoint"
    LABEL_VOCABULARY = "label_vocabulary"
    ATTENTION_KIND_CATALOG = "attention_kind_catalog"


class ComponentLifecycle(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class ComponentReference(_StrictModel):
    kind: ComponentKind
    key: ComponentKey
    revision: Annotated[int, Field(ge=1)]
    content_digest: Digest

    def identity(self) -> tuple[ComponentKind, str, int]:
        return self.kind, self.key, self.revision


class ComponentScope(_StrictModel):
    tenant: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    project: Annotated[str, StringConstraints(min_length=1, max_length=128)] | None


class ComponentCompatibility(_StrictModel):
    ctower: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    requires: tuple[ComponentReference, ...]

    @field_validator("requires")
    @classmethod
    def _unique_requires(
        cls, requires: tuple[ComponentReference, ...]
    ) -> tuple[ComponentReference, ...]:
        if len(requires) != len(set(requires)):
            raise ValueError("component dependency references must be unique")
        return requires


class ComponentProvenance(_StrictModel):
    kind: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    source: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    digest: Digest


class VersionedComponent(_StrictModel):
    schema_: Literal["ctower.versioned-component/v1"] = Field(alias="schema")
    kind: ComponentKind
    key: ComponentKey
    scope: ComponentScope
    revision: Annotated[int, Field(ge=1)]
    content_digest: Digest
    schema_ref: ComponentSchema
    lifecycle: ComponentLifecycle
    compatibility: ComponentCompatibility
    provenance: Annotated[tuple[ComponentProvenance, ...], Field(min_length=1, max_length=64)]
    supersedes: ComponentReference | None = None
    payload_ref: Annotated[str, StringConstraints(pattern=r"^object:sha256:[0-9a-f]{64}$")]

    def reference(self) -> ComponentReference:
        return ComponentReference(
            kind=self.kind,
            key=self.key,
            revision=self.revision,
            content_digest=self.content_digest,
        )


class CompanyBundleResource(_StrictModel):
    component: VersionedComponent
    payload: dict[str, JsonValue]


class CompanyBundleAssignment(_StrictModel):
    subject: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9._-]*:[a-z][a-z0-9._-]*$"),
    ]
    slot: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9._-]{1,63}$")]
    component: ComponentReference


class SecretBindingReference(_StrictModel):
    name: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")]
    reference_class: Literal["os-credential", "vault-path", "runtime-binding"]


class CompanyIdentity(_StrictModel):
    key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{2,63}$")]
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class CompanyBundle(_StrictModel):
    schema_: Literal["ctower.company-bundle/v1"] = Field(alias="schema")
    company: CompanyIdentity
    resources: Annotated[tuple[CompanyBundleResource, ...], Field(min_length=1, max_length=512)]
    assignments: Annotated[tuple[CompanyBundleAssignment, ...], Field(max_length=512)]
    secret_binding_refs: Annotated[tuple[SecretBindingReference, ...], Field(max_length=128)]

    @field_validator("resources")
    @classmethod
    def _unique_resources(
        cls, resources: tuple[CompanyBundleResource, ...]
    ) -> tuple[CompanyBundleResource, ...]:
        identities = tuple(item.component.reference().identity() for item in resources)
        if len(identities) != len(set(identities)):
            raise ValueError("bundle resource identities must be unique")
        return resources


class BundleCheckStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"


class BundleCheck(_StrictModel):
    code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9._-]{1,95}$")]
    status: BundleCheckStatus


class BundleValidation(_StrictModel):
    valid: bool
    bundle_digest: Digest
    checks: tuple[BundleCheck, ...]
    warnings: tuple[Annotated[str, StringConstraints(max_length=500)], ...]


class BundleActionKind(StrEnum):
    CREATE = "create"
    REUSE_EXACT = "reuse_exact"
    SUPERSEDE = "supersede"
    DEPRECATE = "deprecate"
    ASSIGNMENT_CHANGE = "assignment_change"
    POINTER_CHANGE = "pointer_change"
    NO_OP = "no_op"


class BundleAction(_StrictModel):
    kind: BundleActionKind
    component: ComponentReference


class CompanyBundlePlan(_StrictModel):
    actions: tuple[BundleAction, ...]
    base_bundle_digest: Digest | None
    base_version: Annotated[int, Field(ge=0)]
    checks: tuple[BundleCheck, ...]
    plan_digest: Digest
    proposed_bundle_digest: Digest
    warnings: tuple[Annotated[str, StringConstraints(max_length=500)], ...]


class ActiveBundle(_StrictModel):
    version: Annotated[int, Field(ge=1)]
    bundle_digest: Digest
    bundle: CompanyBundle
    command_id: UUID
    actor_principal_id: UUID
    activated_at: datetime
    checks: tuple[BundleCheck, ...]


class CompanyBundleApply(_StrictModel):
    client_command_id: UUID
    bundle: CompanyBundle
    expected_active_version: Annotated[int, Field(ge=0)]
    plan_digest: Digest

    def request_payload(self) -> dict[str, JsonValue]:
        return {
            "bundle": self.bundle.model_dump(mode="json"),
            "expected_active_version": self.expected_active_version,
            "plan_digest": self.plan_digest,
        }


class CompanyBundleCommandResult(_StrictModel):
    command_id: UUID
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    active_version: Annotated[int, Field(ge=1)]
    bundle_digest: Digest
    plan_digest: Digest

    def response_payload(self) -> dict[str, JsonValue]:
        return {
            "active_version": self.active_version,
            "bundle_digest": self.bundle_digest,
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "plan_digest": self.plan_digest,
        }


class CompanyBundleExport(_StrictModel):
    active_version: Annotated[int, Field(ge=1)]
    bundle: CompanyBundle
    bundle_digest: Digest
    activated_at: datetime
    actor_principal_id: UUID
    command_id: UUID
    checks: tuple[BundleCheck, ...]


class CatalogProblem(_StrictModel):
    code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{2,95}$")]
    detail: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    status: Annotated[int, Field(ge=400, le=599)]
    title: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    command_id: UUID | None = None

    def response_payload(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "code": self.code,
            "detail": self.detail,
            "status": self.status,
            "title": self.title,
            "type": f"https://ctower.dev/problems/{self.code}",
        }
        if self.command_id is not None:
            payload["command_id"] = str(self.command_id)
        return payload


class SchemaCatalog(Protocol):
    """Generated, local-only authored schema resource lookup."""

    def schema_for(self, schema_ref: str) -> dict[str, JsonValue] | None: ...
