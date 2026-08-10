"""Strict reviewed-owner and source-fence evidence for Request cutover."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from ctower_contracts import validator_for
from jsonschema import ValidationError

from tools.migration.ctower_project.ctower_project_source.canonical import canonical_digest
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.operator_requests._dry_run_source import (
    read_stable_regular,
    unique_object,
)

__all__ = ["fence_proof", "owner_map"]

OwnerMappings = dict[tuple[str | None, str | None], dict[str, str]]
OwnerMapResult = tuple[
    OwnerMappings,
    dict[str, str],
    str | None,
    str | None,
    str | None,
    list[str],
]


def owner_map(path: Path | None) -> OwnerMapResult:
    if path is None:
        return {}, {}, None, None, None, ["owner-map-missing"]
    value = _load_object(path, "owner-map-malformed")
    if value.get("schema") != "ctower.request-owner-map/v1":
        raise ValueError("owner-map-schema-invalid")
    _validate(value, "ctower.request-owner-map/v1", "owner-map-contract-invalid")
    return (
        _owner_mappings(value.get("mappings", [])),
        _request_reviews(value.get("request_reviews", [])),
        canonical_digest(cast(dict[str, Any], value)),
        cast(str, value["target_tenant_id"]),
        cast(str, value["target_authority_digest"]),
        [],
    )


def _owner_mappings(entries: object) -> OwnerMappings:
    mappings: OwnerMappings = {}
    for item in cast(list[object], entries):
        key, mapping = _owner_mapping(item)
        if key in mappings:
            raise ValueError("owner-map-entry-duplicate")
        mappings[key] = mapping
    return mappings


def _owner_mapping(
    item: object,
) -> tuple[tuple[str | None, str | None], dict[str, str]]:
    if not isinstance(item, dict):
        raise TypeError("owner-map-entry-invalid")
    project, owner, principal = (
        item.get("project_key"),
        item.get("source_owner"),
        item.get("principal_id"),
    )
    if not all(isinstance(member, str) and member for member in (project, owner, principal)):
        raise ValueError("owner-map-entry-invalid")
    try:
        UUID(cast(str, principal))
    except ValueError as error:
        raise ValueError("owner-map-principal-invalid") from error
    return (cast(str, project), cast(str, owner)), {
        "principal_id": cast(str, principal),
        "project_key": cast(str, project),
        "source_owner": cast(str, owner),
    }


def _request_reviews(entries: object) -> dict[str, str]:
    reviews: dict[str, str] = {}
    for item in cast(list[object], entries):
        if not isinstance(item, dict):
            raise TypeError("request-review-invalid")
        request_id, priority = item.get("id"), item.get("priority")
        if not isinstance(request_id, str) or priority not in {"P0", "P1", "P2"}:
            raise ValueError("request-review-invalid")
        if request_id in reviews:
            raise ValueError("request-review-duplicate")
        reviews[request_id] = cast(str, priority)
    return reviews


def fence_proof(
    path: Path | None,
    ledger_digest: str,
    *,
    source_identity: Mapping[str, object],
    signer: ArtifactSigner | None,
) -> tuple[dict[str, object] | None, list[str]]:
    if path is None:
        return None, ["source-fence-proof-missing"]
    value = _load_object(path, "source-fence-proof-malformed")
    if value.get("schema") != "ctower.request-source-fence/v1":
        return None, ["source-fence-proof-invalid"]
    try:
        validator_for("ctower.request-source-fence/v1").validate(value)
    except ValidationError:
        return None, ["source-fence-proof-contract-invalid"]
    blockers = _fence_binding_blockers(value, ledger_digest, source_identity)
    signature_problem = _fence_signature_problem(value, signer)
    if signature_problem is not None:
        blockers.append(signature_problem)
    return value, blockers


def _fence_binding_blockers(
    value: Mapping[str, object],
    ledger_digest: str,
    source_identity: Mapping[str, object],
) -> list[str]:
    blockers: list[str] = []
    if value.get("ledger_sha256") != ledger_digest:
        blockers.append("fence-ledger-digest-unbound")
    expected = {key: source_identity[key] for key in _identity_keys()}
    if value.get("source_identity") != expected:
        blockers.append("fence-source-identity-unbound")
    if value.get("phase") != "freeze":
        blockers.append("source-fence-phase-invalid")
    return blockers


def _fence_signature_problem(
    value: Mapping[str, object], signer: ArtifactSigner | None
) -> str | None:
    if signer is None:
        return "source-fence-signature-unverified"
    try:
        signer.verifier().verify(cast(dict[str, Any], value), "fence_digest")
    except ValueError:
        return "source-fence-signature-invalid"
    return None


def _load_object(path: Path, malformed: str) -> dict[str, object]:
    data, _identity = read_stable_regular(path)
    try:
        value = json.loads(data, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(malformed) from error
    if not isinstance(value, dict):
        raise TypeError(malformed)
    return cast(dict[str, object], value)


def _validate(value: object, schema: str, refusal: str) -> None:
    try:
        validator_for(schema).validate(value)
    except ValidationError as error:
        raise ValueError(refusal) from error


def _identity_keys() -> tuple[str, ...]:
    return "device", "inode", "mode", "mtime_ns", "size"
