"""Fail-closed parsing for immutable server-owned Proof policy snapshots."""

from __future__ import annotations

from typing import cast

import pytest

from ctower_kernel.proof import Criterion, ProofPolicy

__all__: tuple[str, ...] = ()
GATE_DIGEST = "sha256:" + "2" * 64
EVIDENCE_DIGEST = "sha256:" + "3" * 64


def test_exact_gate_and_evidence_mappings_form_one_pinned_policy() -> None:
    policy = ProofPolicy.from_mappings(
        _gate(),
        _evidence(),
        gate_policy_digest=GATE_DIGEST,
        evidence_policy_digest=EVIDENCE_DIGEST,
    )

    assert policy.pin == (
        "fixture.workflow@1",
        "fixture.gates@1",
        GATE_DIGEST,
        "fixture.evidence@1",
        EVIDENCE_DIGEST,
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
    criterion = Criterion(
        key="artifact-current",
        description="Artifact is current.",
        candidate_dependent=True,
        requires_verdict=True,
    )
    with pytest.raises(ValueError, match="references must be versioned"):
        ProofPolicy(
            workflow_ref="not-versioned",
            gate_policy_ref="fixture.gates@1",
            gate_policy_digest=GATE_DIGEST,
            evidence_policy_ref="fixture.evidence@1",
            evidence_policy_digest=EVIDENCE_DIGEST,
            criteria=(criterion,),
            reviewer_kind="operator",
            self_review_forbidden=True,
        )
    with pytest.raises(ValueError, match="digests must be content addressed"):
        ProofPolicy(
            workflow_ref="fixture.workflow@1",
            gate_policy_ref="fixture.gates@1",
            gate_policy_digest="mutable",
            evidence_policy_ref="fixture.evidence@1",
            evidence_policy_digest=EVIDENCE_DIGEST,
            criteria=(criterion,),
            reviewer_kind="operator",
            self_review_forbidden=True,
        )
    with pytest.raises(ValueError, match="nonempty and unique"):
        ProofPolicy(
            workflow_ref="fixture.workflow@1",
            gate_policy_ref="fixture.gates@1",
            gate_policy_digest=GATE_DIGEST,
            evidence_policy_ref="fixture.evidence@1",
            evidence_policy_digest=EVIDENCE_DIGEST,
            criteria=(),
            reviewer_kind="operator",
            self_review_forbidden=True,
        )
    with pytest.raises(ValueError, match="independent operator review"):
        ProofPolicy(
            workflow_ref="fixture.workflow@1",
            gate_policy_ref="fixture.gates@1",
            gate_policy_digest=GATE_DIGEST,
            evidence_policy_ref="fixture.evidence@1",
            evidence_policy_digest=EVIDENCE_DIGEST,
            criteria=(criterion,),
            reviewer_kind="operator",
            self_review_forbidden=False,
        )


def _parse(gate: dict[str, object], evidence: dict[str, object]) -> ProofPolicy:
    return ProofPolicy.from_mappings(
        gate,
        evidence,
        gate_policy_digest=GATE_DIGEST,
        evidence_policy_digest=EVIDENCE_DIGEST,
    )


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
