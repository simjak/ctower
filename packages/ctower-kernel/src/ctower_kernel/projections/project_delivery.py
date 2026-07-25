"""Pure, read-only Project Delivery fold and I1.7 authority-health models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

__all__ = [
    "CheckpointDefinition",
    "CtowerProjectCutoverHealth",
    "DeliveryFacts",
    "DeliveryState",
    "MigrationHealthDigests",
    "ProjectDeliveryRow",
    "ProjectDeliveryView",
    "derive_project_delivery_row",
]

_FRESHNESS_LIMIT = timedelta(hours=1)
_EPOCH = datetime.fromtimestamp(0, UTC)


class DeliveryState(StrEnum):
    """The canonical eight states in increasing maturity order."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    READY_TO_LAND = "ready_to_land"
    MERGED = "merged"
    VERIFIED = "verified"
    RELEASED = "released"
    BLOCKED = "blocked"
    DONE = "done"


_MATURITY_STATES = frozenset(
    {
        DeliveryState.PLANNED,
        DeliveryState.IN_PROGRESS,
        DeliveryState.READY_TO_LAND,
        DeliveryState.MERGED,
        DeliveryState.VERIFIED,
        DeliveryState.RELEASED,
    }
)


@dataclass(frozen=True, slots=True)
class CheckpointDefinition:
    """Versioned checkpoint semantics, never a mutable status row."""

    key: str
    label: str
    outcome: str
    accountable_owner: str
    criteria: tuple[str, ...]
    applicable_states: frozenset[DeliveryState]

    def __post_init__(self) -> None:
        if not self.criteria or len(set(self.criteria)) != len(self.criteria):
            raise ValueError("checkpoint criteria must be nonempty and unique")
        if not {DeliveryState.PLANNED, DeliveryState.DONE} <= self.applicable_states:
            raise ValueError("checkpoint must declare planned and done")
        if not self.applicable_states <= set(DeliveryState):
            raise ValueError("checkpoint declares an unknown delivery state")


@dataclass(frozen=True, slots=True)
class DeliveryFacts:
    """Accepted source facts supplied to the deterministic fold."""

    maturity: DeliveryState
    proven_criteria: frozenset[str]
    effective_blockers: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_watermark: int
    projection_watermark: int
    last_reconciled_at: datetime
    observed_at: datetime
    source_complete: bool
    cp3_d_proven: bool
    durability: str = "CP3_D_NOT_PROVEN"
    recovery: str = "EXTERNAL_FAILURE_DOMAIN_UNPROVEN"
    data_class: str = "RECONSTRUCTIBLE_ONLY"
    rebuild_generation: int = 0

    def __post_init__(self) -> None:
        if self.maturity not in _MATURITY_STATES:
            raise ValueError("underlying maturity cannot be blocked or done")
        if self.source_watermark < 0 or self.projection_watermark < 0:
            raise ValueError("watermarks cannot be negative")
        if self.rebuild_generation < 0:
            raise ValueError("rebuild generation cannot be negative")
        if self.last_reconciled_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("projection times must be timezone-aware")
        if self.observed_at < self.last_reconciled_at:
            raise ValueError("observation cannot precede reconciliation")


@dataclass(frozen=True, slots=True)
class ProjectDeliveryRow:
    """Compact, authorization-safe read row."""

    checkpoint_key: str
    checkpoint_label: str
    headline_state: DeliveryState
    underlying_maturity: DeliveryState
    outcome: str
    accountable_owner: str
    proven_criteria: int
    declared_criteria: int
    source_watermark: int
    projection_watermark: int
    freshness: str
    confidence: str
    health: str
    durability: str
    recovery: str
    data_class: str
    semantic_digest: str
    reconciled_at: datetime
    freshness_due_at: datetime
    rebuild_generation: int
    source_ids: tuple[str, ...]
    derivation_reasons: tuple[str, ...]

    def response_payload(self) -> dict[str, object]:
        return {
            "accountable_owner": self.accountable_owner,
            "checkpoint_key": self.checkpoint_key,
            "checkpoint_label": self.checkpoint_label,
            "confidence": self.confidence,
            "criteria": {
                "declared": self.declared_criteria,
                "proven": self.proven_criteria,
            },
            "derivation_reasons": list(self.derivation_reasons),
            "durability": self.durability,
            "freshness": self.freshness,
            "headline_state": self.headline_state.value,
            "health": self.health,
            "data_class": self.data_class,
            "outcome": self.outcome,
            "projection_watermark": self.projection_watermark,
            "rebuild_generation": self.rebuild_generation,
            "reconciled_at": self.reconciled_at.isoformat(),
            "recovery": self.recovery,
            "semantic_digest": self.semantic_digest,
            "source_ids": list(self.source_ids),
            "source_watermark": self.source_watermark,
            "freshness_due_at": self.freshness_due_at.isoformat(),
            "underlying_maturity": self.underlying_maturity.value,
        }


@dataclass(frozen=True, slots=True)
class ProjectDeliveryView:
    """One company/project hierarchy projection."""

    company_key: str
    project_key: str
    rows: tuple[ProjectDeliveryRow, ...]
    source_record_position: int = 0
    projection_record_position: int = 0
    reconciled_at: datetime = _EPOCH
    freshness_due_at: datetime = _EPOCH
    projection_semantic_digest: str = f"sha256:{'0' * 64}"
    rebuild_generation: int = 0

    def response_payload(self) -> dict[str, object]:
        return {
            "company_key": self.company_key,
            "project_key": self.project_key,
            "source_record_position": self.source_record_position,
            "projection_record_position": self.projection_record_position,
            "reconciled_at": self.reconciled_at.isoformat(),
            "freshness_due_at": self.freshness_due_at.isoformat(),
            "projection_semantic_digest": self.projection_semantic_digest,
            "rebuild_generation": self.rebuild_generation,
            "rows": [row.response_payload() for row in self.rows],
            "schema": "ctower.project-delivery/v1",
        }


@dataclass(frozen=True, slots=True)
class MigrationHealthDigests:
    """Current migration digest pins exposed without credential material."""

    source_selection: str | None = None
    export_equality: str | None = None
    alias_map: str | None = None
    reconciliation: str | None = None
    fence_registry: str | None = None
    fence_observation: str | None = None

    def response_payload(self) -> dict[str, str | None]:
        return {
            "source_selection": self.source_selection,
            "export_equality": self.export_equality,
            "alias_map": self.alias_map,
            "reconciliation": self.reconciliation,
            "fence_registry": self.fence_registry,
            "fence_observation": self.fence_observation,
        }


@dataclass(frozen=True, slots=True)
class CtowerProjectCutoverHealth:
    """Current derived authority boundary; never a write command."""

    cutover_id: UUID | None = None
    authority_mode: str = "legacy_writable"
    phase: str = "not_started"
    writes_enabled: bool = False
    durability_claim: str = "CP3_D_NOT_PROVEN"
    recovery_claim: str = "EXTERNAL_FAILURE_DOMAIN_UNPROVEN"
    data_class: str = "RECONSTRUCTIBLE_ONLY"
    legacy_writer_fence: str = "not_armed"
    split_brain: str = "clear"
    projection_completeness: str = "current"
    source_watermark: int = 0
    projection_watermark: int = 0
    import_run_id: UUID | None = None
    migration_digests: MigrationHealthDigests = MigrationHealthDigests()

    def response_payload(self) -> dict[str, object]:
        return {
            "authority_mode": self.authority_mode,
            "banner": (
                "DEVELOPMENT DOGFOOD — not disaster-safe; do not store credentials, "
                "client data, production authority, incidents, accounting, or "
                "irreplaceable artifacts"
            ),
            "cutover_id": str(self.cutover_id) if self.cutover_id else None,
            "data_class": self.data_class,
            "durability_claim": self.durability_claim,
            "legacy_writer_fence": self.legacy_writer_fence,
            "import_run_id": str(self.import_run_id) if self.import_run_id else None,
            "migration_digests": self.migration_digests.response_payload(),
            "phase": self.phase,
            "projection_completeness": self.projection_completeness,
            "projection_watermark": self.projection_watermark,
            "recovery_claim": self.recovery_claim,
            "schema": "ctower.ctower-project-cutover-health/v1",
            "source_watermark": self.source_watermark,
            "split_brain": self.split_brain,
            "writes_enabled": self.writes_enabled,
        }


def derive_project_delivery_row(
    definition: CheckpointDefinition,
    facts: DeliveryFacts,
) -> ProjectDeliveryRow:
    """Apply proof-aware done/blocked precedence without a writable status."""

    unknown_proof = facts.proven_criteria.difference(definition.criteria)
    if unknown_proof:
        raise ValueError("proof names a criterion absent from the definition")
    proven = tuple(sorted(facts.proven_criteria))
    missing = tuple(sorted(set(definition.criteria).difference(proven)))
    blockers = tuple(sorted(set(facts.effective_blockers)))
    headline = _headline(missing, facts, blockers)
    if headline not in definition.applicable_states and headline is not DeliveryState.BLOCKED:
        raise ValueError("facts name a lifecycle state absent from the checkpoint")
    freshness, confidence, health = _health(facts)
    durability, recovery, data_class = _claims(facts)
    reasons = _derivation_reasons(proven, missing, blockers, facts)
    semantic = _semantic_digest(
        definition,
        facts,
        headline,
        proven,
        reasons,
        durability,
        recovery,
        data_class,
    )
    return ProjectDeliveryRow(
        checkpoint_key=definition.key,
        checkpoint_label=definition.label,
        headline_state=headline,
        underlying_maturity=facts.maturity,
        outcome=definition.outcome,
        accountable_owner=definition.accountable_owner,
        proven_criteria=len(proven),
        declared_criteria=len(definition.criteria),
        source_watermark=facts.source_watermark,
        projection_watermark=facts.projection_watermark,
        freshness=freshness,
        confidence=confidence,
        health=health,
        durability=durability,
        recovery=recovery,
        data_class=data_class,
        semantic_digest=semantic,
        reconciled_at=facts.last_reconciled_at,
        freshness_due_at=facts.last_reconciled_at + _FRESHNESS_LIMIT,
        rebuild_generation=facts.rebuild_generation,
        source_ids=tuple(sorted(set(facts.source_ids))),
        derivation_reasons=reasons,
    )


def _headline(
    missing: tuple[str, ...],
    facts: DeliveryFacts,
    blockers: tuple[str, ...],
) -> DeliveryState:
    """Resolve the visible headline, failing closed away from `done`.

    `done` requires every declared criterion proven AND a complete source AND
    no open effective blocker AND (for the development dogfood checkpoint) a
    proven CP3-D. An unproven CP3-D is itself an effective blocker
    (SPEC "Project Delivery projection"), so it forces `blocked` even when a
    caller forgets to declare it. A gapped source likewise cannot host `done`;
    the visible headline fails closed to `blocked` while the underlying maturity
    is retained in `derivation_reasons`.
    """

    complete = not missing
    if complete and facts.source_complete and not blockers and facts.cp3_d_proven:
        return DeliveryState.DONE
    if blockers or not facts.source_complete or not facts.cp3_d_proven:
        return DeliveryState.BLOCKED
    return facts.maturity


def _derivation_reasons(
    proven: tuple[str, ...],
    missing: tuple[str, ...],
    blockers: tuple[str, ...],
    facts: DeliveryFacts,
) -> tuple[str, ...]:
    reasons: list[str] = [
        *(f"criterion_current:{item}" for item in proven),
        *(f"criterion_missing:{item}" for item in missing),
        *(f"effective_blocker:{item}" for item in blockers),
    ]
    if not facts.cp3_d_proven:
        reasons.append("cp3_d_unproven")
    if not facts.source_complete:
        reasons.append("source_incomplete")
    reasons.append(f"underlying_maturity:{facts.maturity.value}")
    return tuple(reasons)


def _health(facts: DeliveryFacts) -> tuple[str, str, str]:
    if not facts.source_complete or facts.source_watermark != facts.projection_watermark:
        return "STATE_UNKNOWN", "STATE_UNKNOWN", "STATE_UNKNOWN"
    freshness = (
        "stale" if facts.observed_at - facts.last_reconciled_at > _FRESHNESS_LIMIT else "fresh"
    )
    if facts.cp3_d_proven:
        return freshness, "disaster_safe", "CURRENT"
    return freshness, "development_degraded", "CP3_D_NOT_PROVEN"


def _claims(facts: DeliveryFacts) -> tuple[str, str, str]:
    if not facts.source_complete or facts.source_watermark != facts.projection_watermark:
        return "STATE_UNKNOWN", "STATE_UNKNOWN", "STATE_UNKNOWN"
    return facts.durability, facts.recovery, facts.data_class


def _semantic_digest(
    definition: CheckpointDefinition,
    facts: DeliveryFacts,
    headline: DeliveryState,
    proven: tuple[str, ...],
    reasons: tuple[str, ...],
    durability: str,
    recovery: str,
    data_class: str,
) -> str:
    payload = {
        "accountable_owner": definition.accountable_owner,
        "checkpoint_key": definition.key,
        "criteria": {"declared": len(definition.criteria), "proven": len(proven)},
        "data_class": data_class,
        "derivation_reasons": reasons,
        "durability": durability,
        "headline_state": headline.value,
        "projection_watermark": facts.projection_watermark,
        "recovery": recovery,
        "source_ids": tuple(sorted(set(facts.source_ids))),
        "source_watermark": facts.source_watermark,
        "underlying_maturity": facts.maturity.value,
    }
    content = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
