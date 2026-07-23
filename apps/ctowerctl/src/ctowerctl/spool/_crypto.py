"""Private authenticated spool record format."""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Final, Literal, cast
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from ctowerctl.spool._redaction import JsonObject, canonical_json

__all__ = [
    "FORMAT_VERSION",
    "GENESIS_HASH",
    "CryptoError",
    "KeySet",
    "OpenedRecord",
    "RecordType",
    "derive_keys",
    "inspect_signed_body",
    "key_id",
    "open_record",
    "seal_record",
    "sign_document",
    "verify_signed_document",
]

FORMAT_VERSION: Final = 1
GENESIS_HASH = "0" * 64
_MASTER_KEY_BYTES = 32
_GCM_TAG_BYTES = 16
_JSON_OBJECT: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)


class RecordType(StrEnum):
    """Closed durable record vocabulary."""

    COMMAND = "command"
    ACCEPTED_RECEIPT = "accepted_receipt"
    QUARANTINE_RECEIPT = "quarantine_receipt"
    DISPOSITION = "disposition"
    ANCHOR = "anchor"


class CryptoError(ValueError):
    """Authenticated record verification failed."""


class _DiskModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RecordHeader(_DiskModel):
    format_version: Literal[1]
    record_type: RecordType
    sequence: Annotated[int, Field(ge=1)]
    predecessor_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    key_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    nonce: str
    ciphertext_length: Annotated[int, Field(ge=1)]
    ciphertext_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _RecordDocument(_DiskModel):
    header: RecordHeader
    ciphertext: str


class _SignedDocument(_DiskModel):
    body: JsonObject
    mac: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


@dataclass(frozen=True, slots=True)
class KeySet:
    """HKDF-separated keys for one spool UUID."""

    encryption: bytes
    metadata_mac: bytes
    nonce: bytes


@dataclass(frozen=True, slots=True)
class SealedRecord:
    """Bytes and authenticated identity ready for durable append."""

    header: RecordHeader
    data: bytes
    record_hash: str

    @property
    def filename(self) -> str:
        return f"{self.header.sequence:020d}.{self.header.record_type.value}.rec"


@dataclass(frozen=True, slots=True)
class OpenedRecord:
    """Verified record decoded from disk."""

    header: RecordHeader
    payload: JsonObject
    record_hash: str


def key_id(master_key: bytes) -> str:
    """Return the non-secret stable identifier stored in metadata."""

    _require_master_key(master_key)
    return hashlib.sha256(b"ctower-spool-key-id\0" + master_key).hexdigest()[:32]


def derive_keys(master_key: bytes, spool_uuid: UUID) -> KeySet:
    """Derive independent AES, metadata-MAC, and deterministic-nonce keys."""

    _require_master_key(master_key)
    salt = spool_uuid.bytes
    return KeySet(
        encryption=_derive(master_key, salt, b"ctower-spool/v1/aes-256-gcm"),
        metadata_mac=_derive(master_key, salt, b"ctower-spool/v1/metadata-hmac"),
        nonce=_derive(master_key, salt, b"ctower-spool/v1/nonce-hmac"),
    )


def seal_record(
    record_type: RecordType,
    sequence: int,
    predecessor_hash: str,
    key_identifier: str,
    payload: JsonObject,
    keys: KeySet,
) -> SealedRecord:
    """Encrypt one sequence/type-bound record and authenticate its clear header."""

    nonce = _nonce(keys.nonce, sequence, record_type)
    plaintext = canonical_json(payload)
    provisional = _header(
        record_type,
        sequence,
        predecessor_hash,
        key_identifier,
        nonce,
        AESGCM(keys.encryption).encrypt(nonce, plaintext, b""),
    )
    # GCM's encrypted body is independent of AAD; only its authentication tag changes.
    # Binding the body digest breaks the otherwise circular "digest in AAD" dependency.
    ciphertext = AESGCM(keys.encryption).encrypt(
        nonce,
        plaintext,
        canonical_json(cast(JsonObject, provisional.model_dump(mode="json"))),
    )
    header = _header(
        record_type,
        sequence,
        predecessor_hash,
        key_identifier,
        nonce,
        ciphertext,
    )
    header_bytes = canonical_json(cast(JsonObject, header.model_dump(mode="json")))
    record_hash = hashlib.sha256(header_bytes + b"\n" + ciphertext).hexdigest()
    document = _RecordDocument(
        header=header,
        ciphertext=base64.b64encode(ciphertext).decode("ascii"),
    )
    return SealedRecord(
        header=header,
        data=canonical_json(cast(JsonObject, document.model_dump(mode="json"))) + b"\n",
        record_hash=record_hash,
    )


def open_record(data: bytes, keys: KeySet, expected_key_id: str) -> OpenedRecord:
    """Validate, decrypt, and strictly decode one durable record."""

    try:
        document = _RecordDocument.model_validate_json(data, strict=True)
        ciphertext = base64.b64decode(document.ciphertext, validate=True)
    except (ValidationError, ValueError) as error:
        raise CryptoError("record encoding is invalid") from error
    header = document.header
    if header.key_id != expected_key_id:
        raise CryptoError("record key identity does not match metadata")
    expected_nonce = _nonce(keys.nonce, header.sequence, header.record_type)
    encoded_nonce = _decode_nonce(header.nonce)
    _verify_nonce(encoded_nonce, expected_nonce)
    _verify_ciphertext(ciphertext, header)
    header_bytes = canonical_json(cast(JsonObject, header.model_dump(mode="json")))
    record_hash = hashlib.sha256(header_bytes + b"\n" + ciphertext).hexdigest()
    try:
        plaintext = AESGCM(keys.encryption).decrypt(encoded_nonce, ciphertext, header_bytes)
        payload = _JSON_OBJECT.validate_json(plaintext, strict=True)
    except (ValueError, ValidationError) as error:
        raise CryptoError("record authentication or payload validation failed") from error
    return OpenedRecord(header=header, payload=payload, record_hash=record_hash)


def _decode_nonce(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as error:
        raise CryptoError("record nonce encoding is invalid") from error


def _verify_nonce(encoded: bytes, expected: bytes) -> None:
    if not hmac.compare_digest(encoded, expected):
        raise CryptoError("record nonce is not sequence/type bound")


def _verify_ciphertext(ciphertext: bytes, header: RecordHeader) -> None:
    if len(ciphertext) != header.ciphertext_length:
        raise CryptoError("record ciphertext length does not match")
    digest = hashlib.sha256(ciphertext[:-_GCM_TAG_BYTES]).hexdigest()
    if not hmac.compare_digest(digest, header.ciphertext_sha256):
        raise CryptoError("record ciphertext digest does not match")


def sign_document(body: JsonObject, key: bytes) -> bytes:
    """Authenticate metadata or head without encrypting its non-sensitive fields."""

    body_bytes = canonical_json(body)
    document = _SignedDocument(body=body, mac=hmac.new(key, body_bytes, hashlib.sha256).hexdigest())
    return canonical_json(cast(JsonObject, document.model_dump(mode="json"))) + b"\n"


def inspect_signed_body(data: bytes) -> JsonObject:
    """Strictly parse an unauthenticated body only far enough to locate its key."""

    try:
        return _SignedDocument.model_validate_json(data, strict=True).body
    except ValidationError as error:
        raise CryptoError("signed document encoding is invalid") from error


def verify_signed_document(data: bytes, key: bytes) -> JsonObject:
    """Verify and return authenticated metadata or head."""

    try:
        document = _SignedDocument.model_validate_json(data, strict=True)
    except ValidationError as error:
        raise CryptoError("signed document encoding is invalid") from error
    expected = hmac.new(key, canonical_json(document.body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(document.mac, expected):
        raise CryptoError("signed document MAC does not match")
    return document.body


def _header(
    record_type: RecordType,
    sequence: int,
    predecessor_hash: str,
    key_identifier: str,
    nonce: bytes,
    ciphertext: bytes,
) -> RecordHeader:
    return RecordHeader(
        format_version=FORMAT_VERSION,
        record_type=record_type,
        sequence=sequence,
        predecessor_hash=predecessor_hash,
        key_id=key_identifier,
        nonce=base64.b64encode(nonce).decode("ascii"),
        ciphertext_length=len(ciphertext),
        ciphertext_sha256=hashlib.sha256(ciphertext[:-_GCM_TAG_BYTES]).hexdigest(),
    )


def _nonce(nonce_key: bytes, sequence: int, record_type: RecordType) -> bytes:
    if sequence < 1:
        raise CryptoError("record sequence must be positive")
    material = (
        b"ctower-spool/v1/nonce\0"
        + sequence.to_bytes(8, "big", signed=False)
        + b"\0"
        + record_type.value.encode("ascii")
    )
    return hmac.new(nonce_key, material, hashlib.sha256).digest()[:12]


def _derive(master_key: bytes, salt: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(master_key)


def _require_master_key(master_key: bytes) -> None:
    if len(master_key) != _MASTER_KEY_BYTES:
        raise CryptoError("spool master key must contain exactly 256 bits")
