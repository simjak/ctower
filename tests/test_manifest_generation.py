"""RED-phase test: verify Request manifest generation matches the import contract.

This test is RED-first: it exercises the public generate_manifest() function
before the tool ships, proving the contract is testable independently of the
CLI. It reads a tiny JSONL fixture, produces a signed manifest, and validates
every property the schema and the migration boundary demand.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from ctower_contracts import validator_for

from tools.migration.ctower_project.ctower_project_source.refusal import (
    MigrationRefusalError,
)
from tools.migration.ctower_project.ctower_project_source.signing import (
    ArtifactSigner,
    ArtifactVerifier,
)
from tools.migration.operator_requests.generate_manifest import generate_manifest

__all__: tuple[str, ...] = ()

_CUTOVER_NAMESPACE = "4a4fa05a-15ee-55d5-942b-6427217ab3bf"
_ROW_COUNT = 4
_BATCH_SIZE = 25


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def jsonl_fixture(temp_dir: Path) -> Path:
    """Write a small test JSONL ledger with 4 requests across 2 projects.

    Each line is a separate version; R4 is updated to exercise the
    "latest version wins" rule.
    """
    rows = [
        # R1 — simplest NEW request
        {
            "id": "R1",
            "text": "Fix login timeout",
            "status": "NEW",
            "project": "ctower",
            "owner": "alice",
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-02T00:00:00Z",
            "refines": [],
            "relationships": [],
        },
        # R2 — TRIAGED request with priority review implied
        {
            "id": "R2",
            "text": "Add export feature",
            "status": "TRIAGED",
            "project": "ctower",
            "owner": "bob",
            "created": "2026-01-03T00:00:00Z",
            "updated": "2026-01-04T00:00:00Z",
            "refines": [],
            "relationships": [],
        },
        # R3 — WIP request in a different project
        {
            "id": "R3",
            "text": "Write docs for API v2",
            "status": "WIP",
            "project": "docs",
            "owner": "charlie",
            "created": "2026-01-05T00:00:00Z",
            "updated": "2026-01-06T00:00:00Z",
            "refines": [],
            "relationships": [],
        },
        # R4 — BLOCKED; later updated to verify latest-only capture
        {
            "id": "R4",
            "text": "Old: investigate perf regression",
            "status": "NEW",
            "project": "ctower",
            "owner": "dave",
            "created": "2026-01-07T00:00:00Z",
            "updated": "2026-01-08T00:00:00Z",
            "refines": [],
            "relationships": [],
        },
        # R4 — updated version (latest should win)
        {
            "id": "R4",
            "text": "Fix performance regression",
            "status": "BLOCKED",
            "project": "ctower",
            "owner": "dave",
            "created": "2026-01-07T00:00:00Z",
            "updated": "2026-01-09T00:00:00Z",
            "refines": ["R1"],
            "relationships": [{"kind": "refines", "target": "R1", "note": "blocked on R1"}],
        },
    ]
    path = temp_dir / "requests.jsonl"
    lines = "\n".join(json.dumps(row, sort_keys=True) for row in rows)
    path.write_text(lines + "\n", encoding="utf-8")
    return path


@pytest.fixture
def jsonl_bytes(jsonl_fixture: Path) -> bytes:
    return jsonl_fixture.read_bytes()


@pytest.fixture
def ledger_digest(jsonl_bytes: bytes) -> str:
    return f"sha256:{hashlib.sha256(jsonl_bytes).hexdigest()}"


@pytest.fixture
def ed25519_key_pair(temp_dir: Path) -> tuple[Ed25519PrivateKey, Path, Path]:
    """Generate an Ed25519 key, write PEM+map, and return (private, key_path, map_path)."""
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = temp_dir / "signing-ed25519.pem"
    key_path.write_bytes(pem)
    key_path.chmod(0o600)
    key_ref = "signing-key-ref:test-manifest"
    key_map = {key_ref: str(key_path)}
    map_path = temp_dir / "signing-map.json"
    map_path.write_text(json.dumps(key_map, sort_keys=True))
    map_path.chmod(0o600)
    return private, key_path, map_path


@pytest.fixture
def signer(
    ed25519_key_pair: tuple[Ed25519PrivateKey, Path, Path], temp_dir: Path
) -> ArtifactSigner:
    _, _, map_path = ed25519_key_pair
    return ArtifactSigner.from_reference_map(
        map_path, "signing-key-ref:test-manifest", key_version=1
    )


@pytest.fixture
def verifier(ed25519_key_pair: tuple[Ed25519PrivateKey, Path, Path]) -> ArtifactVerifier:
    private, _, _ = ed25519_key_pair
    return ArtifactVerifier(private.public_key())


# ---------------------------------------------------------------------------
# RED — fail closed on bad inputs
# ---------------------------------------------------------------------------


def test_generate_refuses_missing_ledger(
    temp_dir: Path, ed25519_key_pair: tuple[Ed25519PrivateKey, Path, Path]
) -> None:
    """RED: a missing input file raises FileNotFoundError or ValueError."""
    missing = temp_dir / "no-such-file.jsonl"
    with pytest.raises((FileNotFoundError, ValueError, OSError)):
        _, _, map_path = ed25519_key_pair
        signer = ArtifactSigner.from_reference_map(
            map_path, "signing-key-ref:test-manifest", key_version=1
        )
        generate_manifest(missing, signer=signer)


def test_generate_refuses_bad_jsonl(temp_dir: Path) -> None:
    """RED: malformed JSONL raises ValueError."""
    bad = temp_dir / "bad.jsonl"
    bad.write_text("not valid json\n", encoding="utf-8")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        generate_manifest(bad)


# ---------------------------------------------------------------------------
# GREEN — manifest shape and content
# ---------------------------------------------------------------------------


def test_manifest_matches_schema(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
) -> None:
    """The generated sealed manifest validates against the published schema."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    validator_for("ctower.request-import-manifest/v1").validate(manifest)


def test_manifest_row_counts(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
    jsonl_bytes: bytes,
) -> None:
    """Physical and logical row counts match the input ledger."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    counts = cast(dict[str, object], manifest["counts"])

    # 5 physical lines (R4 has 2 versions)
    assert counts["physical_rows"] == 5

    # 4 unique R-ids
    assert counts["logical_requests"] == _ROW_COUNT

    # all 4 latest rows are open (no DONE/SUPERSEDED/MERGED/WONT-DO)
    assert counts["open_requests"] == _ROW_COUNT

    # project breakdown: ctower=3 (R1,R2,R4), docs=1 (R3)
    by_project = cast(list[dict[str, object]], counts["open_by_project"])
    assert {"project_key": "ctower", "count": 3} in by_project
    assert {"project_key": "docs", "count": 1} in by_project

    # open_request_ids matches sorted row IDs
    assert manifest["open_request_ids"] == ["R1", "R2", "R3", "R4"]


def test_manifest_maximum_request_number(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
) -> None:
    """The maximum R number is derived from the full ledger, not just open rows."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    assert manifest["maximum_request_number"] == 4


def test_manifest_batch_structure(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
) -> None:
    """Batches respect the 25-row limit and carry correct metadata."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    batches = cast(list[dict[str, object]], manifest["batches"])

    # 4 rows → one batch
    assert len(batches) == 1

    batch = batches[0]
    assert batch["batch_index"] == 0
    assert batch["source_count"] == _ROW_COUNT
    assert batch["cumulative_count"] == _ROW_COUNT

    # sample_ids: up to 3 deterministic samples
    samples = cast(list[str], batch["sample_ids"])
    assert 1 <= len(samples) <= min(3, _ROW_COUNT)
    for sample in samples:
        assert sample.startswith("R")

    # project count in batch matches rows
    by_project = cast(list[dict[str, object]], batch["source_count_by_project"])
    assert {"project_key": "ctower", "count": 3} in by_project
    assert {"project_key": "docs", "count": 1} in by_project

    # batch_digest is a valid sha256
    assert batch["batch_digest"].startswith("sha256:")
    assert len(batch["batch_digest"]) == 71


def test_manifest_content_digests(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
    jsonl_bytes: bytes,
    ledger_digest: str,
) -> None:
    """Row-level content digests and the overall rows_digest are correct."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    rows = cast(list[dict[str, object]], manifest["rows"])
    assert len(rows) == _ROW_COUNT

    # rows_digest = sha256 of canonical rows array
    expected_rows_digest = f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, rows))).hexdigest()}"
    assert manifest["rows_digest"] == expected_rows_digest

    # sampling_seed equals rows_digest
    assert manifest["sampling_seed"] == manifest["rows_digest"]

    # ledger_sha256 matches the file bytes
    assert manifest["ledger_sha256"] == ledger_digest

    # Verify per-row content digests
    # R4 should have the BLOCKED status (latest wins)
    r4 = next(row for row in rows if cast(str, row["id"]) == "R4")
    assert r4["source_status"] == "BLOCKED"
    expected_text_digest = f"sha256:{hashlib.sha256(b'Fix performance regression').hexdigest()}"
    assert r4["content_sha256"] == expected_text_digest


def test_manifest_deterministic_identities(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
    ledger_digest: str,
) -> None:
    """request_id and command_id are deterministic uuid5 values.

    Run twice and confirm identity equality.
    """
    manifest_a = generate_manifest(jsonl_fixture, signer=signer)
    manifest_b = generate_manifest(jsonl_fixture, signer=signer)

    rows_a = cast(list[dict[str, object]], manifest_a["rows"])
    rows_b = cast(list[dict[str, object]], manifest_b["rows"])

    for ra, rb in zip(rows_a, rows_b, strict=True):
        assert ra["id"] == rb["id"]
        assert ra["request_id"] == rb["request_id"]
        assert ra["command_id"] == rb["command_id"]
        assert ra["content_sha256"] == rb["content_sha256"]


def test_manifest_source_identity(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
) -> None:
    """Source identity is present and carries stat metadata."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    ident = cast(dict[str, object], manifest["source_identity"])
    assert isinstance(ident["device"], int) and ident["device"] >= 0
    assert isinstance(ident["inode"], int) and ident["inode"] >= 1
    assert isinstance(ident["mode"], int)
    assert isinstance(ident["mtime_ns"], str) and ident["mtime_ns"].isdigit()
    assert isinstance(ident["size"], int) and ident["size"] > 0


def test_manifest_schema_constant_fields(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
) -> None:
    """Const-marker fields carry their required literal values."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    assert manifest["schema"] == "ctower.request-import-manifest/v1"
    assert manifest["batch_size"] == _BATCH_SIZE


# ---------------------------------------------------------------------------
# GREEN — signature verification
# ---------------------------------------------------------------------------


def test_manifest_signature_is_valid(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
    verifier: ArtifactVerifier,
) -> None:
    """The signed manifest carries a valid Ed25519 detached signature.

    This test re-verifies the same way the operator tool does:
    extract digest, check the signature payload, verify the raw
    sig against the digest bytes.
    """
    manifest = generate_manifest(jsonl_fixture, signer=signer)

    # The verifier should accept the manifest
    digest = verifier.verify(manifest, "manifest_digest")
    assert digest.startswith("sha256:")
    assert len(digest) == 71

    # Ensure the digest in the manifest_digest field is correct
    assert manifest["manifest_digest"] == digest

    # The signature block has the correct algorithm and key identity
    sig = cast(dict[str, object], manifest["signature"])
    assert sig["algorithm"] == "Ed25519"
    assert sig["signed_digest"] == digest
    assert sig["public_key_digest"] == verifier.public_key_digest


def test_manifest_signature_tamper_detection(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
    verifier: ArtifactVerifier,
) -> None:
    """Any field change invalidates the signature."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)

    # Mutate a row's content
    rows = cast(list[dict[str, object]], manifest["rows"])
    rows[0]["content_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(MigrationRefusalError):
        verifier.verify(manifest, "manifest_digest")


def test_manifest_archive_ref(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
    ledger_digest: str,
) -> None:
    """archive_ref embeds the ledger digest in restricted-archive form."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    expected = f"restricted-archive:{ledger_digest.removeprefix('sha256:')}"
    assert manifest["archive_ref"] == expected


# ---------------------------------------------------------------------------
# GREEN — round-trip with the operator manifest consumer API
# ---------------------------------------------------------------------------


def test_manifest_batch_matches_recomputation(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
) -> None:
    """Each batch digest matches a fresh recomputation."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    rows = cast(list[dict[str, object]], manifest["rows"])
    batches = cast(list[dict[str, object]], manifest["batches"])

    for batch in batches:
        index = cast(int, batch["batch_index"])
        start = index * _BATCH_SIZE
        batch_rows = rows[start : start + _BATCH_SIZE]
        recomputed_digest = (
            f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, batch_rows))).hexdigest()}"
        )
        assert batch["batch_digest"] == recomputed_digest


def test_manifest_empty_jsonl_refused(temp_dir: Path, signer: ArtifactSigner) -> None:
    """An empty or blank-only JSONL file raises ValueError (no requests)."""
    empty = temp_dir / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match=r".*no.*rows.*|.*empty.*"):
        generate_manifest(empty, signer=signer)


def test_manifest_batch_cumulative_count(
    jsonl_fixture: Path,
    signer: ArtifactSigner,
) -> None:
    """cumulative_count equals the total rows when all rows fit in one batch."""
    manifest = generate_manifest(jsonl_fixture, signer=signer)
    batches = cast(list[dict[str, object]], manifest["batches"])
    total = sum(cast(int, b["source_count"]) for b in batches)
    assert batches[-1]["cumulative_count"] == total
    assert total == _ROW_COUNT
