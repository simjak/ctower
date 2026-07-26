"""Strict accepting-boundary tests for reviewed artifact bytes and keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctower_kernel.migration import _artifact
from tools.migration.ctower_project.ctower_project_source.canonical import canonical_bytes

from ._reviewed import reviewed_source
from .source_tool.fixtures import CUTOVER_ID

__all__: tuple[str, ...] = ()


def test_artifact_parser_refuses_noncanonical_duplicate_and_fractional_json(
    tmp_path: Path,
) -> None:
    source = reviewed_source(tmp_path, CUTOVER_ID)
    schema = "ctower.ctower-project-source-selection/v1"
    for text in (
        " " + canonical_bytes(source.fixture.selection).decode(),
        '{"schema":"x","schema":"y"}',
        '{"value":1.5}',
        "[]",
        "{}",
    ):
        with pytest.raises(_artifact.ArtifactError):
            _artifact.parse_artifact(text, schema)


def test_signed_artifact_refuses_rebound_untrusted_mismatched_and_invalid_keys(
    tmp_path: Path,
) -> None:
    source = reviewed_source(tmp_path, CUTOVER_ID)
    text = canonical_bytes(source.fixture.selection).decode()
    artifact, digest = _artifact.verify_signed_artifact(
        text,
        "ctower.ctower-project-source-selection/v1",
        "manifest_digest",
        source.trusted_keys,
    )
    signature = artifact["signature"]
    assert digest == source.fixture.selection["manifest_digest"]

    rebound = {
        **artifact,
        "signature": {**signature, "signed_digest": f"sha256:{'0' * 64}"},
    }
    with pytest.raises(_artifact.ArtifactError, match="signature-rebound"):
        _artifact.verify_signed_artifact(
            canonical_bytes(rebound).decode(),
            "ctower.ctower-project-source-selection/v1",
            "manifest_digest",
            source.trusted_keys,
        )
    with pytest.raises(_artifact.ArtifactError, match="signature-invalid"):
        _artifact._verify_detached({**signature, "algorithm": "RSA"}, digest, source.trusted_keys)
    with pytest.raises(_artifact.ArtifactError, match="review-key-untrusted"):
        _artifact._verify_detached(signature, digest, {})
    with pytest.raises(_artifact.ArtifactError, match="review-key-mismatch"):
        _artifact._verify_detached(
            {**signature, "public_key_digest": f"sha256:{'0' * 64}"},
            digest,
            source.trusted_keys,
        )
    with pytest.raises(_artifact.ArtifactError, match="signature-invalid"):
        _artifact._verify_detached(
            {**signature, "signature": "A"},
            digest,
            source.trusted_keys,
        )


def test_unsigned_artifact_cannot_enter_signed_verifier(tmp_path: Path) -> None:
    source = reviewed_source(tmp_path, CUTOVER_ID)
    with pytest.raises(_artifact.ArtifactError, match="signature-invalid"):
        _artifact.verify_signed_artifact(
            canonical_bytes(source.first.manifest).decode(),
            "ctower.ctower-project-export-manifest/v1",
            "report_digest",
            source.trusted_keys,
        )
