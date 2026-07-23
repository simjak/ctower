"""Immutable server-owned Proof policy snapshots."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from ctower_kernel.proof.interface import Criterion

__all__ = ["ProofPolicy"]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REF = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class ProofPolicy:
    """Server-owned proof obligations identified by exact Workflow policy pins."""

    workflow_ref: str
    gate_policy_ref: str
    gate_policy_digest: str
    evidence_policy_ref: str
    evidence_policy_digest: str
    criteria: tuple[Criterion, ...]
    reviewer_kind: Literal["operator"]
    self_review_forbidden: bool

    def __post_init__(self) -> None:
        refs = (self.workflow_ref, self.gate_policy_ref, self.evidence_policy_ref)
        digests = (self.gate_policy_digest, self.evidence_policy_digest)
        if any(_REF.fullmatch(item) is None for item in refs):
            raise ValueError("proof policy references must be versioned")
        if any(_DIGEST.fullmatch(item) is None for item in digests):
            raise ValueError("proof policy digests must be content addressed")
        if not self.criteria or len({item.key for item in self.criteria}) != len(self.criteria):
            raise ValueError("proof policy criteria must be nonempty and unique")
        if self.reviewer_kind != "operator" or not self.self_review_forbidden:
            raise ValueError("proof policy must require independent operator review")

    @classmethod
    def from_mappings(
        cls,
        gate_policy: Mapping[str, object],
        evidence_policy: Mapping[str, object],
        *,
        gate_policy_digest: str,
        evidence_policy_digest: str,
    ) -> ProofPolicy:
        """Build one strict policy from the same immutable bytes whose digests are pinned."""

        if gate_policy.get("schema") != "ctower.gate-policy/v1":
            raise ValueError("unsupported gate policy schema")
        if evidence_policy.get("schema") != "ctower.evidence-policy/v1":
            raise ValueError("unsupported evidence policy schema")
        gate_ref = _mapping_ref(gate_policy)
        evidence_ref = _mapping_ref(evidence_policy)
        if gate_policy.get("evidence_policy_ref") != evidence_ref:
            raise ValueError("gate policy evidence reference mismatch")
        if (
            evidence_policy.get("digest_algorithm"),
            evidence_policy.get("content_encoding"),
            evidence_policy.get("candidate_binding"),
            evidence_policy.get("corruption_policy"),
            evidence_policy.get("missing_policy"),
        ) != ("sha256", "utf-8", "current_digest", "reject", "reject"):
            raise ValueError("evidence policy does not preserve current immutable bytes")
        protected = gate_policy.get("protected_verdict")
        raw_criteria = gate_policy.get("criteria")
        if not isinstance(protected, Mapping) or not isinstance(raw_criteria, list):
            raise TypeError("gate policy proof obligations must be objects")
        return cls(
            workflow_ref=_mapping_string(gate_policy, "workflow_ref"),
            gate_policy_ref=gate_ref,
            gate_policy_digest=gate_policy_digest,
            evidence_policy_ref=evidence_ref,
            evidence_policy_digest=evidence_policy_digest,
            criteria=tuple(_mapping_criterion(item) for item in raw_criteria),
            reviewer_kind=_literal_operator(protected.get("reviewer_kind")),
            self_review_forbidden=protected.get("self_review") == "forbidden",
        )

    @property
    def pin(self) -> tuple[str, str, str, str, str]:
        """Return the immutable Workflow/policy identity used for catalog lookup."""

        return (
            self.workflow_ref,
            self.gate_policy_ref,
            self.gate_policy_digest,
            self.evidence_policy_ref,
            self.evidence_policy_digest,
        )


def _mapping_ref(payload: Mapping[str, object]) -> str:
    key = _mapping_string(payload, "key")
    revision = payload.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("policy revision must be positive")
    return f"{key}@{revision}"


def _mapping_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"policy {key} must be nonempty")
    return value


def _mapping_criterion(value: object) -> Criterion:
    if not isinstance(value, Mapping):
        raise TypeError("gate policy criterion must be an object")
    candidate_dependent = value.get("candidate_dependent")
    requires_verdict = value.get("requires_verdict")
    if not isinstance(candidate_dependent, bool) or not isinstance(requires_verdict, bool):
        raise TypeError("gate policy criterion flags must be boolean")
    return Criterion(
        key=_mapping_string(value, "key"),
        description=_mapping_string(value, "description"),
        candidate_dependent=candidate_dependent,
        requires_verdict=requires_verdict,
    )


def _literal_operator(value: object) -> Literal["operator"]:
    if value != "operator":
        raise ValueError("protected verdict reviewer must be operator")
    return "operator"
