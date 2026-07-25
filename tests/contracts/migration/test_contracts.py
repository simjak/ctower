"""Strict development cutover-health and refusing-phase contracts."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
MIGRATION_CONTRACTS = ROOT / "contracts/domain/migration"


def test_cutover_health_requires_explicit_development_degradation() -> None:
    validator = _validator("ctower-project-cutover-health.schema.json")
    payload = {
        "schema": "ctower.ctower-project-cutover-health/v1",
        "cutover_id": None,
        "authority_mode": "legacy_writable",
        "phase": "not_started",
        "writes_enabled": False,
        "durability_claim": "CP3_D_NOT_PROVEN",
        "recovery_claim": "EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
        "data_class": "RECONSTRUCTIBLE_ONLY",
        "legacy_writer_fence": "not_armed",
        "split_brain": "clear",
        "projection_completeness": "current",
        "source_watermark": 0,
        "projection_watermark": 0,
        "banner": "DEVELOPMENT DOGFOOD — not disaster-safe",
    }

    validator.validate(payload)
    with pytest.raises(ValidationError):
        validator.validate({**payload, "durability_claim": "probably-safe"})
    with pytest.raises(ValidationError):
        validator.validate({**payload, "status": "green"})


def test_phase_stub_contract_is_narrow_and_digest_bound() -> None:
    validator = _validator("ctower-project-phase.schema.json")
    payload = {
        "schema": "ctower.ctower-project-migration-phase/v1",
        "cutover_id": str(uuid4()),
        "phase": "inventory",
        "input_digest": "sha256:" + ("a" * 64),
    }

    validator.validate(payload)
    with pytest.raises(ValidationError):
        validator.validate({**payload, "input_digest": "mutable-input"})
    with pytest.raises(ValidationError):
        validator.validate({**payload, "records": [{"status": "done"}]})


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((MIGRATION_CONTRACTS / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())
