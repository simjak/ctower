"""Operator-visible transport for the signed, one-way Request authority epoch."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

import httpx
import rfc8785

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner

__all__ = ["complete_reconciled_import", "execute_reconciled_import"]

_COMMAND_NAMESPACE = UUID("f03ff5f7-d114-5cff-8433-441da0c8364a")
_MAX_ACCEPTANCE_POLLS = 120


def execute_reconciled_import(
    client: httpx.Client,
    *,
    ledger_path: Path,
    manifest_path: Path,
    fence_path: Path,
    evidence_dir: Path,
    signer: ArtifactSigner,
    reviewer_public_key_pem: str,
) -> dict[str, object]:
    """Prepare, import, publicly sample, and persist every signed batch proof."""

    manifest = _signed_artifact(manifest_path, signer, "manifest_digest")
    manifest_digest = cast(str, manifest["manifest_digest"])
    _recheck_source(ledger_path, manifest)
    freeze_text = _artifact_text(_signed_artifact(fence_path, signer, "fence_digest"))
    prepare_id = uuid5(_COMMAND_NAMESPACE, f"{manifest_digest}:prepare")
    _post_accepted(
        client,
        "/_internal/request-cutover/prepare",
        prepare_id,
        {
            "manifest": _artifact_text(manifest),
            "fence": freeze_text,
            "reviewer_public_key_pem": reviewer_public_key_pem,
        },
    )
    source_text = _latest_source_text(ledger_path)
    imported = 0
    batches = cast(list[dict[str, object]], manifest["batches"])
    rows = cast(list[dict[str, object]], manifest["rows"])
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    for batch in batches:
        imported += _execute_batch(
            client,
            ledger_path=ledger_path,
            manifest=manifest,
            manifest_digest=manifest_digest,
            fence_path=fence_path,
            evidence_dir=evidence_dir,
            signer=signer,
            reviewer_public_key_pem=reviewer_public_key_pem,
            source_text=source_text,
            rows=rows,
            batch=batch,
        )
    return {
        "schema": "ctower.request-cutover-transcript/v1",
        "phase": "reconciled",
        "manifest_digest": manifest_digest,
        "source_count": len(rows),
        "imported_count": imported,
        "batch_count": len(batches),
        "writes_attempted": imported + len(batches) + 1,
    }


def _execute_batch(
    client: httpx.Client,
    *,
    ledger_path: Path,
    manifest: Mapping[str, object],
    manifest_digest: str,
    fence_path: Path,
    evidence_dir: Path,
    signer: ArtifactSigner,
    reviewer_public_key_pem: str,
    source_text: Mapping[str, str],
    rows: list[dict[str, object]],
    batch: Mapping[str, object],
) -> int:
    batch_index = cast(int, batch["batch_index"])
    start = batch_index * 25
    current = rows[start : start + cast(int, batch["source_count"])]
    for row in current:
        _import_row(
            client,
            ledger_path,
            manifest,
            manifest_digest,
            fence_path,
            signer,
            reviewer_public_key_pem,
            source_text,
            row,
        )
    reconciliation = _get_json(
        client,
        f"/_internal/request-cutover/reconcile/{manifest_digest}/{batch_index}",
    )
    proof = _seal_proof(signer, reconciliation, _public_samples(client, reconciliation))
    proof_path = evidence_dir / f"request-batch-{batch_index:04d}.proof.json"
    proof_path.write_text(_artifact_text(proof), encoding="utf-8")
    proof_id = uuid5(_COMMAND_NAMESPACE, f"{manifest_digest}:proof:{batch_index}")
    _post_accepted(
        client,
        "/_internal/request-cutover/batch-proofs",
        proof_id,
        {"proof": _artifact_text(proof), "reviewer_public_key_pem": reviewer_public_key_pem},
    )
    return len(current)


def _import_row(
    client: httpx.Client,
    ledger_path: Path,
    manifest: Mapping[str, object],
    manifest_digest: str,
    fence_path: Path,
    signer: ArtifactSigner,
    reviewer_public_key_pem: str,
    source_text: Mapping[str, str],
    row: Mapping[str, object],
) -> None:
    _recheck_source(ledger_path, manifest)
    fence = _artifact_text(_signed_artifact(fence_path, signer, "fence_digest"))
    source_id = cast(str, row["id"])
    content = source_text[source_id]
    _require_digest(content.encode(), cast(str, row["content_sha256"]))
    _post_accepted(
        client,
        "/_internal/request-cutover/rows",
        UUID(cast(str, row["command_id"])),
        {
            "manifest_digest": manifest_digest,
            "source_request_id": source_id,
            "content": content,
            "fence": fence,
            "reviewer_public_key_pem": reviewer_public_key_pem,
        },
    )


def complete_reconciled_import(
    client: httpx.Client,
    *,
    manifest_path: Path,
    final_fence_path: Path,
    signer: ArtifactSigner,
    reviewer_public_key_pem: str,
) -> dict[str, object]:
    """Complete only after the separately observed final removal fence exists."""

    manifest = _signed_artifact(manifest_path, signer, "manifest_digest")
    manifest_digest = cast(str, manifest["manifest_digest"])
    final_fence = _signed_artifact(final_fence_path, signer, "fence_digest")
    if final_fence.get("phase") != "final":
        raise ValueError("request-final-fence-phase-invalid")
    command_id = uuid5(_COMMAND_NAMESPACE, f"{manifest_digest}:complete")
    result = _post_accepted(
        client,
        "/_internal/request-cutover/complete",
        command_id,
        {
            "manifest_digest": manifest_digest,
            "final_fence": _artifact_text(final_fence),
            "reviewer_public_key_pem": reviewer_public_key_pem,
        },
    )
    absent = client.get(
        f"/_internal/request-cutover/reconcile/{manifest_digest}/0",
        headers=_read_headers(),
    )
    if absent.status_code != httpx.codes.NOT_FOUND:
        raise ValueError("request-import-operation-still-present")
    return {
        "schema": "ctower.request-cutover-transcript/v1",
        "phase": "completed",
        "manifest_digest": manifest_digest,
        "imported_count": result["imported_count"],
        "target_watermark": result["target_watermark"],
        "import_operation_absent": True,
    }


def _post_accepted(
    client: httpx.Client, path: str, command_id: UUID, payload: Mapping[str, object]
) -> dict[str, Any]:
    headers = {**_command_headers(command_id), "Idempotency-Key": str(command_id)}
    for _attempt in range(_MAX_ACCEPTANCE_POLLS):
        response = client.post(path, json=payload, headers=headers)
        if response.is_error:
            raise ValueError(f"request-cutover-http-refusal:{response.status_code}")
        body = _response_object(response)
        if body.get("durability_state") == "accepted":
            return body
        retry = min(float(response.headers.get("Retry-After", "1")), 5.0)
        time.sleep(max(retry, 0.1))
    raise TimeoutError("request-cutover-durability-acceptance-timeout")


def _get_json(client: httpx.Client, path: str) -> dict[str, Any]:
    response = client.get(path, headers=_read_headers())
    if response.is_error:
        raise ValueError(f"request-cutover-http-refusal:{response.status_code}")
    return _response_object(response)


def _public_samples(
    client: httpx.Client, reconciliation: Mapping[str, object]
) -> list[dict[str, object]]:
    rows = cast(list[dict[str, object]], reconciliation["rows"])
    by_id = {cast(str, row["id"]): row for row in rows}
    selected: list[dict[str, object]] = []
    cache: dict[str, list[dict[str, object]]] = {}
    for source_id in cast(list[str], reconciliation["sample_ids"]):
        expected = by_id[source_id]
        project = cast(str, expected["project_key"])
        if project not in cache:
            payload = _get_json(client, f"/v1/requests?project_key={project}")
            cache[project] = cast(list[dict[str, object]], payload["rows"])
        observed = next(
            (item for item in cache[project] if item.get("request_id") == expected["request_id"]),
            None,
        )
        _compare_public_sample(observed, expected)
        selected.append(expected)
    return selected


def _compare_public_sample(
    observed: dict[str, object] | None, expected: Mapping[str, object]
) -> None:
    if observed is None:
        raise ValueError("request-public-sample-missing")
    comparable = {
        "content_sha256": expected["content_sha256"],
        "durability_state": "accepted",
        "original_owner_sha256": expected["original_owner_sha256"],
        "owner_id": expected["owner_id"],
        "priority": expected["priority"],
        "project_key": expected["project_key"],
        "request_id": expected["request_id"],
        "request_number": expected["request_number"],
        "source_ref": expected["source_alias"],
        "state": expected["state"],
        "ticket_count": 0,
        "triage": expected["triage"],
    }
    if any(observed.get(key) != value for key, value in comparable.items()):
        raise ValueError("request-public-sample-differs")
    if _instant(observed.get("created_at")) != _instant(expected.get("created_at")):
        raise ValueError("request-public-sample-created-at-differs")


def _seal_proof(
    signer: ArtifactSigner,
    reconciliation: dict[str, Any],
    samples: list[dict[str, object]],
) -> dict[str, Any]:
    proof = dict(reconciliation)
    proof.pop("sample_ids", None)
    proof.update({"schema": "ctower.request-batch-proof/v1", "samples": samples})
    return signer.seal(proof, "proof_digest")


def _signed_artifact(path: Path, signer: ArtifactSigner, digest_field: str) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or rfc8785.dumps(value) != raw:
        raise ValueError("request-artifact-not-canonical")
    signer.verifier().verify(cast(dict[str, Any], value), digest_field)
    return cast(dict[str, Any], value)


def _recheck_source(ledger_path: Path, manifest: Mapping[str, object]) -> None:
    metadata = ledger_path.lstat()
    expected = cast(Mapping[str, object], manifest["source_identity"])
    observed = {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mode": metadata.st_mode,
        "mtime_ns": str(metadata.st_mtime_ns),
        "size": metadata.st_size,
    }
    if observed != expected:
        raise ValueError("request-source-identity-drift")
    _require_digest(ledger_path.read_bytes(), cast(str, manifest["ledger_sha256"]))


def _latest_source_text(path: Path) -> dict[str, str]:
    latest: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError("request-source-row-invalid")
        source_id, text = value.get("id"), value.get("text")
        if isinstance(source_id, str) and source_id.startswith("R") and isinstance(text, str):
            latest[source_id] = text
    return latest


def _require_digest(value: bytes, expected: str) -> None:
    if f"sha256:{hashlib.sha256(value).hexdigest()}" != expected:
        raise ValueError("request-source-digest-drift")


def _response_object(response: httpx.Response) -> dict[str, Any]:
    value = response.json()
    if not isinstance(value, dict):
        raise TypeError("request-cutover-response-invalid")
    return cast(dict[str, Any], value)


def _artifact_text(value: Mapping[str, object]) -> str:
    return rfc8785.dumps(cast(Any, value)).decode("utf-8")


def _command_headers(command_id: UUID) -> dict[str, str]:
    return {
        "X-Ctower-Telemetry-Context": json.dumps(
            {
                "schema": "ctower.telemetry-context/v1",
                "trace_id": command_id.hex,
                "span_id": command_id.hex[:16],
                "trace_flags": 1,
                "correlation_id": str(command_id),
                "causation_id": str(command_id),
                "tenant_id": "unresolved",
                "actor_id": "unresolved",
                "command_id": str(command_id),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    }


def _read_headers() -> dict[str, str]:
    command_id = uuid5(_COMMAND_NAMESPACE, "request-cutover-read")
    return _command_headers(command_id)


def _instant(value: object) -> str:
    return str(value).replace("+00:00", "Z")
