"""Immutable server-owned Proof policy snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
from typing import Literal

from ctower_kernel.proof.interface import Criterion

__all__ = ["ProofPolicy"]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REF = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class _PolicyFields:
    workflow_ref: str
    gate_policy_ref: str
    gate_policy_digest: str
    evidence_policy_ref: str
    evidence_policy_digest: str
    criteria: tuple[Criterion, ...]
    reviewer_kind: Literal["operator"]
    self_review_forbidden: bool


@dataclass(frozen=True, slots=True)
class ProofPolicy:
    """Server-owned proof obligations identified by exact Workflow policy pins."""

    _gate_policy_bytes: bytes = field(repr=False)
    _evidence_policy_bytes: bytes = field(repr=False)
    _expected_gate_policy_digest: InitVar[str | None] = None
    _expected_evidence_policy_digest: InitVar[str | None] = None
    workflow_ref: str = field(init=False)
    gate_policy_ref: str = field(init=False)
    gate_policy_digest: str = field(init=False)
    evidence_policy_ref: str = field(init=False)
    evidence_policy_digest: str = field(init=False)
    criteria: tuple[Criterion, ...] = field(init=False)
    reviewer_kind: Literal["operator"] = field(init=False)
    self_review_forbidden: bool = field(init=False)

    def __post_init__(
        self,
        _expected_gate_policy_digest: str | None,
        _expected_evidence_policy_digest: str | None,
    ) -> None:
        gate_bytes = _immutable_bytes("gate", self._gate_policy_bytes)
        evidence_bytes = _immutable_bytes("evidence", self._evidence_policy_bytes)
        gate_digest = _content_digest(gate_bytes)
        evidence_digest = _content_digest(evidence_bytes)
        _verify_expected_digest("gate", gate_digest, _expected_gate_policy_digest)
        _verify_expected_digest("evidence", evidence_digest, _expected_evidence_policy_digest)
        parsed = _parse_policy_fields(
            _mapping_from_bytes("gate", gate_bytes),
            _mapping_from_bytes("evidence", evidence_bytes),
            gate_digest,
            evidence_digest,
        )
        object.__setattr__(self, "workflow_ref", parsed.workflow_ref)
        object.__setattr__(self, "gate_policy_ref", parsed.gate_policy_ref)
        object.__setattr__(self, "gate_policy_digest", parsed.gate_policy_digest)
        object.__setattr__(self, "evidence_policy_ref", parsed.evidence_policy_ref)
        object.__setattr__(self, "evidence_policy_digest", parsed.evidence_policy_digest)
        object.__setattr__(self, "criteria", parsed.criteria)
        object.__setattr__(self, "reviewer_kind", parsed.reviewer_kind)
        object.__setattr__(self, "self_review_forbidden", parsed.self_review_forbidden)
        _validate_policy(self)

    @classmethod
    def from_bytes(
        cls,
        gate_policy_bytes: bytes,
        evidence_policy_bytes: bytes,
        *,
        expected_gate_policy_digest: str | None = None,
        expected_evidence_policy_digest: str | None = None,
    ) -> ProofPolicy:
        """Parse and pin exact immutable policy bytes as one inseparable value."""

        return cls(
            gate_policy_bytes,
            evidence_policy_bytes,
            expected_gate_policy_digest,
            expected_evidence_policy_digest,
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


def _immutable_bytes(kind: str, value: object) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError(f"{kind} policy must be exact immutable bytes")
    return value


def _content_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _verify_expected_digest(kind: str, actual: str, expected: str | None) -> None:
    if expected is None:
        return
    if not isinstance(expected, str) or _DIGEST.fullmatch(expected) is None:
        raise ValueError(f"expected {kind} policy digest must be content addressed")
    if expected != actual:
        raise ValueError(f"{kind} policy digest does not identify supplied bytes")


def _mapping_from_bytes(kind: str, value: bytes) -> Mapping[str, object]:
    try:
        decoded = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{kind} policy bytes must be UTF-8 JSON") from error
    if not isinstance(decoded, Mapping):
        raise TypeError(f"{kind} policy bytes must contain an object")
    return decoded


def _parse_policy_fields(
    gate_policy: Mapping[str, object],
    evidence_policy: Mapping[str, object],
    gate_digest: str,
    evidence_digest: str,
) -> _PolicyFields:
    if gate_policy.get("schema") != "ctower.gate-policy/v1":
        raise ValueError("unsupported gate policy schema")
    if evidence_policy.get("schema") != "ctower.evidence-policy/v1":
        raise ValueError("unsupported evidence policy schema")
    gate_ref = _mapping_ref(gate_policy)
    evidence_ref = _mapping_ref(evidence_policy)
    if gate_policy.get("evidence_policy_ref") != evidence_ref:
        raise ValueError("gate policy evidence reference mismatch")
    _validate_evidence_semantics(evidence_policy)
    protected = gate_policy.get("protected_verdict")
    raw_criteria = gate_policy.get("criteria")
    if not isinstance(protected, Mapping) or not isinstance(raw_criteria, list):
        raise TypeError("gate policy proof obligations must be objects")
    return _PolicyFields(
        workflow_ref=_mapping_string(gate_policy, "workflow_ref"),
        gate_policy_ref=gate_ref,
        gate_policy_digest=gate_digest,
        evidence_policy_ref=evidence_ref,
        evidence_policy_digest=evidence_digest,
        criteria=tuple(_mapping_criterion(item) for item in raw_criteria),
        reviewer_kind=_literal_operator(protected.get("reviewer_kind")),
        self_review_forbidden=protected.get("self_review") == "forbidden",
    )


def _validate_evidence_semantics(evidence_policy: Mapping[str, object]) -> None:
    semantics = (
        evidence_policy.get("digest_algorithm"),
        evidence_policy.get("content_encoding"),
        evidence_policy.get("candidate_binding"),
        evidence_policy.get("corruption_policy"),
        evidence_policy.get("missing_policy"),
    )
    if semantics != ("sha256", "utf-8", "current_digest", "reject", "reject"):
        raise ValueError("evidence policy does not preserve current immutable bytes")


def _validate_policy(policy: ProofPolicy) -> None:
    refs = (policy.workflow_ref, policy.gate_policy_ref, policy.evidence_policy_ref)
    digests = (policy.gate_policy_digest, policy.evidence_policy_digest)
    if any(_REF.fullmatch(item) is None for item in refs):
        raise ValueError("proof policy references must be versioned")
    if any(_DIGEST.fullmatch(item) is None for item in digests):
        raise ValueError("proof policy digests must be content addressed")
    if not policy.criteria or len({item.key for item in policy.criteria}) != len(policy.criteria):
        raise ValueError("proof policy criteria must be nonempty and unique")
    if policy.reviewer_kind != "operator" or not policy.self_review_forbidden:
        raise ValueError("proof policy must require independent operator review")


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
