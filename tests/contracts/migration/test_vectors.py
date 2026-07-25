"""Executable I1.7B cohort, capability, conservation, and signature vectors."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
VECTOR = json.loads(
    (ROOT / "contracts/domain/migration/migration-vectors.json").read_text(encoding="utf-8")
)
STABLE_ALIAS_COUNT = 27
CHECKPOINT_COUNT = 14
REQUEST_COUNT = 86
REQUEST_SNAPSHOT_COUNT = 243
COORDINATION_PATH_COUNT = 89
MAX_BATCH_ITEMS = 64


def test_exact_source_cohort_and_planning_receipts_are_frozen() -> None:
    source = VECTOR["sealed_source"]
    requests = source["mission_control_requests"]
    tasks = source["mission_control_tasks"]

    assert len(source["stable_ticket_ids"]) == STABLE_ALIAS_COUNT
    assert len(set(source["stable_ticket_ids"])) == STABLE_ALIAS_COUNT
    assert len(source["checkpoint_keys"]) == CHECKPOINT_COUNT
    assert len(set(source["checkpoint_keys"])) == CHECKPOINT_COUNT
    assert len(source["mission_control_request_ids"]) == REQUEST_COUNT
    assert len(set(source["mission_control_request_ids"])) == REQUEST_COUNT
    assert source["mission_control_task_ids"] == []
    assert requests == {
        "source_digest": "sha256:2d03b2b24a5545a3cba7bb67d879b911c838ba4be78d131e63afd4657ceeec7a",
        "source_bytes": 3136405,
        "source_rows": 2059,
        "selected_logical": 86,
        "selected_physical_snapshots": 243,
        "selected_statuses": {"DONE": 72, "NEW": 5, "WIP": 8, "WONT-DO": 1},
    }
    assert sum(requests["selected_statuses"].values()) == REQUEST_COUNT
    assert tasks["selected_logical"] == 0
    assert source["coordination_closure"]["path_count"] == COORDINATION_PATH_COUNT
    assert source["github_release_count"] == 0


def test_capability_and_batch_union_are_closed_world() -> None:
    matrix = VECTOR["capability_matrix"]
    batch = VECTOR["typed_batch_union"]

    assert matrix["migration_importer"] == ["applyCtowerProjectImportBatch"]
    assert matrix["fence_observer"] == ["reportCtowerProjectFenceObservation"]
    assert "proof" in matrix["migration_importer_forbidden_classes"]
    assert "workflow" in matrix["migration_importer_forbidden_classes"]
    assert batch["operation_kinds"] == [
        "ticket_seed",
        "exact_alias",
        "ticket_relation",
        "source_link",
    ]
    assert batch["maximum_items"] == MAX_BATCH_ITEMS
    assert batch["maximum_canonical_request_bytes"] == 256 * 1024
    assert batch["ticket_seed_priority"] == "P2"
    assert batch["project_key"] == "ctower"


def test_disposition_and_conservation_equations_are_executable() -> None:
    equation = VECTOR["disposition_equation"]
    conservation = VECTOR["conservation_equations"]

    assert "attention_required" not in equation["selected_logical_items_sum"]
    assert equation["attention_required"] == 0
    for case in equation["vectors"]:
        total = sum(case["dispositions"][name] for name in equation["selected_logical_items_sum"])
        assert (total == case["selected_logical_items"]) is case["valid"]
    assert conservation["selected_request_logical"] == REQUEST_COUNT
    assert conservation["selected_request_physical_snapshots"] == REQUEST_SNAPSHOT_COUNT
    assert conservation["stable_aliases"] == STABLE_ALIAS_COUNT
    assert conservation["checkpoint_definitions"] == CHECKPOINT_COUNT
    for name, value in conservation.items():
        if name not in {
            "selected_request_logical",
            "selected_request_physical_snapshots",
            "stable_aliases",
            "checkpoint_definitions",
        }:
            assert value == 0, name


def test_canonical_digest_and_ed25519_signature_reject_rebinding() -> None:
    fixture = VECTOR["canonical_signature"]
    canonical = rfc8785.dumps(fixture["payload"])
    signed_digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
    key = Ed25519PublicKey.from_public_bytes(_decode(fixture["public_key_base64url"]))

    assert canonical.hex() == fixture["canonical_hex"]
    assert signed_digest == fixture["signed_digest"]
    assert (
        "sha256:" + hashlib.sha256(_decode(fixture["public_key_base64url"])).hexdigest()
        == fixture["public_key_digest"]
    )
    key.verify(_decode(fixture["signature"]), signed_digest.encode("ascii"))
    with pytest.raises(InvalidSignature):
        key.verify(
            _decode(fixture["signature"]),
            ("sha256:" + ("f" * 64)).encode("ascii"),
        )


def test_red_negative_and_dormant_fence_vectors_cover_stop_conditions() -> None:
    negative = set(VECTOR["negative_cases"])
    fence = VECTOR["synthetic_fence_registry"]

    assert {
        "unknown_field",
        "operation_kind_drift",
        "digest_rebinding",
        "signature_rebinding",
        "cross_project",
        "cross_tenant",
        "alias_cycle",
        "alias_fork",
        "stale_correction_tip",
        "missing_relation_endpoint",
        "forbidden_relation_cycle",
        "noncontiguous_fence_observation",
    } == negative
    assert fence["mode"] == "synthetic_dormant"
    assert fence["observer_can_disable"] is True
    assert fence["observer_can_enable"] is False


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))
