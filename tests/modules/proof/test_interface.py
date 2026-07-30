"""Public Proof Interface tracer tests."""

from __future__ import annotations

import hashlib
from typing import Literal
from uuid import UUID

from ctower_kernel.proof import (
    ChangeCandidate,
    Criterion,
    FreezeCriteria,
    Proof,
    ProofActor,
    ProofSnapshot,
    RecordEvidence,
    RecordVerdict,
    VerdictDecision,
)
from ctower_kernel.record import PrincipalKind

TENANT_ID = UUID("10000000-0000-4000-8000-000000000001")
AUTHOR_ID = UUID("20000000-0000-4000-8000-000000000001")
REVIEWER_ID = UUID("20000000-0000-4000-8000-000000000002")
__all__: tuple[str, ...] = ()


def _actor(
    principal_id: UUID = AUTHOR_ID, kind: PrincipalKind = PrincipalKind.COMMANDER
) -> ProofActor:
    proof_kind: Literal["operator", "commander"] = (
        "operator" if kind is PrincipalKind.OPERATOR else "commander"
    )
    return ProofActor(principal_id=principal_id, tenant_id=TENANT_ID, kind=proof_kind)


def test_criteria_freeze_once_and_incompatible_mutation_is_refused() -> None:
    proof = Proof()
    initial = ProofSnapshot.empty()
    command = FreezeCriteria(
        candidate_digest="sha256:" + "a" * 64,
        candidate_author_id=AUTHOR_ID,
        criteria=(
            Criterion(
                key="artifact-current",
                description="Candidate artifact matches the current digest.",
                candidate_dependent=True,
                requires_verdict=True,
            ),
        ),
    )

    frozen = proof.decide(_actor(), initial, command)
    incompatible = proof.decide(
        _actor(),
        frozen.snapshot,
        FreezeCriteria(
            candidate_digest=command.candidate_digest,
            candidate_author_id=AUTHOR_ID,
            criteria=(
                Criterion(
                    key="different",
                    description="A later caller cannot replace frozen policy.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
    )

    assert frozen.accepted is True
    assert frozen.facts == ("criteria.frozen",)
    assert frozen.snapshot.criteria == command.criteria
    assert incompatible.accepted is False
    assert incompatible.reason == "criteria-already-frozen"
    assert incompatible.snapshot == frozen.snapshot


def test_evidence_must_match_its_bytes_and_the_current_candidate_digest() -> None:
    proof = Proof()
    candidate_digest = "sha256:" + "a" * 64
    frozen = proof.decide(
        _actor(),
        ProofSnapshot.empty(),
        FreezeCriteria(
            candidate_digest=candidate_digest,
            candidate_author_id=AUTHOR_ID,
            criteria=(
                Criterion(
                    key="artifact-current",
                    description="Artifact is current.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
    ).snapshot
    content = b"deterministic evidence"
    digest = "sha256:" + hashlib.sha256(content).hexdigest()

    current = proof.decide(
        _actor(),
        frozen,
        RecordEvidence(
            evidence_id=UUID("30000000-0000-4000-8000-000000000001"),
            criterion_key="artifact-current",
            candidate_digest=None,
            artifact_digest=digest,
            content=content,
        ),
    )
    corrupt = proof.decide(
        _actor(),
        frozen,
        RecordEvidence(
            evidence_id=UUID("30000000-0000-4000-8000-000000000002"),
            criterion_key="artifact-current",
            candidate_digest=candidate_digest,
            artifact_digest=digest,
            content=b"tampered",
        ),
    )
    stale = proof.decide(
        _actor(),
        frozen,
        RecordEvidence(
            evidence_id=UUID("30000000-0000-4000-8000-000000000003"),
            criterion_key="artifact-current",
            candidate_digest="sha256:" + "b" * 64,
            artifact_digest=digest,
            content=content,
        ),
    )

    assert current.accepted is True
    assert current.snapshot.evidence[0].candidate_digest == candidate_digest
    assert current.snapshot.evidence[0].artifact_digest == digest
    assert current.facts == ("evidence.recorded",)
    assert corrupt.reason == "evidence-digest-mismatch"
    assert corrupt.snapshot == frozen
    assert stale.reason == "candidate-digest-not-current"
    assert stale.snapshot == frozen


def test_protected_verdict_requires_an_authorized_non_self_reviewer() -> None:
    proof = Proof()
    candidate_digest = "sha256:" + "a" * 64
    frozen = proof.decide(
        _actor(),
        ProofSnapshot.empty(),
        FreezeCriteria(
            candidate_digest=candidate_digest,
            candidate_author_id=AUTHOR_ID,
            criteria=(
                Criterion(
                    key="artifact-current",
                    description="Artifact is current.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
    ).snapshot
    content = b"reviewed evidence"
    with_evidence = proof.decide(
        _actor(),
        frozen,
        RecordEvidence(
            evidence_id=UUID("30000000-0000-4000-8000-000000000004"),
            criterion_key="artifact-current",
            candidate_digest=candidate_digest,
            artifact_digest="sha256:" + hashlib.sha256(content).hexdigest(),
            content=content,
        ),
    ).snapshot
    command = RecordVerdict(
        verdict_id=UUID("40000000-0000-4000-8000-000000000001"),
        criterion_key="artifact-current",
        candidate_digest=None,
        decision=VerdictDecision.PASSING,
    )

    self_review = proof.decide(_actor(kind=PrincipalKind.OPERATOR), with_evidence, command)
    unprotected = proof.decide(_actor(REVIEWER_ID, PrincipalKind.COMMANDER), with_evidence, command)
    accepted = proof.decide(_actor(REVIEWER_ID, PrincipalKind.OPERATOR), with_evidence, command)
    later_failure = proof.decide(
        _actor(REVIEWER_ID, PrincipalKind.OPERATOR),
        accepted.snapshot,
        RecordVerdict(
            verdict_id=UUID("40000000-0000-4000-8000-000000000003"),
            criterion_key="artifact-current",
            candidate_digest=candidate_digest,
            decision=VerdictDecision.FAILING,
        ),
    )

    assert self_review.reason == "self-review-refused"
    assert unprotected.reason == "protected-authority-required"
    assert accepted.accepted is True
    assert accepted.snapshot.verdicts[0].candidate_digest == candidate_digest
    assert accepted.snapshot.verdicts[0].reviewer_id == REVIEWER_ID
    assert accepted.facts == ("verdict.recorded",)
    assert proof.is_satisfied(accepted.snapshot) is True
    assert later_failure.accepted is True
    assert proof.is_satisfied(later_failure.snapshot) is False


def test_verdict_requires_current_evidence_and_proof_identifiers_are_single_use() -> None:
    proof = Proof()
    candidate_digest = "sha256:" + "d" * 64
    frozen = proof.decide(
        _actor(),
        ProofSnapshot.empty(),
        FreezeCriteria(
            candidate_digest=candidate_digest,
            candidate_author_id=AUTHOR_ID,
            criteria=(
                Criterion(
                    key="artifact-current",
                    description="Artifact is current.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
    ).snapshot
    verdict = RecordVerdict(
        verdict_id=UUID("40000000-0000-4000-8000-000000000004"),
        criterion_key="artifact-current",
        candidate_digest=candidate_digest,
        decision=VerdictDecision.PASSING,
    )

    missing_evidence = proof.decide(_actor(REVIEWER_ID, PrincipalKind.OPERATOR), frozen, verdict)
    content = b"single-use evidence"
    evidence = RecordEvidence(
        evidence_id=UUID("30000000-0000-4000-8000-000000000007"),
        criterion_key="artifact-current",
        candidate_digest=candidate_digest,
        artifact_digest="sha256:" + hashlib.sha256(content).hexdigest(),
        content=content,
    )
    recorded = proof.decide(_actor(), frozen, evidence)
    duplicate_evidence = proof.decide(_actor(), recorded.snapshot, evidence)
    reviewed = proof.decide(_actor(REVIEWER_ID, PrincipalKind.OPERATOR), recorded.snapshot, verdict)
    duplicate_verdict = proof.decide(
        _actor(REVIEWER_ID, PrincipalKind.OPERATOR), reviewed.snapshot, verdict
    )

    assert missing_evidence.accepted is False
    assert missing_evidence.reason == "current-evidence-missing"
    assert missing_evidence.snapshot == frozen
    assert recorded.accepted is True
    assert duplicate_evidence.accepted is False
    assert duplicate_evidence.reason == "evidence-id-conflict"
    assert duplicate_evidence.snapshot == recorded.snapshot
    assert reviewed.accepted is True
    assert duplicate_verdict.accepted is False
    assert duplicate_verdict.reason == "verdict-id-conflict"
    assert duplicate_verdict.snapshot == reviewed.snapshot


def test_candidate_change_invalidates_only_candidate_dependent_proof() -> None:
    proof = Proof()
    first_digest = "sha256:" + "a" * 64
    snapshot = proof.decide(
        _actor(),
        ProofSnapshot.empty(),
        FreezeCriteria(
            candidate_digest=first_digest,
            candidate_author_id=AUTHOR_ID,
            criteria=(
                Criterion(
                    key="candidate",
                    description="Candidate-specific proof.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
                Criterion(
                    key="policy",
                    description="Candidate-independent policy proof.",
                    candidate_dependent=False,
                    requires_verdict=False,
                ),
            ),
        ),
    ).snapshot
    dependent_id = UUID("30000000-0000-4000-8000-000000000005")
    independent_id = UUID("30000000-0000-4000-8000-000000000006")
    for evidence_id, criterion_key in (
        (dependent_id, "candidate"),
        (independent_id, "policy"),
    ):
        content = criterion_key.encode()
        snapshot = proof.decide(
            _actor(),
            snapshot,
            RecordEvidence(
                evidence_id=evidence_id,
                criterion_key=criterion_key,
                candidate_digest=first_digest,
                artifact_digest="sha256:" + hashlib.sha256(content).hexdigest(),
                content=content,
            ),
        ).snapshot
    verdict_id = UUID("40000000-0000-4000-8000-000000000002")
    snapshot = proof.decide(
        _actor(REVIEWER_ID, PrincipalKind.OPERATOR),
        snapshot,
        RecordVerdict(
            verdict_id=verdict_id,
            criterion_key="candidate",
            candidate_digest=first_digest,
            decision=VerdictDecision.PASSING,
        ),
    ).snapshot

    changed = proof.decide(
        _actor(), snapshot, ChangeCandidate(candidate_digest="sha256:" + "b" * 64)
    )

    assert changed.accepted is True
    assert changed.invalidated_evidence_ids == (dependent_id,)
    assert changed.invalidated_verdict_ids == (verdict_id,)
    assert independent_id not in changed.snapshot.invalidated_evidence_ids
    assert tuple(item.evidence_id for item in changed.snapshot.evidence) == (
        dependent_id,
        independent_id,
    )
    assert tuple(item.verdict_id for item in changed.snapshot.verdicts) == (verdict_id,)
    assert proof.is_satisfied(changed.snapshot) is False
