"""Strict contract vectors for the four external-estate import tiers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from ctower_contracts import validator_for
from jsonschema.exceptions import ValidationError

__all__: tuple[str, ...] = ()

_SHA = "sha256:" + "1" * 64
_SIGNATURE = {
    "algorithm": "Ed25519",
    "signed_digest": _SHA,
    "key_ref": "signing-key-ref:estate-import",
    "key_version": 1,
    "public_key_digest": _SHA,
    "signature": "A" * 86,
}
_TIERS = ("inbox_history", "agreed_decisions", "knowledge_documents", "company_records")


def test_each_estate_tier_manifest_is_strict_and_signed() -> None:
    manifest = {
        "schema": "ctower.estate-import-manifest/v1",
        "tier": "inbox_history",
        "source_identity": {
            "namespace": "mission-control:estate",
            "source_path": "state/inbox.jsonl",
            "source_sha256": _SHA,
        },
        "counts": {"source_rows": 1, "mapped_rows": 1, "source_only_rows": 0},
        "batches": [{"batch_index": 0, "batch_digest": _SHA, "source_count": 1}],
        "manifest_digest": _SHA,
        "signature": _SIGNATURE,
    }

    for tier in _TIERS:
        candidate = deepcopy(manifest)
        candidate["tier"] = tier
        if tier == "company_records":
            candidate["source_identity"]["source_path"] = "state/escapes.jsonl"
        validator_for("ctower.estate-import-manifest/v1").validate(candidate)


def test_estate_manifest_rejects_unknown_fields() -> None:
    manifest = {
        "schema": "ctower.estate-import-manifest/v1",
        "tier": "company_records",
        "source_identity": {
            "namespace": "mission-control:estate",
            "source_path": "state/escapes.jsonl",
            "source_sha256": _SHA,
        },
        "counts": {"source_rows": 1},
        "batches": [{"batch_index": 0, "batch_digest": _SHA, "source_count": 1}],
        "manifest_digest": _SHA,
        "signature": _SIGNATURE,
        "unexpected": True,
    }

    with pytest.raises(ValidationError):
        validator_for("ctower.estate-import-manifest/v1").validate(manifest)


def test_company_record_payload_is_a_closed_typed_object() -> None:
    payload: dict[str, Any] = {
        "schema": "ctower.company-record-import/v1",
        "record_type": "escape",
        "natural_key": "2026-08-15:example defect",
        "occurred_on": "2026-08-15",
        "payload": {
            "defect": "example defect",
            "seat": "engineer",
        },
    }

    validator_for("ctower.company-record-import/v1").validate(payload)
    invalid = deepcopy(payload)
    invalid["payload"]["secret"] = {"nested": "value"}
    with pytest.raises(ValidationError):
        validator_for("ctower.company-record-import/v1").validate(invalid)
