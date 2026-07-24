"""Public pure Catalog policy and shared-object staging services."""

from __future__ import annotations

from uuid import UUID

from ctower_kernel.catalog._objects import stage_payloads
from ctower_kernel.catalog._planning import plan_bundle
from ctower_kernel.catalog._validation import validate_bundle
from ctower_kernel.catalog.interface import (
    ActiveBundle,
    BundleValidation,
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundlePlan,
    SchemaCatalog,
)
from ctower_kernel.catalog.object_interface import StagedPayload
from ctower_kernel.objects import ObjectStore

__all__ = ["CatalogPayloadStager", "CatalogPolicy"]


class CatalogPayloadStager:
    """Stage Catalog bytes through the one shared generic object capability."""

    def __init__(self, store: ObjectStore, *, key_reference: str) -> None:
        self._store = store
        self._key_reference = key_reference

    def stage(self, tenant_id: UUID, bundle: CompanyBundle) -> tuple[StagedPayload, ...]:
        return stage_payloads(
            tenant_id,
            bundle,
            self._store,
            key_reference=self._key_reference,
        )


class CatalogPolicy:
    """Pure validation and deterministic planning over injected local schemas."""

    def __init__(self, schemas: SchemaCatalog) -> None:
        self._schemas = schemas

    def validate(self, tenant_key: str, bundle: CompanyBundle) -> BundleValidation | CatalogProblem:
        return validate_bundle(tenant_key, bundle, self._schemas)

    def plan(
        self,
        tenant_key: str,
        bundle: CompanyBundle,
        active: ActiveBundle | None,
    ) -> CompanyBundlePlan | CatalogProblem:
        return plan_bundle(tenant_key, bundle, active, self._schemas)

    def prepare_activation(
        self,
        tenant_key: str,
        command: CompanyBundleApply,
        active: ActiveBundle | None,
    ) -> CompanyBundlePlan | CatalogProblem:
        """Replan against a locked base and require the caller's exact plan."""

        plan = self.plan(tenant_key, command.bundle, active)
        if isinstance(plan, CatalogProblem):
            return plan
        if command.expected_active_version != plan.base_version:
            return CatalogProblem(
                code="bundle-base-conflict",
                detail="The active CompanyBundle version changed before apply.",
                status=409,
                title="Bundle base conflict",
                command_id=command.client_command_id,
            )
        if command.plan_digest != plan.plan_digest:
            return CatalogProblem(
                code="bundle-plan-conflict",
                detail="The supplied plan digest does not match the locked semantic plan.",
                status=409,
                title="Bundle plan conflict",
                command_id=command.client_command_id,
            )
        return plan
