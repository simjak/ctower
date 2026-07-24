"""Single public protocol for Catalog lifecycle and CompanyBundle authority."""

from __future__ import annotations

from typing import Protocol

from ctower_kernel.catalog.interface import (
    BundleValidation,
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    CompanyBundleExport,
    CompanyBundlePlan,
    ComponentReference,
    JsonValue,
    VersionedComponent,
)
from ctower_kernel.catalog.lifecycle import CatalogDecision

__all__ = ["Catalog"]


class Catalog(Protocol):
    """Single tenant Catalog and CompanyBundle lifecycle authority."""

    def validate(
        self, tenant_key: str, bundle: CompanyBundle
    ) -> BundleValidation | CatalogProblem: ...

    def plan(
        self, tenant_key: str, bundle: CompanyBundle
    ) -> CompanyBundlePlan | CatalogProblem: ...

    def apply(
        self, tenant_key: str, command: CompanyBundleApply
    ) -> CompanyBundleCommandResult | CatalogProblem: ...

    def export(self, tenant_key: str) -> CompanyBundleExport | CatalogProblem: ...

    def stage(
        self,
        tenant_key: str,
        component: VersionedComponent,
        payload: dict[str, JsonValue],
    ) -> CatalogDecision | CatalogProblem: ...

    def publish(
        self, tenant_key: str, component: ComponentReference
    ) -> CatalogDecision | CatalogProblem: ...

    def resolve(
        self, tenant_key: str, component: ComponentReference
    ) -> CatalogDecision | CatalogProblem: ...

    def supersede(
        self, tenant_key: str, component: VersionedComponent
    ) -> CatalogDecision | CatalogProblem: ...

    def deprecate(
        self, tenant_key: str, component: ComponentReference
    ) -> CatalogDecision | CatalogProblem: ...

    def revoke(
        self, tenant_key: str, component: ComponentReference
    ) -> CatalogDecision | CatalogProblem: ...
