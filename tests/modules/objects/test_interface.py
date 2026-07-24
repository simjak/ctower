from __future__ import annotations

import pytest

from ctower_kernel.objects import (
    ObjectIntegrityError,
    ObjectStore,
    StoredObject,
    digest_bytes,
    verify_digest,
)
from ctower_kernel.proof.objects import (
    ObjectIntegrityError as ProofObjectIntegrityError,
)
from ctower_kernel.proof.objects import ProofObjectStore
from ctower_kernel.proof.objects import StoredObject as ProofStoredObject


def test_proof_object_surface_is_an_identity_preserving_facade() -> None:
    assert ProofObjectStore is ObjectStore
    assert ProofStoredObject is StoredObject
    assert ProofObjectIntegrityError is ObjectIntegrityError


def test_generic_digest_boundary_fails_closed() -> None:
    content = b"shared object boundary"
    digest = digest_bytes(content)

    verify_digest(content, digest)
    with pytest.raises(ObjectIntegrityError, match="digest mismatch"):
        verify_digest(content + b"!", digest)
