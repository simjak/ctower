"""Per-object AES-GCM envelope custody for RESTRICTED console output."""

from __future__ import annotations

import secrets
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ctower_kernel.console.models import ConsoleCiphertext

__all__ = ["AesGcmConsoleCipher"]

_REFERENCE_PREFIXES = ("secret-service:", "vault:", "kms:")
_AES_256_KEY_BYTES = 32


class AesGcmConsoleCipher:
    """Encrypt every object under a fresh DEK, then wrap that DEK under one KEK."""

    def __init__(self, *, wrapping_key: bytes, wrapping_key_reference: str) -> None:
        if len(wrapping_key) != _AES_256_KEY_BYTES:
            raise ValueError("console output wrapping key must be a 256-bit key")
        if not wrapping_key_reference.startswith(_REFERENCE_PREFIXES):
            raise ValueError("console output wrapping key must be identified by a secret reference")
        self._wrapping_key = wrapping_key
        self._wrapping_key_reference = wrapping_key_reference

    def encrypt(self, object_id: UUID, plaintext: bytes, *, aad: bytes) -> ConsoleCiphertext:
        data_key = secrets.token_bytes(32)
        content_nonce = secrets.token_bytes(12)
        wrapping_nonce = secrets.token_bytes(12)
        data_key_reference = uuid4()
        ciphertext = AESGCM(data_key).encrypt(content_nonce, plaintext, aad)
        wrapped = AESGCM(self._wrapping_key).encrypt(
            wrapping_nonce,
            data_key,
            _wrapping_aad(object_id, data_key_reference, self._wrapping_key_reference),
        )
        return ConsoleCiphertext(
            object_id=object_id,
            ciphertext=ciphertext,
            content_nonce=content_nonce,
            wrapped_data_key=wrapped,
            wrapping_nonce=wrapping_nonce,
            wrapping_key_reference=self._wrapping_key_reference,
            data_key_reference=data_key_reference,
        )

    def decrypt(self, envelope: ConsoleCiphertext, *, reader: str, aad: bytes) -> bytes:
        if reader != "console_output_reader":
            raise PermissionError("console output requires the console_output_reader identity")
        if envelope.wrapping_key_reference != self._wrapping_key_reference:
            raise ValueError("console output wrapping-key reference mismatch")
        try:
            data_key = AESGCM(self._wrapping_key).decrypt(
                envelope.wrapping_nonce,
                envelope.wrapped_data_key,
                _wrapping_aad(
                    envelope.object_id,
                    envelope.data_key_reference,
                    envelope.wrapping_key_reference,
                ),
            )
            return AESGCM(data_key).decrypt(envelope.content_nonce, envelope.ciphertext, aad)
        except InvalidTag as error:
            raise ValueError("console output envelope authentication failed") from error


def _wrapping_aad(object_id: UUID, data_key_reference: UUID, key_reference: str) -> bytes:
    return f"{object_id}:{data_key_reference}:{key_reference}".encode()
