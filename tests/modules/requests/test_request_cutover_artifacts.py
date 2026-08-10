"""Fail-closed Request cutover artifact validation."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid5

import pytest
import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ctower_kernel.record.artifacts import ArtifactError
from ctower_kernel.work import _request_cutover_artifacts as artifacts

__all__: tuple[str, ...] = ()

_NAMESPACE = UUID("4a4fa05a-15ee-55d5-942b-6427217ab3bf")
_NOW = datetime(2026, 8, 10, tzinfo=UTC)
_DIGEST = "sha256:" + "1" * 64


def test_reviewer_key_and_digest_boundaries_refuse_wrong_shapes() -> None:
    private = Ed25519PrivateKey.generate()
    pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    public, digest = artifacts.load_reviewer_key(pem)
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert digest == f"sha256:{hashlib.sha256(raw).hexdigest()}"
    assert artifacts.artifact_digest_bytes("sha256:" + "ab" * 32) == bytes.fromhex("ab" * 32)

    with pytest.raises(ArtifactError, match="review-key-invalid"):
        artifacts.load_reviewer_key("")
    with pytest.raises(ArtifactError, match="review-key-invalid"):
        artifacts.load_reviewer_key("not a PEM")
    rsa_pem = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    with pytest.raises(ArtifactError, match="review-key-invalid"):
        artifacts.load_reviewer_key(rsa_pem)
    for value in ("sha256:short", "sha256:" + "gg" * 32):
        with pytest.raises(ArtifactError, match="artifact-digest-invalid"):
            artifacts.artifact_digest_bytes(value)


def test_artifact_signature_envelope_is_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    public = Ed25519PrivateKey.generate().public_key()
    monkeypatch.setattr(artifacts, "parse_artifact", lambda *_args: {})
    with pytest.raises(ArtifactError, match="signature-invalid"):
        artifacts.verify_request_artifact("{}", "schema", "digest", public)
    monkeypatch.setattr(artifacts, "parse_artifact", lambda *_args: {"signature": {}})
    with pytest.raises(ArtifactError, match="signature-invalid"):
        artifacts.verify_request_artifact("{}", "schema", "digest", public)
    monkeypatch.setattr(
        artifacts,
        "parse_artifact",
        lambda *_args: {"signature": {"key_ref": "reviewer", "key_version": 1}},
    )
    monkeypatch.setattr(
        artifacts,
        "verify_signed_artifact",
        lambda *_args: ({"verified": True}, _DIGEST),
    )
    assert artifacts.verify_request_artifact("{}", "schema", "digest", public) == (
        {"verified": True},
        _DIGEST,
    )


def test_manifest_replays_denominator_batches_and_identity() -> None:
    manifest, fence, key_digest = _manifest()
    artifacts.validate_manifest(manifest, fence, key_digest=key_digest)

    mutations: tuple[tuple[str, Any], ...] = (
        ("key", lambda value: value["signature"].update(public_key_digest="sha256:" + "9" * 64)),
        ("empty", lambda value: value.update(rows=[])),
        ("order", lambda value: value.update(open_request_ids=[])),
        ("counts", lambda value: cast(dict[str, object], value["counts"]).update(open_requests=2)),
        ("rows-digest", lambda value: value.update(rows_digest="sha256:" + "8" * 64)),
        ("fence", lambda value: value.update(fence_digest="sha256:" + "7" * 64)),
        ("identity", lambda value: value["rows"][0].update(request_id=str(UUID(int=0)))),
        ("number", lambda value: value["rows"][0].update(request_number=2)),
        ("batch-count", lambda value: value.update(batches=[])),
        ("batch-plan", lambda value: value["batches"][0].update(source_count=2)),
        ("self-refinement", lambda value: value["rows"][0].update(refines=["R1"])),
    )
    for _name, mutate in mutations:
        candidate = deepcopy(manifest)
        mutate(candidate)
        with pytest.raises(ValueError):
            artifacts.validate_manifest(candidate, fence, key_digest=key_digest)


def test_manifest_refinement_cycle_and_fence_freshness_refuse() -> None:
    manifest, fence, key_digest = _manifest(two_rows=True)
    cast(list[dict[str, object]], manifest["rows"])[0]["refines"] = ["R2"]
    cast(list[dict[str, object]], manifest["rows"])[1]["refines"] = ["R1"]
    _rebind_rows(manifest)
    with pytest.raises(ValueError, match="cycle"):
        artifacts.validate_manifest(manifest, fence, key_digest=key_digest)

    one, one_fence, _key_digest = _manifest()
    artifacts.validate_fence(one_fence, one, now=_NOW, phases={"freeze"})
    variants = (
        {**one_fence, "phase": "final"},
        {**one_fence, "ledger_sha256": "sha256:" + "4" * 64},
        {**one_fence, "source_identity": {"size": 2}},
        {**one_fence, "observed_at": (_NOW + timedelta(seconds=1)).isoformat()},
        {**one_fence, "observed_at": (_NOW - timedelta(seconds=301)).isoformat()},
        {**one_fence, "callers": []},
    )
    for candidate in variants:
        with pytest.raises(ValueError):
            artifacts.validate_fence(candidate, one, now=_NOW, phases={"freeze"})

    ordered, _fence_value, _key = _manifest(two_rows=True)
    rows = cast(list[dict[str, object]], ordered["rows"])
    with pytest.raises(ValueError, match="permanent-number order"):
        artifacts._validate_row_order(ordered, list(reversed(rows)))
    with pytest.raises(ValueError, match="Request number"):
        artifacts._validate_identities(
            [{**rows[0], "request_number": 9}], cast(str, ordered["ledger_sha256"])
        )
    artifacts._validate_acyclic({"R1": ("R3",), "R2": ("R3",), "R3": ()})


def _manifest(*, two_rows: bool = False) -> tuple[dict[str, Any], dict[str, Any], str]:
    ledger = "sha256:" + "1" * 64
    rows = [_row(ledger, 1)]
    if two_rows:
        rows.append(_row(ledger, 2))
    rows_digest = _digest(rows)
    key_digest = "sha256:" + "2" * 64
    fence_digest = "sha256:" + "3" * 64
    manifest: dict[str, Any] = {
        "batches": [artifacts._batch_plan(rows, rows_digest, 0, len(rows))],
        "counts": {
            "open_requests": len(rows),
            "open_by_project": [{"project_key": "ctower", "count": len(rows)}],
        },
        "fence_digest": fence_digest,
        "ledger_sha256": ledger,
        "open_request_ids": [cast(str, row["id"]) for row in rows],
        "rows": rows,
        "rows_digest": rows_digest,
        "sampling_seed": rows_digest,
        "signature": {"public_key_digest": key_digest},
        "source_identity": {"size": 1},
    }
    fence = {
        "callers": [{"path": "requests.py"}],
        "fence_digest": fence_digest,
        "ledger_sha256": ledger,
        "observed_at": _NOW.isoformat(),
        "phase": "freeze",
        "source_identity": {"size": 1},
    }
    return manifest, fence, key_digest


def _row(ledger: str, number: int) -> dict[str, object]:
    source_id = f"R{number}"
    return {
        "command_id": str(uuid5(_NAMESPACE, f"{ledger}:{source_id}:import:1")),
        "id": source_id,
        "project_key": "ctower",
        "refines": [],
        "request_id": str(uuid5(_NAMESPACE, f"{ledger}:{source_id}:request")),
        "request_number": number,
    }


def _rebind_rows(manifest: dict[str, Any]) -> None:
    rows = cast(list[dict[str, object]], manifest["rows"])
    digest = _digest(rows)
    manifest["rows_digest"] = digest
    manifest["sampling_seed"] = digest
    manifest["batches"] = [artifacts._batch_plan(rows, digest, 0, len(rows))]


def _digest(value: object) -> str:
    return f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, value))).hexdigest()}"
