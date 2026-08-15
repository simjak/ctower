"""Shared, strict machinery for R3000 external-estate imports.

The external custodian owns source freezing and closure. This package owns only
source identity, signed manifest/parity validation, seat dispositions, and the
stable identifiers used by each tier importer. It never creates a principal,
seat, or grant.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid5

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from ctower_contracts import validator_for
from jsonschema import ValidationError

from ctower_kernel.record.artifacts import ArtifactError, verify_signed_artifact

__all__ = (
    "EstateImportWorkflow",
    "EstateRefusal",
    "EstateRefusalError",
    "SeatDisposition",
    "build_estate_manifest",
    "load_seat_mapping",
    "parity_report",
    "read_stable_source",
    "resolve_seat",
    "stable_source_id",
    "verify_estate_manifest_text",
)

_MANIFEST_SCHEMA = "ctower.estate-import-manifest/v1"
_PARITY_SCHEMA = "ctower.estate-import-parity/v1"
_MAPPING_SCHEMA = "ctower.estate-seat-mapping/v1"
_BATCH_SIZE = 100
_MAX_SOURCE_REF = 512
_MAPPING_DIGEST_FIELD = "mapping_digest"
_ESTATE_NAMESPACE = UUID("b6fb53ef-8a3f-5e0d-9b1d-5a66efab4b5a")
_TIERS = frozenset({"inbox_history", "agreed_decisions", "knowledge_documents", "company_records"})
_SHA256_PREFIX = "sha256:"


class _Sealer(Protocol):
    def seal(self, artifact: Mapping[str, Any], digest_field: str) -> dict[str, Any]: ...


class EstateRefusalError(ValueError):
    """One stable import refusal made before target mutation."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


EstateRefusal = EstateRefusalError


@dataclass(frozen=True, slots=True)
class SeatDisposition:
    source_seat: str
    disposition: str
    target_seat_key: str | None


class EstateImportWorkflow:
    """Run one signed tier import with authority and closure ordering fences."""

    def __init__(self, public_key: Ed25519PublicKey) -> None:
        self._public_key = public_key

    def execute(
        self,
        *,
        actor_kind: str,
        tier: str,
        manifest_text: str,
        rows: Sequence[Mapping[str, Any]],
        batch_importer: Callable[[int, Sequence[Mapping[str, Any]]], int],
        emit_report: Callable[[Mapping[str, Any]], None],
        close_source: Callable[[], None],
        signer: _Sealer,
    ) -> dict[str, Any]:
        """Preflight everything, import batches, persist parity, then close the source."""

        if actor_kind != "operator":
            raise EstateRefusal("operator-required", "estate imports require operator authority")
        manifest = verify_estate_manifest_text(
            manifest_text,
            tier=tier,
            source_row_count=len(rows),
            public_key=self._public_key,
        )
        _validate_row_dispositions(rows)
        batch_counts = self._import_batches(manifest, rows, batch_importer)
        report = parity_report(
            tier=tier,
            manifest=manifest,
            source_count=len(rows),
            imported_count=sum(count for _index, count in batch_counts),
            batch_imports=batch_counts,
            sampled=_samples(rows),
            source_only_owners=_source_only_owners(rows),
            signer=signer,
        )
        emit_report(report)
        close_source()
        return report

    @staticmethod
    def _import_batches(
        manifest: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        batch_importer: Callable[[int, Sequence[Mapping[str, Any]]], int],
    ) -> list[tuple[int, int]]:
        batches = manifest.get("batches")
        if not isinstance(batches, list):
            raise EstateRefusal("manifest-invalid", "manifest batches are missing")
        result: list[tuple[int, int]] = []
        offset = 0
        for item in batches:
            if not isinstance(item, dict):
                raise EstateRefusal("manifest-invalid", "manifest batch is not an object")
            index, count = int(item["batch_index"]), int(item["source_count"])
            batch_rows = rows[offset : offset + count]
            imported = batch_importer(index, batch_rows)
            if imported < 0 or imported > count:
                raise EstateRefusal(
                    "import-count-invalid", "batch importer returned an invalid count"
                )
            result.append((index, imported))
            offset += count
        if offset != len(rows):
            raise EstateRefusal(
                "manifest-count-mismatch", "manifest batches do not cover source rows"
            )
        return result


def read_stable_source(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Read one regular source file and bind its bytes to one identity snapshot."""

    try:
        before = path.lstat()
    except OSError as error:
        raise EstateRefusal("source-missing", f"source file is absent: {path}") from error
    if not path.is_file() or path.is_symlink():
        raise EstateRefusal("source-not-regular", f"source file is not a regular file: {path}")
    try:
        data = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise EstateRefusal("source-unreadable", f"source file cannot be read: {path}") from error
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise EstateRefusal("source-drift", f"source changed while it was read: {path}")
    return data, {
        "namespace": "mission-control:estate",
        "source_path": str(path.resolve()),
        "source_sha256": _digest(data),
        "size_bytes": len(data),
        "frozen_at": datetime.fromtimestamp(after.st_mtime, tz=UTC).isoformat(),
    }


def load_seat_mapping(path: Path) -> dict[str, SeatDisposition]:
    """Load and verify one operator-approved source-seat disposition plan."""

    raw = _read_mapping(path)
    _verify_mapping_digest(raw)
    return _parse_mapping_rows(raw)


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EstateRefusal(
            "seat-mapping-invalid", f"seat mapping cannot be read: {path}"
        ) from error
    try:
        validator_for(_MAPPING_SCHEMA).validate(value)
    except ValidationError as error:
        raise EstateRefusal(
            "seat-mapping-invalid", "seat mapping violates its strict contract"
        ) from error
    if not isinstance(value, dict):
        raise EstateRefusal("seat-mapping-invalid", "seat mapping must be an object")
    return cast(dict[str, Any], value)


def _verify_mapping_digest(raw: Mapping[str, Any]) -> None:
    expected = _canonical_digest_without(raw, _MAPPING_DIGEST_FIELD)
    if raw.get(_MAPPING_DIGEST_FIELD) != expected:
        raise EstateRefusal(
            "seat-mapping-digest-mismatch",
            "seat mapping digest does not bind its rows",
        )


def _parse_mapping_rows(raw: Mapping[str, Any]) -> dict[str, SeatDisposition]:
    result: dict[str, SeatDisposition] = {}
    mappings = raw.get("mappings")
    if not isinstance(mappings, list):
        raise EstateRefusal("seat-mapping-invalid", "seat mapping rows are missing")
    for entry in mappings:
        if not isinstance(entry, dict):
            raise EstateRefusal("seat-mapping-invalid", "seat mapping row is not an object")
        source_seat = str(entry["source_seat"])
        if source_seat in result:
            raise EstateRefusal("seat-mapping-duplicate", f"seat mapped twice: {source_seat}")
        disposition = str(entry["disposition"])
        target = entry.get("target_seat_key")
        if disposition == "mapped" and not isinstance(target, str):
            raise EstateRefusal("seat-mapping-invalid", f"mapped seat has no target: {source_seat}")
        if disposition == "source_only" and target is not None:
            raise EstateRefusal(
                "seat-mapping-invalid", f"source-only seat has a target: {source_seat}"
            )
        result[source_seat] = SeatDisposition(
            source_seat,
            disposition,
            target if isinstance(target, str) else None,
        )
    return result


def resolve_seat(
    source_seat: str,
    mapping: Mapping[str, SeatDisposition],
) -> SeatDisposition:
    """Resolve one owner or return a typed refusal; never invent a principal."""

    disposition = mapping.get(source_seat)
    if disposition is None:
        raise EstateRefusal(
            "seat-unmapped", f"source seat has no approved disposition: {source_seat}"
        )
    return disposition


def stable_source_id(tier: str, source_ref: str) -> UUID:
    """Derive one deterministic identity from the immutable tier/source reference."""

    _validate_tier(tier)
    if not source_ref or len(source_ref) > _MAX_SOURCE_REF:
        raise EstateRefusal("source-ref-invalid", "source reference is outside the contract")
    return uuid5(_ESTATE_NAMESPACE, f"{tier}:{source_ref}")


def build_estate_manifest(
    *,
    tier: str,
    source_identity: dict[str, Any],
    rows: list[dict[str, Any]],
    seat_mapping_digest: str | None,
    project_key: str | None = None,
    signer: _Sealer | None,
) -> dict[str, Any]:
    """Build one strict signed manifest over a non-empty frozen source."""

    _validate_tier(tier)
    if not rows:
        raise EstateRefusal("source-empty", "an estate manifest cannot bind an empty source")
    _validate_row_dispositions(rows)
    source_count = len(rows)
    mapped = sum(1 for row in rows if row.get("_disposition") == "mapped")
    manifest: dict[str, Any] = {
        "schema": _MANIFEST_SCHEMA,
        "tier": tier,
        "source_identity": source_identity,
        "counts": {
            "source_rows": source_count,
            "mapped_rows": mapped,
            "source_only_rows": source_count - mapped,
        },
        "batches": [
            {
                "batch_index": index // _BATCH_SIZE,
                "batch_digest": _digest_json(rows[index : index + _BATCH_SIZE]),
                "source_count": len(rows[index : index + _BATCH_SIZE]),
            }
            for index in range(0, source_count, _BATCH_SIZE)
        ],
    }
    if project_key is not None:
        manifest["project_key"] = project_key
    if seat_mapping_digest is not None:
        _validate_digest(seat_mapping_digest, "seat mapping digest")
        manifest["seat_mapping_digest"] = seat_mapping_digest
    return manifest if signer is None else signer.seal(manifest, "manifest_digest")


def verify_estate_manifest_text(
    manifest_text: str,
    *,
    tier: str,
    source_row_count: int,
    public_key: Ed25519PublicKey,
) -> dict[str, Any]:
    """Verify canonical JSON, schema, signature, tier, and complete batch denominator."""

    _validate_tier(tier)
    try:
        artifact, _digest = verify_signed_artifact(
            manifest_text,
            _MANIFEST_SCHEMA,
            "manifest_digest",
            _trusted_key(manifest_text, public_key),
        )
    except ArtifactError as error:
        raise EstateRefusal("manifest-tampered", str(error)) from error
    if artifact.get("tier") != tier:
        raise EstateRefusal(
            "manifest-tier-mismatch",
            "manifest tier does not match the requested import",
        )
    counts = artifact.get("counts")
    batches = artifact.get("batches")
    if not isinstance(counts, dict) or not isinstance(batches, list):
        raise EstateRefusal("manifest-invalid", "manifest counts or batches are missing")
    declared = counts.get("source_rows")
    if declared != source_row_count:
        raise EstateRefusal(
            "manifest-count-mismatch",
            f"manifest declares {declared} rows; source has {source_row_count}",
        )
    _validate_batches(batches, source_row_count)
    return artifact


def parity_report(
    *,
    tier: str,
    manifest: Mapping[str, Any],
    source_count: int,
    imported_count: int,
    batch_imports: list[tuple[int, int]],
    sampled: list[tuple[str, str]],
    source_only_owners: list[tuple[str, int]],
    signer: _Sealer | None,
) -> dict[str, Any]:
    """Create one typed parity report; callers must persist it before closure."""

    _validate_tier(tier)
    _validate_parity_counts(source_count, imported_count)
    manifest_digest = _manifest_digest(manifest)
    batches = _manifest_parity_batches(manifest)
    actual = _validated_batch_imports(batches, batch_imports)
    _validate_samples(sampled)
    report = {
        "schema": _PARITY_SCHEMA,
        "tier": tier,
        "manifest_digest": manifest_digest,
        "source_count": source_count,
        "imported_count": imported_count,
        "batches": [
            {
                "batch_index": int(batch["batch_index"]),
                "batch_digest": str(batch["batch_digest"]),
                "source_count": int(batch["source_count"]),
                "imported_count": actual[int(batch["batch_index"])],
            }
            for batch in batches
        ],
        "sampled_content_hashes": [
            {"source_ref": source_ref, "content_sha256": digest} for source_ref, digest in sampled
        ],
        "source_only_owners": [
            {
                "source_seat": source_seat,
                "row_count": row_count,
                "source_only_disposition": "source_only",
            }
            for source_seat, row_count in source_only_owners
        ],
        "emitted_before_closure": True,
    }
    return report if signer is None else signer.seal(report, "parity_digest")


def _validate_parity_counts(source_count: int, imported_count: int) -> None:
    if source_count < 1 or imported_count != source_count:
        raise EstateRefusal(
            "parity-count-mismatch",
            "parity requires source_count == imported_count > 0, "
            f"got {source_count}/{imported_count}",
        )


def _manifest_digest(manifest: Mapping[str, Any]) -> str:
    value = manifest.get("manifest_digest")
    if not isinstance(value, str):
        raise EstateRefusal("manifest-invalid", "parity requires a signed manifest digest")
    _validate_digest(value, "manifest digest")
    return value


def _manifest_parity_batches(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    batches = manifest.get("batches")
    if (
        not isinstance(batches, list)
        or not batches
        or not all(isinstance(batch, dict) for batch in batches)
    ):
        raise EstateRefusal("manifest-invalid", "parity requires manifest batches")
    return cast(list[dict[str, Any]], batches)


def _validated_batch_imports(
    batches: Sequence[Mapping[str, Any]], batch_imports: Sequence[tuple[int, int]]
) -> dict[int, int]:
    expected = {int(batch["batch_index"]): int(batch["source_count"]) for batch in batches}
    actual = dict(batch_imports)
    if set(expected) != set(actual) or any(
        actual[index] != count for index, count in expected.items()
    ):
        raise EstateRefusal(
            "parity-batch-mismatch", "imported batch counts do not match the manifest"
        )
    return actual


def _validate_samples(sampled: Sequence[tuple[str, str]]) -> None:
    if not sampled:
        raise EstateRefusal("parity-sample-missing", "parity requires a content sample")
    for source_ref, digest in sampled:
        if not source_ref or len(source_ref) > _MAX_SOURCE_REF:
            raise EstateRefusal("parity-sample-invalid", "sample source reference is invalid")
        _validate_digest(digest, "sample content digest")


def _validate_tier(tier: str) -> None:
    if tier not in _TIERS:
        raise EstateRefusal("tier-invalid", f"unknown estate import tier: {tier}")


def _validate_digest(value: str, label: str) -> None:
    if len(value) != len(_SHA256_PREFIX) + 64 or not value.startswith(_SHA256_PREFIX):
        raise EstateRefusal("digest-invalid", f"{label} is not a sha256 digest")
    try:
        int(value.removeprefix(_SHA256_PREFIX), 16)
    except ValueError as error:
        raise EstateRefusal("digest-invalid", f"{label} is not a sha256 digest") from error


def _digest(value: bytes) -> str:
    return f"{_SHA256_PREFIX}{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: object) -> str:
    return _digest(rfc8785.dumps(cast(Any, value)))


def _canonical_digest_without(value: Mapping[str, Any], excluded: str) -> str:
    return _digest_json({key: item for key, item in value.items() if key != excluded})


def _validate_batches(batches: list[object], source_count: int) -> None:
    total = 0
    for expected_index, item in enumerate(batches):
        if not isinstance(item, dict):
            raise EstateRefusal("manifest-invalid", "manifest batch is not an object")
        index = item.get("batch_index")
        count = item.get("source_count")
        digest = item.get("batch_digest")
        if index != expected_index or not isinstance(count, int) or count < 1:
            raise EstateRefusal("manifest-batch-mismatch", "manifest batches are not contiguous")
        if not isinstance(digest, str):
            raise EstateRefusal("manifest-batch-mismatch", "manifest batch digest is missing")
        _validate_digest(digest, "manifest batch digest")
        total += count
    if total != source_count:
        raise EstateRefusal(
            "manifest-count-mismatch",
            f"manifest batches total {total} rows; source has {source_count}",
        )


def _validate_row_dispositions(rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        if row.get("_disposition") not in {"mapped", "source_only"}:
            raise EstateRefusal(
                "seat-disposition-missing",
                "every imported row needs a mapped or source_only disposition",
            )


def _samples(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for row in rows[:3]:
        source_ref = row.get("source_ref")
        content_sha256 = row.get("content_sha256")
        if isinstance(source_ref, str) and isinstance(content_sha256, str):
            result.append((source_ref, content_sha256))
    return result


def _source_only_owners(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("_disposition") != "source_only":
            continue
        source_seat = row.get("source_seat")
        if not isinstance(source_seat, str) or not source_seat:
            raise EstateRefusal(
                "seat-disposition-missing", "source-only rows must name their source seat"
            )
        counts[source_seat] = counts.get(source_seat, 0) + 1
    return sorted(counts.items())


def _trusted_key(
    manifest_text: str, public_key: Ed25519PublicKey
) -> dict[tuple[str, int], Ed25519PublicKey]:
    try:
        parsed = json.loads(manifest_text)
        signature = parsed.get("signature", {})
        key_ref = signature.get("key_ref")
        key_version = signature.get("key_version")
    except (json.JSONDecodeError, AttributeError) as error:
        raise EstateRefusal("manifest-invalid", "manifest is not a JSON object") from error
    if not isinstance(key_ref, str) or not isinstance(key_version, int):
        raise EstateRefusal("manifest-unsigned", "manifest signature identity is missing")
    return {(key_ref, key_version): public_key}
