"""Catalog bridge to the shared generic content-addressed object port."""

from __future__ import annotations

from uuid import UUID

from ctower_kernel.catalog._canonical import canonical_bytes
from ctower_kernel.catalog.interface import CompanyBundle
from ctower_kernel.catalog.object_interface import CatalogObjectError, StagedPayload
from ctower_kernel.objects import (
    ObjectIntegrityError,
    ObjectStore,
    verify_digest,
)

__all__: tuple[str, ...] = ()


def stage_payloads(
    tenant_id: UUID,
    bundle: CompanyBundle,
    store: ObjectStore,
    *,
    key_reference: str,
) -> tuple[StagedPayload, ...]:
    """Stage and read back every payload before Catalog facts can become active."""

    staged: list[StagedPayload] = []
    for resource in bundle.resources:
        component = resource.component
        content = canonical_bytes(resource.payload)
        try:
            verify_digest(content, component.content_digest)
            receipt = store.put_verified(
                tenant_id,
                component.content_digest,
                content,
                key_reference=key_reference,
            )
            recovered = store.read_verified(tenant_id, receipt)
            _verify_staged(
                content,
                recovered,
                expected_digest=component.content_digest,
                receipt_digest=receipt.artifact_digest,
            )
        except (ObjectIntegrityError, OSError, RuntimeError) as error:
            raise CatalogObjectError("catalog payload staging failed closed") from error
        staged.append(StagedPayload(component=component.reference(), receipt=receipt))
    return tuple(staged)


def _verify_staged(
    expected: bytes,
    recovered: bytes,
    *,
    expected_digest: str,
    receipt_digest: str,
) -> None:
    if receipt_digest != expected_digest:
        raise ObjectIntegrityError("object receipt digest mismatch")
    verify_digest(recovered, expected_digest)
    if recovered != expected:
        raise ObjectIntegrityError("object read-back bytes mismatch")
