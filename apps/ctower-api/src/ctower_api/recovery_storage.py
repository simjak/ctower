"""Fixed concrete storage and integrity composition for CP3-C operations."""

from __future__ import annotations

from uuid import UUID

from ctower_api._kms import (
    ExternalKms,
    KmsConfig,
    SignatureReceipt,
    VerificationReceipt,
)
from ctower_api._object_store import ObjectStoreConfig, S3CompatibleObjectStore
from ctower_kernel.proof.objects import StoredObject
from ctower_kernel.record.recovery import SignatureVerification

__all__ = [
    "ExternalIntegrityAuthority",
    "KmsConfig",
    "ObjectStoreConfig",
    "RecoveryObjectStorage",
    "SignatureReceipt",
    "VerificationReceipt",
]


class RecoveryObjectStorage:
    """Compose the selected S3-compatible and KMS Adapters as one capability."""

    def __init__(self, object_config: ObjectStoreConfig, kms_config: KmsConfig) -> None:
        self._store = S3CompatibleObjectStore(object_config, ExternalKms(kms_config))

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        """Encrypt, conditionally upload, read back, decrypt, and verify."""

        return self._store.put_verified(
            tenant_id,
            artifact_digest,
            content,
            key_reference=key_reference,
        )

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes:
        """Read one exact version and verify recovered plaintext."""

        return self._store.read_verified(tenant_id, receipt)

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None:
        """Erase one exact version and its wrapped data key."""

        self._store.erase(tenant_id, receipt)


class ExternalIntegrityAuthority:
    """Compose the selected external signer without exposing private key material."""

    def __init__(self, config: KmsConfig) -> None:
        self._kms = ExternalKms(config)

    def sign(self, digest: str, *, key_reference: str) -> SignatureReceipt:
        """Request an externally held signature over one digest."""

        return self._kms.sign(digest, key_reference=key_reference)

    def verify(self, receipt: SignatureReceipt) -> SignatureVerification:
        """Return an exact signature-bound external verification receipt."""

        verification = self._kms.verify(receipt)
        return SignatureVerification(
            digest=receipt.digest,
            signature=receipt.signature,
            signing_key_reference=receipt.key_reference,
            signing_key_version=receipt.key_version,
            public_key_sha256=receipt.public_key_sha256,
            signed_at=receipt.signed_at,
            verified=verification.verified,
            verified_at=verification.verified_at,
            reason=verification.reason,
        )
