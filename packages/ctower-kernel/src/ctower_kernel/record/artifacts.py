"""Canonical signed-artifact verification at the lower Record boundary."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Any, cast

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from ctower_contracts import validator_for
from jsonschema import ValidationError

__all__ = [
    "ArtifactError",
    "ReviewerKey",
    "TrustedReviewerKeys",
    "parse_artifact",
    "reviewer_key",
    "verify_signed_artifact",
]

type TrustedReviewerKeys = Mapping[tuple[str, int], Ed25519PublicKey]
type ReviewerKey = tuple[str, int, str]


def parse_artifact(text: str, schema_ref: str) -> dict[str, Any]:
    """Parse one exact RFC 8785 artifact and validate its authored schema."""

    try:
        value = _exact_json(text)
        validator_for(schema_ref).validate(value)
    except (UnicodeError, ValueError, json.JSONDecodeError, ValidationError) as error:
        raise ArtifactError("artifact-invalid") from error
    return cast(dict[str, Any], value)


def _exact_json(text: str) -> dict[str, object]:
    value = json.loads(
        text,
        object_pairs_hook=_unique_object,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )
    if not isinstance(value, dict) or rfc8785.dumps(value).decode("utf-8") != text:
        raise ValueError("artifact is not exact canonical JSON")
    return value


def verify_signed_artifact(
    text: str,
    schema_ref: str,
    digest_field: str,
    trusted_keys: TrustedReviewerKeys,
) -> tuple[dict[str, Any], str]:
    artifact = parse_artifact(text, schema_ref)
    digest = artifact.get(digest_field)
    signature = artifact.get("signature")
    if not isinstance(digest, str) or not isinstance(signature, dict):
        raise ArtifactError("signature-invalid")
    canonical = {
        key: value for key, value in artifact.items() if key not in {digest_field, "signature"}
    }
    expected = f"sha256:{hashlib.sha256(rfc8785.dumps(canonical)).hexdigest()}"
    if digest != expected or signature.get("signed_digest") != digest:
        raise ArtifactError("signature-rebound")
    _verify_detached(signature, digest, trusted_keys)
    return artifact, digest


def reviewer_key(artifact: Mapping[str, object]) -> ReviewerKey:
    """Return the exact reviewer key tuple carried by a verified artifact."""

    signature = artifact.get("signature")
    if not isinstance(signature, Mapping):
        raise ArtifactError("signature-invalid")
    key_ref = signature.get("key_ref")
    key_version = signature.get("key_version")
    key_digest = signature.get("public_key_digest")
    if (
        not isinstance(key_ref, str)
        or not isinstance(key_version, int)
        or not isinstance(key_digest, str)
    ):
        raise ArtifactError("signature-invalid")
    return key_ref, key_version, key_digest


def _verify_detached(
    signature: Mapping[str, object],
    digest: str,
    trusted_keys: TrustedReviewerKeys,
) -> None:
    key_ref, key_version = signature.get("key_ref"), signature.get("key_version")
    if (
        signature.get("algorithm") != "Ed25519"
        or not isinstance(key_ref, str)
        or not isinstance(key_version, int)
    ):
        raise ArtifactError("signature-invalid")
    public_key = trusted_keys.get((key_ref, key_version))
    if public_key is None:
        raise ArtifactError("review-key-untrusted")
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    public_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    encoded = signature.get("signature")
    if signature.get("public_key_digest") != public_digest or not isinstance(encoded, str):
        raise ArtifactError("review-key-mismatch")
    try:
        public_key.verify(base64.urlsafe_b64decode(encoded + "=="), digest.encode("ascii"))
    except (InvalidSignature, ValueError) as error:
        raise ArtifactError("signature-invalid") from error


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _reject_number(value: str) -> object:
    del value
    raise ValueError("non-integral JSON number")


class ArtifactError(ValueError):
    """Stable internal refusal reason; never crosses the Interface."""
