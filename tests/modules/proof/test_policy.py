"""Fail-closed parsing for immutable server-owned Proof policy snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from ctower_kernel.proof import Criterion, ProofPolicy

__all__: tuple[str, ...] = ()
ROOT = Path(__file__).parents[3]


def test_exact_authoritative_bytes_are_inseparable_from_their_digests() -> None:
    gate_bytes = (ROOT / "packs/policies/gates/trust-spine-four-stage-v1.yaml").read_bytes()
    evidence_bytes = (ROOT / "packs/policies/evidence/trust-spine-four-stage-v1.yaml").read_bytes()
    gate_digest = "sha256:" + hashlib.sha256(gate_bytes).hexdigest()
    evidence_digest = "sha256:" + hashlib.sha256(evidence_bytes).hexdigest()

    policy = ProofPolicy.from_bytes(
        gate_bytes,
        evidence_bytes,
        expected_gate_policy_digest=gate_digest,
        expected_evidence_policy_digest=evidence_digest,
    )

    assert policy.pin == (
        "ctower.trust-spine-four-stage@1",
        "ctower.trust-spine-four-stage.gates@1",
        gate_digest,
        "ctower.trust-spine-four-stage.evidence@1",
        evidence_digest,
    )
    weakened_gate_bytes = gate_bytes.replace(
        b'"requires_verdict": true',
        b'"requires_verdict": false',
    )
    assert weakened_gate_bytes != gate_bytes
    with pytest.raises(ValueError, match="gate policy digest does not identify supplied bytes"):
        ProofPolicy.from_bytes(
            weakened_gate_bytes,
            evidence_bytes,
            expected_gate_policy_digest=gate_digest,
            expected_evidence_policy_digest=evidence_digest,
        )


def test_exact_gate_and_evidence_bytes_form_one_pinned_policy() -> None:
    gate, evidence = _gate(), _evidence()
    gate_bytes = _policy_bytes(gate)
    evidence_bytes = _policy_bytes(evidence)
    gate_digest = "sha256:" + hashlib.sha256(gate_bytes).hexdigest()
    evidence_digest = "sha256:" + hashlib.sha256(evidence_bytes).hexdigest()

    policy = ProofPolicy.from_bytes(gate_bytes, evidence_bytes)

    assert policy.pin == (
        "fixture.workflow@1",
        "fixture.gates@1",
        gate_digest,
        "fixture.evidence@1",
        evidence_digest,
    )
    assert policy.criteria == (
        Criterion(
            key="artifact-current",
            description="Artifact is current.",
            candidate_dependent=True,
            requires_verdict=True,
        ),
    )


def test_mapping_schemas_and_evidence_semantics_fail_closed() -> None:
    gate, evidence = _gate(), _evidence()
    gate["schema"] = "unsupported"
    with pytest.raises(ValueError, match="gate policy schema"):
        _parse(gate, evidence)

    gate, evidence = _gate(), _evidence()
    evidence["schema"] = "unsupported"
    with pytest.raises(ValueError, match="evidence policy schema"):
        _parse(gate, evidence)

    gate, evidence = _gate(), _evidence()
    gate["evidence_policy_ref"] = "other.evidence@1"
    with pytest.raises(ValueError, match="evidence reference mismatch"):
        _parse(gate, evidence)

    gate, evidence = _gate(), _evidence()
    evidence["candidate_binding"] = "caller"
    with pytest.raises(ValueError, match="current immutable bytes"):
        _parse(gate, evidence)


def test_gate_shape_and_protected_verdict_fail_closed() -> None:
    gate = _gate()
    gate["protected_verdict"] = None
    with pytest.raises(TypeError, match="proof obligations"):
        _parse(gate, _evidence())

    gate = _gate()
    gate["criteria"] = [None]
    with pytest.raises(TypeError, match="criterion must be an object"):
        _parse(gate, _evidence())

    gate = _gate()
    cast(list[dict[str, object]], gate["criteria"])[0]["requires_verdict"] = "yes"
    with pytest.raises(TypeError, match="flags must be boolean"):
        _parse(gate, _evidence())

    gate = _gate()
    cast(dict[str, object], gate["protected_verdict"])["reviewer_kind"] = "commander"
    with pytest.raises(ValueError, match="reviewer must be operator"):
        _parse(gate, _evidence())


def test_policy_identity_and_independence_fail_closed() -> None:
    gate, evidence = _gate(), _evidence()
    gate["workflow_ref"] = "not-versioned"
    with pytest.raises(ValueError, match="references must be versioned"):
        _parse(gate, evidence)

    with pytest.raises(ValueError, match="expected gate policy digest must be content addressed"):
        ProofPolicy.from_bytes(
            _policy_bytes(_gate()),
            _policy_bytes(_evidence()),
            expected_gate_policy_digest="mutable",
        )

    gate = _gate()
    gate["criteria"] = []
    with pytest.raises(ValueError, match="nonempty and unique"):
        _parse(gate, _evidence())

    gate = _gate()
    cast(dict[str, object], gate["protected_verdict"])["self_review"] = "allowed"
    with pytest.raises(ValueError, match="independent operator review"):
        _parse(gate, _evidence())


def _parse(gate: dict[str, object], evidence: dict[str, object]) -> ProofPolicy:
    return ProofPolicy.from_bytes(_policy_bytes(gate), _policy_bytes(evidence))


def _policy_bytes(policy: dict[str, object]) -> bytes:
    return json.dumps(policy, separators=(",", ":"), sort_keys=True).encode()


def _gate() -> dict[str, object]:
    return {
        "schema": "ctower.gate-policy/v1",
        "key": "fixture.gates",
        "revision": 1,
        "workflow_ref": "fixture.workflow@1",
        "evidence_policy_ref": "fixture.evidence@1",
        "criteria": [
            {
                "key": "artifact-current",
                "description": "Artifact is current.",
                "candidate_dependent": True,
                "requires_verdict": True,
            }
        ],
        "protected_verdict": {
            "reviewer_kind": "operator",
            "self_review": "forbidden",
        },
    }


def _evidence() -> dict[str, object]:
    return {
        "schema": "ctower.evidence-policy/v1",
        "key": "fixture.evidence",
        "revision": 1,
        "digest_algorithm": "sha256",
        "content_encoding": "utf-8",
        "candidate_binding": "current_digest",
        "corruption_policy": "reject",
        "missing_policy": "reject",
    }
