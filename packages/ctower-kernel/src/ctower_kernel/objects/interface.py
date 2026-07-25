"""Generic content-addressed encrypted-object boundary."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "ObjectIntegrityError",
    "ObjectStore",
    "StoredObject",
    "digest_bytes",
    "verify_digest",
]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9._:/-]{2,255}$")


class ObjectIntegrityError(RuntimeError):
    """Fail-closed encrypted-object corruption or key-access failure."""


class StoredObject(BaseModel):
    """Strict receipt for one read-after-write verified encrypted object."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifact_digest: str
    object_key: str
    object_version: str
    ciphertext_sha256: str
    key_reference: str
    key_version: str
    wrapped_key_sha256: str
    uploaded_at: datetime
    verified_at: datetime

    @field_validator("artifact_digest", "ciphertext_sha256", "wrapped_key_sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("object receipt digest must be lowercase SHA-256")
        return value

    @field_validator("key_reference")
    @classmethod
    def _reference(cls, value: str) -> str:
        if _REFERENCE.fullmatch(value) is None:
            raise ValueError("object key reference must be stable and secret-free")
        return value


class ObjectStore(Protocol):
    """Fixed-shape object capability that never exposes a provider handle."""

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject: ...

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes: ...

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None: ...


def digest_bytes(content: bytes) -> str:
    """Return the canonical content digest."""

    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def verify_digest(content: bytes, expected: str) -> None:
    """Reject corrupt bytes before upload, evidence linkage, or restore."""

    if _DIGEST.fullmatch(expected) is None or digest_bytes(content) != expected:
        raise ObjectIntegrityError("object digest mismatch")
