"""Concrete private S3-compatible encrypted object Adapter."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

from ctower_api._kms import EncryptionReceipt, ExternalKms
from ctower_kernel.objects import (
    ObjectIntegrityError,
    StoredObject,
    digest_bytes,
    verify_digest,
)

__all__: tuple[str, ...] = ()
_HTTP_OK = 200


class ObjectStoreConfig(BaseModel):
    """Secret-free immutable bucket identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    endpoint: str
    bucket: str
    workload_identity_ref: str
    timeout_seconds: int = 15

    @field_validator("endpoint")
    @classmethod
    def _endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query:
            raise ValueError("object endpoint must be credential-free HTTPS")
        return value.rstrip("/")

    @field_validator("bucket")
    @classmethod
    def _bucket(cls, value: str) -> str:
        valid = all(
            character.islower() or character.isdigit() or character in ".-" for character in value
        )
        if not value or not valid:
            raise ValueError("object bucket must be one stable DNS-style name")
        return value


class S3CompatibleObjectStore:
    """Write immutable ciphertext, read it back, then verify recovered plaintext."""

    def __init__(
        self,
        config: ObjectStoreConfig,
        kms: ExternalKms,
        *,
        client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._kms = kms
        self._client = client or httpx.Client(
            timeout=config.timeout_seconds,
            follow_redirects=False,
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        verify_digest(content, artifact_digest)
        encrypted = self._kms.encrypt(content, key_reference=key_reference)
        object_key = _object_key(tenant_id, artifact_digest)
        uploaded_at = self._clock()
        response = self._client.put(
            self._url(object_key),
            content=encrypted.ciphertext,
            headers={
                "Content-Type": "application/octet-stream",
                "If-None-Match": "*",
                "X-Ctower-Ciphertext-Sha256": encrypted.ciphertext_sha256,
                "X-Ctower-Workload-Identity-Ref": self._config.workload_identity_ref,
            },
        )
        if response.status_code not in (200, 201):
            raise ObjectIntegrityError(f"immutable object PUT failed: {response.status_code}")
        object_version = response.headers.get("X-Amz-Version-Id")
        if not object_version:
            raise ObjectIntegrityError("object PUT omitted a version receipt")
        receipt = _stored_receipt(
            artifact_digest,
            object_key,
            object_version,
            encrypted,
            uploaded_at=uploaded_at,
            verified_at=self._clock(),
        )
        self.read_verified(tenant_id, receipt)
        return receipt

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes:
        if receipt.object_key != _object_key(tenant_id, receipt.artifact_digest):
            raise ObjectIntegrityError("object receipt belongs to another tenant or digest")
        response = self._client.get(
            self._url(receipt.object_key),
            params={"versionId": receipt.object_version},
            headers={
                "X-Ctower-Workload-Identity-Ref": self._config.workload_identity_ref,
            },
        )
        if response.status_code != _HTTP_OK:
            raise ObjectIntegrityError(f"versioned object GET failed: {response.status_code}")
        if digest_bytes(response.content) != receipt.ciphertext_sha256:
            raise ObjectIntegrityError("restored ciphertext is corrupt")
        encrypted = EncryptionReceipt(
            ciphertext=response.content,
            ciphertext_sha256=receipt.ciphertext_sha256,
            key_reference=receipt.key_reference,
            key_version=receipt.key_version,
            wrapped_key_sha256=receipt.wrapped_key_sha256,
            used_at=receipt.uploaded_at,
        )
        plaintext = self._kms.decrypt(encrypted)
        verify_digest(plaintext, receipt.artifact_digest)
        return plaintext

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None:
        if receipt.object_key != _object_key(tenant_id, receipt.artifact_digest):
            raise ObjectIntegrityError("object erasure receipt identity mismatch")
        response = self._client.delete(
            self._url(receipt.object_key),
            params={"versionId": receipt.object_version},
            headers={
                "X-Ctower-Workload-Identity-Ref": self._config.workload_identity_ref,
            },
        )
        if response.status_code not in (200, 204, 404):
            raise ObjectIntegrityError(f"exact object erasure failed: {response.status_code}")
        self._kms.erase_key(
            EncryptionReceipt(
                ciphertext=b"",
                ciphertext_sha256=receipt.ciphertext_sha256,
                key_reference=receipt.key_reference,
                key_version=receipt.key_version,
                wrapped_key_sha256=receipt.wrapped_key_sha256,
                used_at=receipt.uploaded_at,
            )
        )

    def _url(self, object_key: str) -> str:
        return f"{self._config.endpoint}/{quote(self._config.bucket)}/{quote(object_key, safe='/')}"


def _object_key(tenant_id: UUID, artifact_digest: str) -> str:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest) is None:
        raise ObjectIntegrityError("object key requires a canonical digest")
    return f"tenants/{tenant_id}/objects/sha256/{artifact_digest.removeprefix('sha256:')}"


def _stored_receipt(
    artifact_digest: str,
    object_key: str,
    object_version: str,
    encrypted: EncryptionReceipt,
    *,
    uploaded_at: datetime,
    verified_at: datetime,
) -> StoredObject:
    return StoredObject(
        artifact_digest=artifact_digest,
        object_key=object_key,
        object_version=object_version,
        ciphertext_sha256=encrypted.ciphertext_sha256,
        key_reference=encrypted.key_reference,
        key_version=encrypted.key_version,
        wrapped_key_sha256=encrypted.wrapped_key_sha256,
        uploaded_at=uploaded_at,
        verified_at=verified_at,
    )
