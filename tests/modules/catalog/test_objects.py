from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from ctower_kernel.catalog import (
    CatalogObjectError,
    CatalogPayloadStager,
)
from ctower_kernel.objects import StoredObject
from modules.catalog.support import minimal_bundle

_TENANT_ID = UUID("00000000-0000-4000-8000-000000000001")


class MemoryObjectStore:
    def __init__(self, *, corrupt_read: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.corrupt_read = corrupt_read

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        del tenant_id
        self.objects[artifact_digest] = content
        now = datetime(2026, 7, 24, tzinfo=UTC)
        return StoredObject(
            artifact_digest=artifact_digest,
            object_key="catalog/" + artifact_digest,
            object_version="v1",
            ciphertext_sha256="sha256:" + "1" * 64,
            key_reference=key_reference,
            key_version="v1",
            wrapped_key_sha256="sha256:" + "2" * 64,
            uploaded_at=now,
            verified_at=now,
        )

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes:
        del tenant_id
        content = self.objects[receipt.artifact_digest]
        return content + b"!" if self.corrupt_read else content

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None:
        del tenant_id
        self.objects.pop(receipt.artifact_digest)


def test_catalog_uses_the_shared_object_port_and_verifies_read_back() -> None:
    store = MemoryObjectStore()
    staged = CatalogPayloadStager(store, key_reference="vault:catalog-key").stage(
        _TENANT_ID, minimal_bundle()
    )

    assert len(staged) == len(minimal_bundle().resources)
    assert {item.component.content_digest for item in staged} == set(store.objects)


def test_catalog_object_corruption_fails_before_activation() -> None:
    store = MemoryObjectStore(corrupt_read=True)

    with pytest.raises(CatalogObjectError, match="failed closed"):
        CatalogPayloadStager(store, key_reference="vault:catalog-key").stage(
            _TENANT_ID, minimal_bundle()
        )
