"""RED-first shared estate-import authority and parity vectors."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.estate_imports import (
    EstateImportWorkflow,
    EstateRefusal,
    build_estate_manifest,
    load_seat_mapping,
    parity_report,
    verify_estate_manifest_text,
)

__all__: tuple[str, ...] = ()

_SHA = "sha256:" + "1" * 64


class _Signer:
    def seal(self, value: Mapping[str, Any], digest_field: str) -> dict[str, Any]:
        result = dict(value)
        result[digest_field] = _SHA
        result["signature"] = {
            "algorithm": "Ed25519",
            "signed_digest": _SHA,
            "key_ref": "signing-key-ref:test",
            "key_version": 1,
            "public_key_digest": _SHA,
            "signature": "A" * 86 + "==",
        }
        return result


def test_manifest_builder_refuses_an_empty_source() -> None:
    with pytest.raises(EstateRefusal) as raised:
        build_estate_manifest(
            tier="company_records",
            source_identity={
                "namespace": "mission-control:estate",
                "source_path": "state/escapes.jsonl",
                "source_sha256": _SHA,
            },
            rows=[],
            seat_mapping_digest=None,
            signer=_Signer(),
        )

    assert raised.value.code == "source-empty"


def test_seat_mapping_digest_is_verified_before_rows_are_accepted(tmp_path: Path) -> None:
    mapping = {
        "schema": "ctower.estate-seat-mapping/v1",
        "mapping_digest": _SHA,
        "mappings": [
            {"source_seat": "engineer", "disposition": "mapped", "target_seat_key": "engineer"}
        ],
    }
    unsigned = dict(mapping)
    unsigned.pop("mapping_digest", None)
    mapping["mapping_digest"] = "sha256:" + hashlib.sha256(
        rfc8785.dumps(cast(Any, unsigned))
    ).hexdigest()
    path = tmp_path / "seat-map.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    loaded = load_seat_mapping(path)
    assert loaded["engineer"].target_seat_key == "engineer"

    mapping["mapping_digest"] = "sha256:" + "2" * 64
    path.write_text(json.dumps(mapping), encoding="utf-8")
    with pytest.raises(EstateRefusal) as raised:
        load_seat_mapping(path)
    assert raised.value.code == "seat-mapping-digest-mismatch"


def test_manifest_verification_rejects_a_batch_count_mismatch() -> None:
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:test", 1, private_key)
    manifest = signer.seal(
        {
            "schema": "ctower.estate-import-manifest/v1",
            "tier": "company_records",
            "source_identity": {
                "namespace": "mission-control:estate",
                "source_path": "state/escapes.jsonl",
                "source_sha256": _SHA,
            },
            "counts": {"source_rows": 1},
            "batches": [{"batch_index": 0, "batch_digest": _SHA, "source_count": 2}],
        },
        "manifest_digest",
    )

    with pytest.raises(EstateRefusal) as raised:
        verify_estate_manifest_text(
            rfc8785.dumps(manifest).decode("utf-8"),
            tier="company_records",
            source_row_count=1,
            public_key=private_key.public_key(),
        )
    assert raised.value.code == "manifest-count-mismatch"


def test_parity_report_rejects_more_imports_than_source_rows() -> None:
    manifest = {
        "manifest_digest": _SHA,
        "batches": [{"batch_index": 0, "batch_digest": _SHA, "source_count": 1}],
    }

    with pytest.raises(EstateRefusal) as raised:
        parity_report(
            tier="company_records",
            manifest=manifest,
            source_count=1,
            imported_count=2,
            batch_imports=[(0, 2)],
            sampled=[("state/escapes.jsonl#1", _SHA)],
            source_only_owners=[],
            signer=_Signer(),
        )
    assert raised.value.code == "parity-count-mismatch"


def test_workflow_refuses_non_operator_before_import_or_closure() -> None:
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:test", 1, private_key)
    rows = _workflow_rows()
    manifest = _workflow_manifest(signer, rows)
    observed: list[str] = []

    with pytest.raises(EstateRefusal) as raised:
        EstateImportWorkflow(private_key.public_key()).execute(
            actor_kind="commander",
            tier="company_records",
            manifest_text=rfc8785.dumps(manifest).decode(),
            rows=rows,
            batch_importer=lambda _index, _rows: observed.append("import") or 1,
            emit_report=lambda _report: observed.append("report"),
            close_source=lambda: observed.append("close"),
            signer=signer,
        )

    assert raised.value.code == "operator-required"
    assert observed == []


def test_workflow_emits_parity_before_source_closure() -> None:
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:test", 1, private_key)
    rows = _workflow_rows()
    manifest = _workflow_manifest(signer, rows)
    observed: list[str] = []

    report = EstateImportWorkflow(private_key.public_key()).execute(
        actor_kind="operator",
        tier="company_records",
        manifest_text=rfc8785.dumps(manifest).decode(),
        rows=rows,
        batch_importer=lambda _index, _rows: 1,
        emit_report=lambda _report: observed.append("report"),
        close_source=lambda: observed.append("close"),
        signer=signer,
    )

    assert report["emitted_before_closure"] is True
    assert report["source_count"] == report["imported_count"] == 1
    assert observed == ["report", "close"]


def _workflow_rows() -> list[dict[str, Any]]:
    return [
        {
            "_disposition": "source_only",
            "source_seat": "unknown-owner",
            "source_ref": "state/escapes.jsonl#1",
            "content_sha256": _SHA,
        }
    ]


def _workflow_manifest(signer: ArtifactSigner, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return signer.seal(
        build_estate_manifest(
            tier="company_records",
            source_identity={
                "namespace": "mission-control:estate",
                "source_path": "state/escapes.jsonl",
                "source_sha256": _SHA,
            },
            rows=rows,
            seat_mapping_digest=None,
            signer=None,
        ),
        "manifest_digest",
    )
