"""Evidence-manifest consumer subset vectors."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).parents[3]


def test_current_proof_manifest_and_explicit_zero_sources_validate() -> None:
    validator = Draft202012Validator(_schema())

    validator.validate(_manifest())


def test_activated_or_nonzero_deferred_source_fails_closed() -> None:
    validator = Draft202012Validator(_schema())
    for key, value in (("status", "exercised"), ("source_count", 1)):
        candidate = copy.deepcopy(_manifest())
        candidate["deferred_sources"]["remote"][key] = value
        with pytest.raises(ValidationError):
            validator.validate(candidate)


def _schema() -> dict[str, Any]:
    path = ROOT / "contracts/evidence/evidence-manifest.schema.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _manifest() -> dict[str, Any]:
    not_exercised = {"status": "not_exercised", "source_count": 0}
    return {
        "schema": "ctower.evidence-manifest/v1",
        "status": "development_only",
        "tenant_id": "00000000-0000-4000-8000-000000000001",
        "ticket_id": "00000000-0000-4000-8000-000000000002",
        "candidate_digest": "sha256:" + "a" * 64,
        "criteria_revision": 1,
        "artifacts": [
            {
                "criterion_key": "artifact-current",
                "artifact_digest": "sha256:" + "b" * 64,
                "candidate_digest": "sha256:" + "a" * 64,
            }
        ],
        "verdict_ids": ["00000000-0000-4000-8000-000000000003"],
        "deferred_sources": {
            name: dict(not_exercised) for name in ("remote", "images", "effects", "extensions")
        },
    }
