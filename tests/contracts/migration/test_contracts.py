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

_HEALTH_BASE: dict[str, object] = {
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

_HEALTH_CONTRADICTIONS: dict[str, dict[str, object]] = {
    "writes_enabled_true_with_unarmed_fence": {
        **_HEALTH_BASE,
        "authority_mode": "development_single_writer",
        "phase": "development_epoch_committed",
        "writes_enabled": True,
        "legacy_writer_fence": "not_armed",
    },
    "writes_enabled_true_with_detected_split_brain": {
        **_HEALTH_BASE,
        "authority_mode": "development_single_writer",
        "phase": "development_epoch_committed",
        "writes_enabled": True,
        "legacy_writer_fence": "enforced",
        "split_brain": "detected",
    },
    "writes_enabled_true_under_legacy_writable": {
        **_HEALTH_BASE,
        "writes_enabled": True,
        "legacy_writer_fence": "enforced",
        "split_brain": "clear",
    },
    "development_mode_claims_cp3_d_proven": {
        **_HEALTH_BASE,
        "authority_mode": "development_single_writer",
        "phase": "development_epoch_committed",
        "durability_claim": "CP3_D_PROVEN",
    },
    "disaster_safe_without_recovery_proof": {
        **_HEALTH_BASE,
        "authority_mode": "disaster_safe",
        "phase": "disaster_safe_active",
        "durability_claim": "CP3_D_PROVEN",
        "recovery_claim": "EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
        "data_class": "DISASTER_SAFE_CTOWER_ENGINEERING",
    },
    "prepared_phase_with_development_mode": {
        **_HEALTH_BASE,
        "authority_mode": "development_single_writer",
    },
    "development_epoch_committed_with_legacy_writable": {
        **_HEALTH_BASE,
        "phase": "development_epoch_committed",
    },
}


def test_cutover_health_requires_explicit_development_degradation() -> None:
    validator = _validator("ctower-project-cutover-health.schema.json")
    payload = dict(_HEALTH_BASE)

    validator.validate(payload)
    with pytest.raises(ValidationError):
        validator.validate({**payload, "durability_claim": "probably-safe"})
    with pytest.raises(ValidationError):
        validator.validate({**payload, "status": "green"})


def test_cutover_health_rejects_self_contradictory_boundary_combinations() -> None:
    validator = _validator("ctower-project-cutover-health.schema.json")
    for payload in _HEALTH_CONTRADICTIONS.values():
        with pytest.raises(ValidationError):
            validator.validate(payload)


def test_cutover_health_accepts_coherent_armed_and_disaster_safe_payloads() -> None:
    validator = _validator("ctower-project-cutover-health.schema.json")
    armed = {
        **_HEALTH_BASE,
        "cutover_id": "00000000-0000-0000-0000-000000000001",
        "authority_mode": "development_single_writer",
        "phase": "development_epoch_committed",
        "writes_enabled": True,
        "legacy_writer_fence": "enforced",
        "source_watermark": 5,
        "projection_watermark": 5,
    }
    disaster_safe = {
        **armed,
        "authority_mode": "disaster_safe",
        "phase": "disaster_safe_active",
        "writes_enabled": False,
        "legacy_writer_fence": "enforced",
        "durability_claim": "CP3_D_PROVEN",
        "recovery_claim": "EXTERNAL_FAILURE_DOMAIN_PROVEN",
        "data_class": "DISASTER_SAFE_CTOWER_ENGINEERING",
    }

    validator.validate(armed)
    validator.validate(disaster_safe)


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
