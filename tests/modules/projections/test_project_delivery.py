"""Pure proof-aware Project Delivery fold for the I1.7A boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ctower_kernel.projections import (
    CheckpointDefinition,
    DeliveryFacts,
    DeliveryState,
    derive_project_delivery_row,
)

__all__: tuple[str, ...] = ()

_CRITERIA = (
    "authority_decision",
    "contracts",
    "append_only_storage",
    "read_only_projection",
    "development_dogfood",
    "cp3_d",
)
_REBUILD_GENERATION = 7


def test_i17_retains_verified_maturity_but_cp3_d_blocks_done() -> None:
    facts = _facts()
    row = derive_project_delivery_row(_definition(), facts)

    assert row.headline_state is DeliveryState.BLOCKED
    assert row.underlying_maturity is DeliveryState.VERIFIED
    assert (row.proven_criteria, row.declared_criteria) == (5, 6)
    assert row.confidence == "development_degraded"
    assert row.health == "CP3_D_NOT_PROVEN"
    assert "criterion_missing:cp3_d" in row.derivation_reasons
    assert "effective_blocker:cp3_d" in row.derivation_reasons

    complete = derive_project_delivery_row(
        _definition(),
        replace(
            facts,
            proven_criteria=frozenset(_CRITERIA),
            effective_blockers=(),
            cp3_d_proven=True,
        ),
    )
    assert complete.headline_state is DeliveryState.DONE
    assert complete.confidence == "disaster_safe"


def test_health_faults_are_loud_without_moving_lifecycle_or_proof() -> None:
    facts = _facts()
    current = derive_project_delivery_row(_definition(), facts)
    heartbeat = derive_project_delivery_row(
        _definition(),
        replace(facts, observed_at=facts.observed_at + timedelta(minutes=59)),
    )
    stale = derive_project_delivery_row(
        _definition(),
        replace(facts, observed_at=facts.observed_at + timedelta(hours=2)),
    )
    unknown = derive_project_delivery_row(
        _definition(),
        replace(facts, projection_watermark=26),
    )

    assert heartbeat.headline_state is current.headline_state
    assert heartbeat.derivation_reasons == current.derivation_reasons
    assert stale.headline_state is DeliveryState.BLOCKED
    assert stale.freshness == "stale"
    assert unknown.health == "STATE_UNKNOWN"
    assert unknown.confidence == "STATE_UNKNOWN"


def test_semantic_digest_excludes_heartbeat_generation_and_wording() -> None:
    first = derive_project_delivery_row(_definition(), _facts())
    heartbeat_at = _facts().last_reconciled_at + timedelta(hours=2)
    heartbeat = derive_project_delivery_row(
        replace(_definition(), label="Reworded label", outcome="Reworded outcome"),
        replace(
            _facts(),
            last_reconciled_at=heartbeat_at,
            observed_at=heartbeat_at,
            rebuild_generation=_REBUILD_GENERATION,
        ),
    )

    assert heartbeat.semantic_digest == first.semantic_digest
    assert heartbeat.source_ids == first.source_ids
    assert heartbeat.derivation_reasons == first.derivation_reasons
    assert heartbeat.rebuild_generation == _REBUILD_GENERATION


def test_fold_rejects_zero_criteria_unknown_proof_and_invalid_time() -> None:
    definition = _definition()
    with pytest.raises(ValueError, match="nonempty"):
        replace(definition, criteria=())
    with pytest.raises(ValueError, match="absent"):
        derive_project_delivery_row(
            definition,
            replace(_facts(), proven_criteria=frozenset({"invented"})),
        )
    with pytest.raises(ValueError, match="precede"):
        replace(
            _facts(),
            observed_at=datetime(2026, 7, 25, 9, tzinfo=UTC),
        )


type _FactsOverride = Callable[[DeliveryFacts], DeliveryFacts]

_DONE_GATE_CASES: tuple[
    tuple[str, _FactsOverride, tuple[str, ...] | None, DeliveryState, set[str]], ...
] = (
    (
        "cp3_d_unproven_even_when_criterion_reported_proven",
        lambda facts: replace(facts, proven_criteria=frozenset(_CRITERIA)),
        None,
        DeliveryState.BLOCKED,
        {"cp3_d_unproven", "effective_blocker:cp3_d"},
    ),
    (
        "cp3_d_omitted_from_definition_but_still_unproven",
        lambda facts: replace(facts, proven_criteria=frozenset(_CRITERIA[:-1])),
        _CRITERIA[:-1],
        DeliveryState.BLOCKED,
        {"cp3_d_unproven", "effective_blocker:cp3_d"},
    ),
    (
        "effective_blockers_open_with_full_proof_and_cp3_proven",
        lambda facts: replace(
            facts,
            proven_criteria=frozenset(_CRITERIA),
            effective_blockers=("legacy_writer_unfenced", "split_brain_detected"),
            cp3_d_proven=True,
        ),
        None,
        DeliveryState.BLOCKED,
        {"effective_blocker:legacy_writer_unfenced", "effective_blocker:split_brain_detected"},
    ),
    (
        "source_incomplete_with_full_proof_cp3_proven_no_blockers",
        lambda facts: replace(
            facts,
            proven_criteria=frozenset(_CRITERIA),
            effective_blockers=(),
            cp3_d_proven=True,
            source_complete=False,
        ),
        None,
        DeliveryState.BLOCKED,
        {"source_incomplete"},
    ),
    (
        "fully_done_when_source_complete_no_blockers_cp3_proven",
        lambda facts: replace(
            facts,
            proven_criteria=frozenset(_CRITERIA),
            effective_blockers=(),
            cp3_d_proven=True,
            source_complete=True,
        ),
        None,
        DeliveryState.DONE,
        set(),
    ),
)


@pytest.mark.parametrize(
    ("label", "apply_facts", "criteria_override", "expected_headline", "expected_reasons"),
    _DONE_GATE_CASES,
)
def test_fold_never_publishes_done_over_unproven_gapped_or_blocked_sources(
    label: str,
    apply_facts: _FactsOverride,
    criteria_override: tuple[str, ...] | None,
    expected_headline: DeliveryState,
    expected_reasons: set[str],
) -> None:
    del label
    definition = _definition()
    if criteria_override is not None:
        definition = replace(definition, criteria=criteria_override)
    facts = apply_facts(_facts())

    row = derive_project_delivery_row(definition, facts)

    assert row.headline_state is expected_headline
    assert row.underlying_maturity is facts.maturity
    assert expected_reasons <= set(row.derivation_reasons)
    if expected_headline is DeliveryState.DONE:
        assert row.confidence == "disaster_safe"
        assert row.health == "CURRENT"
    elif facts.source_complete is False:
        assert row.freshness == "STATE_UNKNOWN"
        assert row.confidence == "STATE_UNKNOWN"
        assert row.health == "STATE_UNKNOWN"


def _definition() -> CheckpointDefinition:
    return CheckpointDefinition(
        key="I1.7",
        label="Development dogfood cutover",
        outcome="ctower owns reviewed reconstructible engineering work",
        accountable_owner="operator",
        criteria=_CRITERIA,
        applicable_states=frozenset(DeliveryState),
    )


def _facts() -> DeliveryFacts:
    return DeliveryFacts(
        maturity=DeliveryState.VERIFIED,
        proven_criteria=frozenset(_CRITERIA[:-1]),
        effective_blockers=("cp3_d",),
        source_ids=("mission-control:i1.7", "ctower:CT-I1-007"),
        source_watermark=27,
        projection_watermark=27,
        last_reconciled_at=datetime(2026, 7, 25, 10, tzinfo=UTC),
        observed_at=datetime(2026, 7, 25, 10, 30, tzinfo=UTC),
        source_complete=True,
        cp3_d_proven=False,
    )
