"""Public Interface for deterministic generated-artifact ownership."""

from tools.checks._impl.generated import (
    GeneratedArtifact,
    GeneratedManifestError,
    atomic_write_generated_text,
    digest_bytes,
    digest_file,
    load_generated_manifest,
    render_generated_manifest,
)

__all__ = [
    "GeneratedArtifact",
    "GeneratedManifestError",
    "atomic_write_generated_text",
    "digest_bytes",
    "digest_file",
    "load_generated_manifest",
    "render_generated_manifest",
]
