"""Single public protocol for Catalog lifecycle and CompanyBundle authority."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ctower_kernel.catalog.interface import (
    BundleValidation,
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    CompanyBundleExport,
    CompanyBundlePlan,
    ComponentKind,
    ComponentReference,
    JsonValue,
    VersionedComponent,
)
from ctower_kernel.catalog.lifecycle import CatalogDecision
from ctower_kernel.record import Actor
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["Catalog"]


class Catalog(Protocol):
    """Single tenant Catalog and CompanyBundle lifecycle authority."""

    def validate(
        self, actor: Actor, bundle: CompanyBundle
    ) -> BundleValidation | CatalogProblem: ...

    def plan(self, actor: Actor, bundle: CompanyBundle) -> CompanyBundlePlan | CatalogProblem: ...

    def apply(
        self,
        actor: Actor,
        command: CompanyBundleApply,
        *,
        telemetry: TelemetryContext,
    ) -> CompanyBundleCommandResult | CatalogProblem: ...

    def export(self, actor: Actor) -> CompanyBundleExport | CatalogProblem: ...

    def component_bytes(
        self,
        tenant_id: UUID,
        kind: ComponentKind,
        key: str,
        revision: int,
        *,
        content_digest: str | None = None,
    ) -> bytes | None: ...

    def stage(
        self,
        actor: Actor,
        component: VersionedComponent,
        payload: dict[str, JsonValue],
    ) -> CatalogDecision | CatalogProblem: ...

    def publish(
        self, actor: Actor, component: ComponentReference
    ) -> CatalogDecision | CatalogProblem: ...

    def resolve(
        self, actor: Actor, component: ComponentReference
    ) -> CatalogDecision | CatalogProblem: ...

    def supersede(
        self, actor: Actor, component: VersionedComponent
    ) -> CatalogDecision | CatalogProblem: ...

    def deprecate(
        self, actor: Actor, component: ComponentReference
    ) -> CatalogDecision | CatalogProblem: ...

    def revoke(
        self, actor: Actor, component: ComponentReference
    ) -> CatalogDecision | CatalogProblem: ...
