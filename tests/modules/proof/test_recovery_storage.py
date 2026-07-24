"""Public fixed-storage composition tests over deterministic HTTP transport."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from ctower_api.recovery_storage import (
    ExternalIntegrityAuthority,
    KmsConfig,
    ObjectStoreConfig,
    RecoveryObjectStorage,
)
from ctower_kernel.proof.objects import ObjectIntegrityError, digest_bytes

NOW = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
HTTP_CREATED = 201
__all__: tuple[str, ...] = ()


class RecoveryTransport:
    """Deterministic external KMS plus versioned-object service."""

    def __init__(self) -> None:
        self.ciphertext = b""
        self.metadata: dict[str, str] = {}
        self.fault = ""
        self.erased = False
        self.encrypt_calls = 0
        self.put_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v1/"):
            return self._kms(request)
        return self._object(request)

    def _object(self, request: httpx.Request) -> httpx.Response:
        handler = {
            "DELETE": self._delete,
            "GET": self._get,
            "HEAD": self._head,
            "PUT": self._put,
        }.get(request.method)
        return httpx.Response(405) if handler is None else handler(request)

    def _head(self, request: httpx.Request) -> httpx.Response:
        del request
        if not self.ciphertext:
            return httpx.Response(404)
        return httpx.Response(200, headers=self._object_headers())

    def _put(self, request: httpx.Request) -> httpx.Response:
        self.put_calls += 1
        status = 503 if self.fault == "put_status" else HTTP_CREATED
        if status == HTTP_CREATED:
            self.ciphertext = request.content
            self.metadata = {
                key: value
                for key, value in request.headers.items()
                if key.lower().startswith("x-amz-meta-ctower-")
            }
        headers = {} if self.fault == "put_version" else {"X-Amz-Version-Id": "v1"}
        return httpx.Response(status, headers=headers)

    def _get(self, request: httpx.Request) -> httpx.Response:
        del request
        if self.fault == "get_status":
            return httpx.Response(404)
        content = b"corrupt" if self.fault == "corrupt_object" else self.ciphertext
        return httpx.Response(200, content=content, headers=self._object_headers())

    def _delete(self, request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503 if self.fault == "delete_status" else 204)

    def _kms(self, request: httpx.Request) -> httpx.Response:
        payload = _json(request)
        if request.url.path == "/v1/encrypt":
            return self._encrypt(payload)
        if request.url.path == "/v1/decrypt":
            return self._decrypt(payload)
        if request.url.path == "/v1/key-erasure":
            return self._erase(payload)
        if request.url.path == "/v1/sign":
            return self._sign(payload)
        if request.url.path == "/v1/verify":
            return self._verify(payload)
        return httpx.Response(404)

    def _encrypt(self, payload: dict[str, object]) -> httpx.Response:
        self.encrypt_calls += 1
        plaintext = base64.b64decode(str(payload["plaintext_base64"]))
        ciphertext = b"ciphertext:" + plaintext[::-1]
        digest = digest_bytes(ciphertext)
        if self.fault == "encrypt_digest":
            digest = "sha256:" + "0" * 64
        key_reference = str(payload["key_reference"])
        if self.fault == "encrypt_key":
            key_reference = "kms-ref:test/wrong"
        return _response(
            {
                "ciphertext_base64": base64.b64encode(ciphertext).decode(),
                "ciphertext_sha256": digest,
                "key_reference": key_reference,
                "key_version": "v1",
                "wrapped_key_sha256": "sha256:" + "1" * 64,
                "used_at": _timestamp(),
            }
        )

    def _object_headers(self) -> dict[str, str]:
        headers = {"X-Amz-Version-Id": "v1", **self.metadata}
        if self.fault == "existing_key":
            headers["x-amz-meta-ctower-key-reference"] = "kms-ref:test/wrong"
        return headers

    def _decrypt(self, payload: dict[str, object]) -> httpx.Response:
        ciphertext = base64.b64decode(str(payload["ciphertext_base64"]))
        plaintext = ciphertext.removeprefix(b"ciphertext:")[::-1]
        return _response(
            {
                "plaintext_base64": base64.b64encode(plaintext).decode(),
                "key_reference": payload["key_reference"],
            }
        )

    def _erase(self, payload: dict[str, object]) -> httpx.Response:
        self.erased = True
        return _response(
            {
                "erased": self.fault != "erase_denied",
                "key_reference": payload["key_reference"],
                "key_version": payload["key_version"],
            }
        )

    def _sign(self, payload: dict[str, object]) -> httpx.Response:
        digest = str(payload["digest"])
        if self.fault == "sign_digest":
            digest = "sha256:" + "2" * 64
        return _response(
            {
                "digest": digest,
                "signature": "external-signature",
                "key_reference": payload["key_reference"],
                "key_version": "v1",
                "public_key_sha256": "sha256:" + "3" * 64,
                "signed_at": _timestamp(),
            }
        )

    def _verify(self, payload: dict[str, object]) -> httpx.Response:
        key_reference = str(payload["key_reference"])
        if self.fault == "verify_key":
            key_reference = "kms-ref:test/wrong"
        reason = "invalid_signature" if self.fault == "verify_reason" else "valid"
        return _response(
            {
                "digest": payload["digest"],
                "key_reference": key_reference,
                "key_version": payload["key_version"],
                "public_key_sha256": payload["public_key_sha256"],
                "verified": True,
                "verified_at": _timestamp(),
                "reason": reason,
            }
        )


def test_concrete_storage_and_external_signing_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = RecoveryTransport()
    _install_transport(monkeypatch, transport)
    storage = RecoveryObjectStorage(_object_config(), _kms_config())
    tenant_id = uuid4()
    content = b"restored encrypted evidence"
    artifact_digest = digest_bytes(content)

    receipt = storage.put_verified(
        tenant_id,
        artifact_digest,
        content,
        key_reference="kms-ref:test/object",
    )
    reconciled = storage.put_verified(
        tenant_id,
        artifact_digest,
        content,
        key_reference="kms-ref:test/object",
    )

    assert storage.read_verified(tenant_id, receipt) == content
    assert storage.read_verified(tenant_id, reconciled) == content
    assert transport.encrypt_calls == 1
    assert transport.put_calls == 1
    storage.erase(tenant_id, receipt)
    assert transport.erased is True
    signer = ExternalIntegrityAuthority(_kms_config())
    signature = signer.sign(artifact_digest, key_reference="kms-ref:test/signing")
    verification = signer.verify(signature)
    assert verification.verified is True
    assert verification.digest == artifact_digest


@pytest.mark.parametrize(
    ("fault", "match"),
    [
        ("corrupt_object", "ciphertext"),
        ("existing_key", "wrong key reference"),
    ],
)
def test_same_content_reconciliation_verifies_existing_bytes_and_receipt(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    match: str,
) -> None:
    transport = RecoveryTransport()
    _install_transport(monkeypatch, transport)
    storage = RecoveryObjectStorage(_object_config(), _kms_config())
    tenant_id = uuid4()
    content = b"reconciled evidence"
    digest = digest_bytes(content)
    storage.put_verified(
        tenant_id,
        digest,
        content,
        key_reference="kms-ref:test/object",
    )
    transport.fault = fault

    with pytest.raises(ObjectIntegrityError, match=match):
        storage.put_verified(
            tenant_id,
            digest,
            content,
            key_reference="kms-ref:test/object",
        )

    assert transport.encrypt_calls == 1
    assert transport.put_calls == 1


@pytest.mark.parametrize(
    ("fault", "match"),
    [
        ("encrypt_digest", "ciphertext digest"),
        ("encrypt_key", "wrong key"),
        ("put_status", "PUT failed"),
        ("put_version", "version receipt"),
    ],
)
def test_upload_faults_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    match: str,
) -> None:
    transport = RecoveryTransport()
    transport.fault = fault
    _install_transport(monkeypatch, transport)
    content = b"evidence"

    with pytest.raises(ObjectIntegrityError, match=match):
        RecoveryObjectStorage(_object_config(), _kms_config()).put_verified(
            uuid4(),
            digest_bytes(content),
            content,
            key_reference="kms-ref:test/object",
        )


def test_read_erase_and_signature_faults_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = RecoveryTransport()
    _install_transport(monkeypatch, transport)
    storage = RecoveryObjectStorage(_object_config(), _kms_config())
    tenant_id = uuid4()
    content = b"evidence"
    receipt = storage.put_verified(
        tenant_id,
        digest_bytes(content),
        content,
        key_reference="kms-ref:test/object",
    )

    with pytest.raises(ObjectIntegrityError, match="another tenant"):
        storage.read_verified(uuid4(), receipt)
    transport.fault = "get_status"
    with pytest.raises(ObjectIntegrityError, match="GET failed"):
        storage.read_verified(tenant_id, receipt)
    transport.fault = "corrupt_object"
    with pytest.raises(ObjectIntegrityError, match="ciphertext"):
        storage.read_verified(tenant_id, receipt)
    transport.fault = "delete_status"
    with pytest.raises(ObjectIntegrityError, match="erasure failed"):
        storage.erase(tenant_id, receipt)
    transport.fault = "erase_denied"
    with pytest.raises(ObjectIntegrityError, match="key erasure"):
        storage.erase(tenant_id, receipt)
    signer = ExternalIntegrityAuthority(_kms_config())
    transport.fault = "sign_digest"
    with pytest.raises(ObjectIntegrityError, match="not request-bound"):
        signer.sign(digest_bytes(content), key_reference="kms-ref:test/signing")
    transport.fault = ""
    signature = signer.sign(digest_bytes(content), key_reference="kms-ref:test/signing")
    transport.fault = "verify_key"
    with pytest.raises(ObjectIntegrityError, match="not signature-bound"):
        signer.verify(signature)
    transport.fault = "verify_reason"
    with pytest.raises(ObjectIntegrityError, match="result and reason disagree"):
        signer.verify(signature)


def test_configs_reject_credentials_and_invalid_bucket() -> None:
    with pytest.raises(ValidationError):
        KmsConfig(
            endpoint="https://user:password@kms.test",
            workload_identity_ref="workload-ref:test",
        )
    with pytest.raises(ValidationError):
        ObjectStoreConfig(
            endpoint="http://objects.test",
            bucket="Not Valid",
            workload_identity_ref="workload-ref:test",
        )


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    transport: RecoveryTransport,
) -> None:
    client_type = httpx.Client
    mock = httpx.MockTransport(transport)
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **_kwargs: client_type(transport=mock),
    )


def _kms_config() -> KmsConfig:
    return KmsConfig(
        endpoint="https://kms.test",
        workload_identity_ref="workload-ref:test/kms",
    )


def _object_config() -> ObjectStoreConfig:
    return ObjectStoreConfig(
        endpoint="https://objects.test",
        bucket="ctower-test",
        workload_identity_ref="workload-ref:test/objects",
    )


def _json(request: httpx.Request) -> dict[str, object]:
    payload = json.loads(request.read())
    assert isinstance(payload, dict)
    return payload


def _response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _timestamp() -> str:
    return NOW.isoformat().replace("+00:00", "Z")
