"""Compatibility facade for the generic kernel object port."""

from ctower_kernel.objects import (
    ObjectIntegrityError,
    StoredObject,
    digest_bytes,
    verify_digest,
)
from ctower_kernel.objects import (
    ObjectStore as ProofObjectStore,
)

__all__ = [
    "ObjectIntegrityError",
    "ProofObjectStore",
    "StoredObject",
    "digest_bytes",
    "verify_digest",
]
