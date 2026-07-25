from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.migration.ctower_project.ctower_project_source.canonical import canonical_bytes
from tools.migration.ctower_project.ctower_project_source.refusal import (
    MigrationRefusal,
    RefusalCode,
)
from tools.migration.ctower_project.ctower_project_source.signing import (
    ArtifactSigner,
    ArtifactVerifier,
)

__all__: tuple[str, ...] = ()

KEY_REF = "signing-key-ref:test/reviewer"


def test_private_material_is_loaded_only_through_protected_reference_map(
    tmp_path: Path,
) -> None:
    private = Ed25519PrivateKey.generate()
    key_path = tmp_path / "reviewer-private.pem"
    private_bytes = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    key_path.write_bytes(private_bytes)
    key_path.chmod(0o600)
    map_path = tmp_path / "key-map.json"
    map_path.write_bytes(canonical_bytes({KEY_REF: str(key_path)}))
    map_path.chmod(0o600)
    signer = ArtifactSigner.from_reference_map(map_path, KEY_REF, key_version=1)
    sealed = signer.seal({"schema": "synthetic/v1", "value": 1}, "artifact_digest")
    verifier = ArtifactVerifier(private.public_key())
    assert verifier.verify(sealed, "artifact_digest") == sealed["artifact_digest"]
    assert private_bytes not in canonical_bytes(sealed)


def test_unprotected_or_unknown_private_reference_refuses(tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    key_path = tmp_path / "reviewer-private.pem"
    key_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o644)
    map_path = tmp_path / "key-map.json"
    map_path.write_bytes(canonical_bytes({KEY_REF: str(key_path)}))
    map_path.chmod(0o600)
    with pytest.raises(MigrationRefusal) as caught:
        ArtifactSigner.from_reference_map(map_path, KEY_REF, key_version=1)
    assert caught.value.code == RefusalCode.KEY_FILE_INSECURE
    with pytest.raises(MigrationRefusal) as caught:
        ArtifactSigner.from_reference_map(
            map_path,
            "signing-key-ref:test/missing",
            key_version=1,
        )
    assert caught.value.code == RefusalCode.KEY_REFERENCE_UNKNOWN
