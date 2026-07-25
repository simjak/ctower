"""Small public Catalog boundary for staged content-addressed payloads."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ctower_kernel.catalog.interface import ComponentReference
from ctower_kernel.objects import StoredObject

__all__ = ["CatalogObjectError", "StagedPayload"]


class CatalogObjectError(RuntimeError):
    """A payload could not be staged and read back through the shared object port."""


class StagedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    component: ComponentReference
    receipt: StoredObject
