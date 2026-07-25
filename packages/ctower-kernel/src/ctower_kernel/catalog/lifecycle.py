"""Universal component lifecycle decisions shared by every Catalog category."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from ctower_kernel.catalog.interface import ComponentReference, VersionedComponent

__all__ = ["CatalogDecision", "CatalogDecisionKind"]


class CatalogDecisionKind(StrEnum):
    STAGED = "staged"
    PUBLISHED = "published"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class CatalogDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    component: VersionedComponent
    decision: CatalogDecisionKind
    previous: ComponentReference | None = None
