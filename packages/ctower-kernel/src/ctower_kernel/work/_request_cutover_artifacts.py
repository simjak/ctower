"""Strict canonical and Ed25519 verification for Request cutover artifacts."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid5

import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ctower_kernel.record.artifacts import (
    ArtifactError,
    parse_artifact,
    verify_signed_artifact,
)

__all__ = [
    "artifact_digest_bytes",
    "load_reviewer_key",
    "validate_fence",
    "validate_manifest",
    "validate_manifest_key",
    "verify_request_artifact",
]

_SHA256_TEXT_LENGTH = 71
_MAX_FENCE_AGE_SECONDS = 300
_CUTOVER_NAMESPACE = UUID("4a4fa05a-15ee-55d5-942b-6427217ab3bf")


def load_reviewer_key(pem: str) -> tuple[Ed25519PublicKey, str]:
    """Load one bounded public key and return its immutable digest."""

    if not 1 <= len(pem.encode("utf-8")) <= 16 * 1024:
        raise ArtifactError("review-key-invalid")
    try:
        candidate = serialization.load_pem_public_key(pem.encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise ArtifactError("review-key-invalid") from error
    if not isinstance(candidate, Ed25519PublicKey):
        raise ArtifactError("review-key-invalid")
    raw = candidate.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return candidate, f"sha256:{hashlib.sha256(raw).hexdigest()}"


def verify_request_artifact(
    text: str,
    schema_ref: str,
    digest_field: str,
    public_key: Ed25519PublicKey,
) -> tuple[dict[str, Any], str]:
    """Verify a strict artifact using only the exact key identity it declares."""

    parsed = parse_artifact(text, schema_ref)
    signature = parsed.get("signature")
    if not isinstance(signature, Mapping):
        raise ArtifactError("signature-invalid")
    key_ref, key_version = signature.get("key_ref"), signature.get("key_version")
    if not isinstance(key_ref, str) or not isinstance(key_version, int):
        raise ArtifactError("signature-invalid")
    return verify_signed_artifact(
        text,
        schema_ref,
        digest_field,
        {(key_ref, key_version): public_key},
    )


def artifact_digest_bytes(value: object) -> bytes:
    """Decode one already-validated sha256 value for PostgreSQL storage."""

    text = cast(str, value)
    if not text.startswith("sha256:") or len(text) != _SHA256_TEXT_LENGTH:
        raise ArtifactError("artifact-digest-invalid")
    try:
        return bytes.fromhex(text.removeprefix("sha256:"))
    except ValueError as error:
        raise ArtifactError("artifact-digest-invalid") from error


def validate_manifest(manifest: dict[str, Any], fence: dict[str, Any], *, key_digest: str) -> None:
    """Replay every signed denominator invariant before preparing an epoch."""

    validate_manifest_key(manifest, key_digest)
    rows = cast(list[dict[str, object]], manifest["rows"])
    if not rows:
        raise ValueError("frozen open denominator is empty")
    _validate_row_order(manifest, rows)
    _validate_counts(manifest, rows)
    rows_digest = f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, rows))).hexdigest()}"
    if manifest["rows_digest"] != rows_digest or manifest["sampling_seed"] != rows_digest:
        raise ValueError("manifest row or sampling digest differs")
    if manifest["fence_digest"] != fence["fence_digest"]:
        raise ValueError("manifest is not bound to the freeze proof")
    _validate_identities(rows, cast(str, manifest["ledger_sha256"]))
    _validate_batches(manifest, rows, rows_digest)
    _validate_refinement_graph(rows)


def validate_manifest_key(manifest: Mapping[str, object], key_digest: str) -> None:
    signature = cast(Mapping[str, object], manifest["signature"])
    if signature["public_key_digest"] != key_digest:
        raise ValueError("manifest reviewer key differs")


def validate_fence(
    fence: Mapping[str, object],
    manifest: Mapping[str, object],
    *,
    now: datetime,
    phases: set[str],
) -> None:
    """Require a fresh signed observation of the same immutable source."""

    if fence["phase"] not in phases:
        raise ValueError("fence phase differs from operation")
    if fence["ledger_sha256"] != manifest["ledger_sha256"]:
        raise ValueError("fence ledger digest differs")
    if fence["source_identity"] != manifest["source_identity"]:
        raise ValueError("fence source identity differs")
    observed = datetime.fromisoformat(cast(str, fence["observed_at"]))
    if observed > now or (now - observed).total_seconds() > _MAX_FENCE_AGE_SECONDS:
        raise ValueError("fence observation is stale")
    if not cast(list[object], fence["callers"]):
        raise ValueError("fence caller inventory is empty")


def _validate_row_order(manifest: Mapping[str, object], rows: list[dict[str, object]]) -> None:
    ids = [cast(str, row["id"]) for row in rows]
    if ids != sorted(ids, key=lambda value: int(value[1:])):
        raise ValueError("manifest rows are not in permanent-number order")
    if manifest["open_request_ids"] != ids or len(set(ids)) != len(ids):
        raise ValueError("manifest open set differs from row identities")


def _validate_counts(manifest: Mapping[str, object], rows: list[dict[str, object]]) -> None:
    counts = cast(dict[str, object], manifest["counts"])
    project_counts = _project_count_items(Counter(str(row["project_key"]) for row in rows))
    if counts["open_requests"] != len(rows) or counts["open_by_project"] != project_counts:
        raise ValueError("manifest counts differ from rows")


def _validate_identities(rows: list[dict[str, object]], ledger_digest: str) -> None:
    for row in rows:
        source_id = cast(str, row["id"])
        request_id = uuid5(_CUTOVER_NAMESPACE, f"{ledger_digest}:{source_id}:request")
        command_id = uuid5(_CUTOVER_NAMESPACE, f"{ledger_digest}:{source_id}:import:1")
        if row["request_id"] != str(request_id) or row["command_id"] != str(command_id):
            raise ValueError("manifest deterministic import identity differs")
        if row["request_number"] != int(source_id[1:]):
            raise ValueError("manifest Request number differs from source identity")


def _validate_batches(
    manifest: Mapping[str, object], rows: list[dict[str, object]], seed: str
) -> None:
    batches = cast(list[dict[str, object]], manifest["batches"])
    if len(batches) != (len(rows) + 24) // 25:
        raise ValueError("manifest batch count differs")
    for batch_index, plan in enumerate(batches):
        batch = rows[batch_index * 25 : (batch_index + 1) * 25]
        if plan != _batch_plan(batch, seed, batch_index, len(rows)):
            raise ValueError("manifest batch plan differs")


def _batch_plan(
    batch: list[dict[str, object]], seed: str, batch_index: int, total: int
) -> dict[str, object]:
    ranked = sorted(
        batch,
        key=lambda item: hashlib.sha256(f"{seed}:{batch_index}:{item['id']}".encode()).digest(),
    )
    return {
        "batch_digest": f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, batch))).hexdigest()}",
        "batch_index": batch_index,
        "cumulative_count": min((batch_index + 1) * 25, total),
        "sample_ids": sorted(str(item["id"]) for item in ranked[: min(3, len(ranked))]),
        "source_count": len(batch),
        "source_count_by_project": _project_count_items(
            Counter(str(item["project_key"]) for item in batch)
        ),
    }


def _project_count_items(counts: Mapping[str, int]) -> list[dict[str, object]]:
    return [
        {"project_key": project_key, "count": count}
        for project_key, count in sorted(counts.items())
    ]


def _validate_refinement_graph(rows: list[dict[str, object]]) -> None:
    by_id = {cast(str, row["id"]): row for row in rows}
    graph: dict[str, tuple[str, ...]] = {}
    for row in rows:
        source = cast(str, row["id"])
        targets = tuple(cast(list[str], row["refines"]))
        if source in targets:
            raise ValueError("self refinement is forbidden")
        graph[source] = tuple(
            target
            for target in targets
            if target in by_id and by_id[target]["project_key"] == row["project_key"]
        )
    _validate_acyclic(graph)


def _validate_acyclic(graph: Mapping[str, tuple[str, ...]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("refinement cycle is forbidden")
        if node in visited:
            return
        visiting.add(node)
        for target in graph[node]:
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
