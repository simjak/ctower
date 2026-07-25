"""Reference-only Ed25519 signing and detached-signature verification."""

from __future__ import annotations

import base64
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .canonical import artifact_digest, sha256_digest, strict_json
from .refusal import MigrationRefusal, RefusalCode

__all__ = ("ArtifactSigner", "ArtifactVerifier")

_KEY_REF = re.compile(r"^signing-key-ref:[a-z0-9/_-]{3,255}$")


class ArtifactSigner:
    def __init__(self, key_ref: str, key_version: int, private_key: Ed25519PrivateKey) -> None:
        if not _KEY_REF.fullmatch(key_ref) or key_version < 1:
            raise MigrationRefusal(RefusalCode.KEY_REFERENCE_UNKNOWN, "invalid key reference")
        self._key_ref = key_ref
        self._key_version = key_version
        self._private_key = private_key

    @classmethod
    def from_reference_map(
        cls, map_path: Path, key_ref: str, *, key_version: int
    ) -> ArtifactSigner:
        mapping_value = strict_json(_read_regular(map_path, protected=True), context="key map")
        if not isinstance(mapping_value, dict):
            raise MigrationRefusal(RefusalCode.KEY_REFERENCE_UNKNOWN, "key map shape")
        key_path = mapping_value.get(key_ref)
        if not isinstance(key_path, str):
            raise MigrationRefusal(RefusalCode.KEY_REFERENCE_UNKNOWN, "unmapped key reference")
        key_bytes = _read_regular(Path(key_path), protected=True)
        try:
            private_key = serialization.load_pem_private_key(key_bytes, password=None)
        except (TypeError, ValueError) as error:
            raise MigrationRefusal(
                RefusalCode.KEY_REFERENCE_UNKNOWN, "private key format"
            ) from error
        if not isinstance(private_key, Ed25519PrivateKey):
            raise MigrationRefusal(RefusalCode.KEY_REFERENCE_UNKNOWN, "private key algorithm")
        return cls(key_ref, key_version, private_key)

    def detached(self, signed_digest: str) -> dict[str, JsonScalar]:
        signature = self._private_key.sign(signed_digest.encode("ascii"))
        public_key = self._private_key.public_key()
        public_raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return {
            "algorithm": "Ed25519",
            "signed_digest": signed_digest,
            "key_ref": self._key_ref,
            "key_version": self._key_version,
            "public_key_digest": sha256_digest(public_raw),
            "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
        }

    def seal(self, artifact: Mapping[str, Any], digest_field: str) -> dict[str, Any]:
        sealed = dict(artifact)
        digest = artifact_digest(sealed, digest_field, "signature")
        sealed[digest_field] = digest
        sealed["signature"] = self.detached(digest)
        return sealed


class ArtifactVerifier:
    def __init__(self, public_key: Ed25519PublicKey) -> None:
        self._public_key = public_key
        public_raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.public_key_digest = sha256_digest(public_raw)

    @classmethod
    def from_path(cls, path: Path) -> ArtifactVerifier:
        key_bytes = _read_regular(path, protected=False)
        try:
            key = serialization.load_pem_public_key(key_bytes)
        except (TypeError, ValueError) as error:
            raise MigrationRefusal(RefusalCode.SIGNATURE_INVALID, "public key format") from error
        if not isinstance(key, Ed25519PublicKey):
            raise MigrationRefusal(RefusalCode.SIGNATURE_INVALID, "public key algorithm")
        return cls(key)

    def verify(self, artifact: Mapping[str, Any], digest_field: str) -> str:
        digest_value = artifact.get(digest_field)
        signature_value = artifact.get("signature")
        if not isinstance(digest_value, str) or not isinstance(signature_value, dict):
            raise MigrationRefusal(RefusalCode.SIGNATURE_INVALID, digest_field)
        expected = artifact_digest(artifact, digest_field, "signature")
        if digest_value != expected:
            raise MigrationRefusal(RefusalCode.SIGNATURE_REBOUND, digest_field)
        self._verify_detached(signature_value, digest_value)
        return digest_value

    def _verify_detached(self, signature: Mapping[str, object], digest: str) -> None:
        if (
            signature.get("algorithm") != "Ed25519"
            or signature.get("signed_digest") != digest
            or signature.get("public_key_digest") != self.public_key_digest
        ):
            raise MigrationRefusal(RefusalCode.SIGNATURE_REBOUND, "detached signature binding")
        encoded = signature.get("signature")
        if not isinstance(encoded, str):
            raise MigrationRefusal(RefusalCode.SIGNATURE_INVALID, "signature encoding")
        try:
            raw = base64.urlsafe_b64decode(encoded + "==")
            self._public_key.verify(raw, digest.encode("ascii"))
        except (InvalidSignature, ValueError) as error:
            raise MigrationRefusal(
                RefusalCode.SIGNATURE_INVALID, "signature verification"
            ) from error


JsonScalar = str | int


def _read_regular(path: Path, *, protected: bool) -> bytes:
    metadata = _key_metadata(path, protected=protected)
    fd = _open_key(path)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise MigrationRefusal(RefusalCode.SOURCE_DRIFT, "key material identity")
        return os.read(fd, 1024 * 1024)
    finally:
        os.close(fd)


def _key_metadata(path: Path, *, protected: bool) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise MigrationRefusal(RefusalCode.SOURCE_UNREADABLE, "key material path") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MigrationRefusal(RefusalCode.SOURCE_NOT_REGULAR, "key material path")
    if protected and metadata.st_mode & 0o077:
        raise MigrationRefusal(RefusalCode.KEY_FILE_INSECURE, "key file permissions")
    return metadata


def _open_key(path: Path) -> int:
    try:
        return os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise MigrationRefusal(RefusalCode.SOURCE_UNREADABLE, "key material path") from error
