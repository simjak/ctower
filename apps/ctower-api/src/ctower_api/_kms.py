"""Fixed external KMS/Vault client using only references and typed receipts."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ctower_kernel.proof.objects import ObjectIntegrityError

__all__: tuple[str, ...] = ()


class KmsConfig(BaseModel):
    """Secret-free connection identity for a root-configured mTLS client."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    endpoint: str
    workload_identity_ref: str
    timeout_seconds: int = 10

    @field_validator("endpoint")
    @classmethod
    def _endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query:
            raise ValueError("KMS endpoint must be credential-free HTTPS")
        return value.rstrip("/")


class EncryptionReceipt(BaseModel):
    """Ciphertext returned by external envelope-encryption authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ciphertext: bytes
    ciphertext_sha256: str
    key_reference: str
    key_version: str
    wrapped_key_sha256: str
    used_at: datetime


class SignatureReceipt(BaseModel):
    """Signature metadata without an application-owned private key."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    digest: str
    signature: str
    key_reference: str
    key_version: str
    public_key_sha256: str
    signed_at: datetime


class VerificationReceipt(BaseModel):
    """Fail-closed external signature verification result."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    digest: str
    key_reference: str
    key_version: str
    public_key_sha256: str
    verified: bool
    verified_at: datetime
    reason: Literal["valid", "invalid_signature", "key_unavailable", "wrong_key_reference"]

    @model_validator(mode="after")
    def _consistent_result(self) -> VerificationReceipt:
        if self.verified != (self.reason == "valid"):
            raise ValueError("KMS verification result and reason disagree")
        return self


class ExternalKms:
    """One selected private KMS API; endpoint paths and payloads are fixed."""

    def __init__(self, config: KmsConfig, *, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            timeout=config.timeout_seconds,
            follow_redirects=False,
        )

    def encrypt(self, content: bytes, *, key_reference: str) -> EncryptionReceipt:
        payload = self._post(
            "/v1/encrypt",
            {
                "schema_id": "ctower.kms-encrypt-request/v1",
                "key_reference": key_reference,
                "plaintext_base64": base64.b64encode(content).decode("ascii"),
                "workload_identity_ref": self._config.workload_identity_ref,
            },
        )
        receipt = _encryption_receipt(payload)
        if _digest(receipt.ciphertext) != receipt.ciphertext_sha256:
            raise ObjectIntegrityError("KMS ciphertext digest mismatch")
        if receipt.key_reference != key_reference:
            raise ObjectIntegrityError("KMS used the wrong key reference")
        return receipt

    def decrypt(self, receipt: EncryptionReceipt) -> bytes:
        payload = self._post(
            "/v1/decrypt",
            {
                "schema_id": "ctower.kms-decrypt-request/v1",
                "ciphertext_base64": base64.b64encode(receipt.ciphertext).decode("ascii"),
                "ciphertext_sha256": receipt.ciphertext_sha256,
                "key_reference": receipt.key_reference,
                "key_version": receipt.key_version,
                "wrapped_key_sha256": receipt.wrapped_key_sha256,
                "workload_identity_ref": self._config.workload_identity_ref,
            },
        )
        plaintext = _base64_field(payload, "plaintext_base64")
        if payload.get("key_reference") != receipt.key_reference:
            raise ObjectIntegrityError("KMS decrypted with the wrong key reference")
        return plaintext

    def sign(self, digest: str, *, key_reference: str) -> SignatureReceipt:
        payload = self._post(
            "/v1/sign",
            {
                "schema_id": "ctower.kms-sign-request/v1",
                "digest": digest,
                "key_reference": key_reference,
                "workload_identity_ref": self._config.workload_identity_ref,
            },
        )
        receipt = _signature_receipt(payload)
        if receipt.digest != digest or receipt.key_reference != key_reference:
            raise ObjectIntegrityError("KMS signature receipt is not request-bound")
        return receipt

    def verify(self, receipt: SignatureReceipt) -> VerificationReceipt:
        payload = self._post(
            "/v1/verify",
            {
                "schema_id": "ctower.kms-verify-request/v1",
                **receipt.model_dump(mode="json"),
                "workload_identity_ref": self._config.workload_identity_ref,
            },
        )
        verification = _verification_receipt(payload)
        if (
            verification.digest != receipt.digest
            or verification.key_reference != receipt.key_reference
            or verification.key_version != receipt.key_version
            or verification.public_key_sha256 != receipt.public_key_sha256
        ):
            raise ObjectIntegrityError("KMS verification receipt is not signature-bound")
        return verification

    def erase_key(self, receipt: EncryptionReceipt) -> None:
        """Erase the exact wrapped per-object key without accepting key bytes."""

        payload = self._post(
            "/v1/key-erasure",
            {
                "schema_id": "ctower.kms-key-erasure-request/v1",
                "key_reference": receipt.key_reference,
                "key_version": receipt.key_version,
                "wrapped_key_sha256": receipt.wrapped_key_sha256,
                "workload_identity_ref": self._config.workload_identity_ref,
            },
        )
        if (
            payload.get("erased") is not True
            or payload.get("key_reference") != receipt.key_reference
            or payload.get("key_version") != receipt.key_version
        ):
            raise ObjectIntegrityError("KMS did not prove exact key erasure")

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        response = self._client.post(f"{self._config.endpoint}{path}", json=payload)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ObjectIntegrityError("KMS returned a malformed response")
        return value


def _encryption_receipt(payload: dict[str, object]) -> EncryptionReceipt:
    return EncryptionReceipt(
        ciphertext=_base64_field(payload, "ciphertext_base64"),
        ciphertext_sha256=_string_field(payload, "ciphertext_sha256"),
        key_reference=_string_field(payload, "key_reference"),
        key_version=_string_field(payload, "key_version"),
        wrapped_key_sha256=_string_field(payload, "wrapped_key_sha256"),
        used_at=_datetime_field(payload, "used_at"),
    )


def _signature_receipt(payload: dict[str, object]) -> SignatureReceipt:
    return SignatureReceipt(
        digest=_string_field(payload, "digest"),
        signature=_string_field(payload, "signature"),
        key_reference=_string_field(payload, "key_reference"),
        key_version=_string_field(payload, "key_version"),
        public_key_sha256=_string_field(payload, "public_key_sha256"),
        signed_at=_datetime_field(payload, "signed_at"),
    )


def _verification_receipt(payload: dict[str, object]) -> VerificationReceipt:
    verified = payload.get("verified")
    if not isinstance(verified, bool):
        raise ObjectIntegrityError("KMS response omitted verified")
    reason = _reason_field(payload)
    if verified != (reason == "valid"):
        raise ObjectIntegrityError("KMS verification result and reason disagree")
    return VerificationReceipt(
        digest=_string_field(payload, "digest"),
        key_reference=_string_field(payload, "key_reference"),
        key_version=_string_field(payload, "key_version"),
        public_key_sha256=_string_field(payload, "public_key_sha256"),
        verified=verified,
        verified_at=_datetime_field(payload, "verified_at"),
        reason=reason,
    )


def _base64_field(payload: dict[str, object], field: str) -> bytes:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ObjectIntegrityError(f"KMS response omitted {field}")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as error:
        raise ObjectIntegrityError(f"KMS response contained invalid {field}") from error


def _string_field(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ObjectIntegrityError(f"KMS response omitted {field}")
    return value


def _datetime_field(payload: dict[str, object], field: str) -> datetime:
    value = _string_field(payload, field)
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ObjectIntegrityError(f"KMS response contained invalid {field}") from error


def _reason_field(
    payload: dict[str, object],
) -> Literal["valid", "invalid_signature", "key_unavailable", "wrong_key_reference"]:
    value = _string_field(payload, "reason")
    if value == "valid":
        return "valid"
    if value == "invalid_signature":
        return "invalid_signature"
    if value == "key_unavailable":
        return "key_unavailable"
    if value == "wrong_key_reference":
        return "wrong_key_reference"
    raise ObjectIntegrityError("KMS response contained invalid reason")


def _digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
