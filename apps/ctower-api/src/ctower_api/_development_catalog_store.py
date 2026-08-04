"""Development-runtime local object capability for Catalog payloads."""

from __future__ import annotations

import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from ctower_kernel.objects import ObjectIntegrityError, StoredObject, digest_bytes, verify_digest

__all__ = ["DevelopmentCatalogObjectStore", "development_catalog_store"]


class DevelopmentCatalogObjectStore:
    """Owner-local, content-addressed object Adapter for the shadow development runtime."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        verify_digest(content, artifact_digest)
        object_dir = self._object_dir(tenant_id, artifact_digest)
        content_path = object_dir / "content.bin"
        receipt_path = object_dir / "receipt.json"
        if receipt_path.is_file():
            receipt = StoredObject.model_validate_json(receipt_path.read_text(encoding="utf-8"))
            if receipt.key_reference != key_reference:
                raise ObjectIntegrityError(
                    "existing development Catalog object uses another key reference"
                )
            existing = content_path.read_bytes()
            if digest_bytes(existing) != artifact_digest or existing != content:
                raise ObjectIntegrityError("existing development Catalog object bytes differ")
            return receipt
        now = datetime.now(UTC)
        receipt = StoredObject(
            artifact_digest=artifact_digest,
            object_key=f"development-catalog/{tenant_id}/{_digest_name(artifact_digest)}",
            object_version="version-1",
            ciphertext_sha256=digest_bytes(content),
            key_reference=key_reference,
            key_version="development-local-v1",
            wrapped_key_sha256=digest_bytes(key_reference.encode("utf-8")),
            uploaded_at=now,
            verified_at=now,
        )
        object_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        _write_owner_only(content_path, content)
        _write_owner_only(
            receipt_path,
            receipt.model_dump_json().encode("utf-8") + b"\n",
        )
        return receipt

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes:
        content_path = self._object_dir(tenant_id, receipt.artifact_digest) / "content.bin"
        content = content_path.read_bytes()
        verify_digest(content, receipt.artifact_digest)
        if digest_bytes(content) != receipt.ciphertext_sha256:
            raise ObjectIntegrityError("development Catalog object receipt digest mismatch")
        return content

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None:
        object_dir = self._object_dir(tenant_id, receipt.artifact_digest)
        for path in (object_dir / "content.bin", object_dir / "receipt.json"):
            path.unlink(missing_ok=True)
        with suppress(OSError):
            object_dir.rmdir()

    def _object_dir(self, tenant_id: UUID, artifact_digest: str) -> Path:
        return self._root / str(tenant_id) / _digest_name(artifact_digest)


def development_catalog_store() -> DevelopmentCatalogObjectStore:
    state_home = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    return DevelopmentCatalogObjectStore(state_home / "ctower" / "development-catalog-objects")


def _digest_name(value: str) -> str:
    if not value.startswith("sha256:"):
        raise ObjectIntegrityError("development Catalog object digest is malformed")
    return value.removeprefix("sha256:")


def _write_owner_only(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    path.chmod(0o600)
