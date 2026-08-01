"""Pure proof-aware Project Delivery fold for the I1.7A boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from ctower_kernel.projections import (
    CheckpointDefinition,
    DeliveryFacts,
    DeliveryState,
    derive_project_delivery_row,
)
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.projections.project_delivery import EvidenceSlotFact, EvidenceSlotState

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


def test_qualifying_stage_slots_preserve_filled_unfilled_and_unknown_facts() -> None:
    ticket_ids = tuple(uuid4() for _ in range(4))
    criteria: list[dict[str, object]] = [
        {
            "criterion_key": checkpoint_key,
            "proof_ticket_id": ticket_id,
            "proof_criterion_key": proof_key,
            "source_ids": [],
        }
        for checkpoint_key, ticket_id, proof_key in (
            ("checkpoint-alpha", ticket_ids[0], "alpha"),
            ("checkpoint-beta", ticket_ids[1], "beta"),
            ("checkpoint-delta", ticket_ids[2], "delta"),
            ("checkpoint-epsilon", ticket_ids[3], "epsilon"),
        )
    ]
    criteria.append(
        {
            "criterion_key": "unlinked-checkpoint-proof",
            "proof_ticket_id": None,
            "proof_criterion_key": None,
            "source_ids": [],
        }
    )
    # One row per configured link, carrying the two facts that may make a slot genuinely
    # unestablishable beside the shared two-valued predicate. Behaviour against a real
    # database is proven by tests/acceptance/increment-1/test_project_delivery_evidence.py.
    slot_rows: list[dict[str, object]] = [
        _link_row(ticket_ids[0], "alpha", proven=True),
        _link_row(ticket_ids[1], "beta", proven=False),
        _link_row(ticket_ids[2], "delta", stage_present=False),
        _link_row(ticket_ids[3], "epsilon", criterion_present=False),
    ]
    connection, connect_context = _reconcile_connection(criteria, slot_rows)
    with patch.object(psycopg, "connect", return_value=connect_context):
        affected = PostgresProjections("postgresql://projection").reconcile_project_delivery(
            uuid4(),
            now=datetime(2026, 7, 30, 12, tzinfo=UTC),
        )

    assert affected == 1
    payload = _stored_payload(connection)
    assert payload["qualifying_stage_slots_filled"] == 1
    assert payload["qualifying_stage_slots_required"] == len(criteria)
    assert payload["qualifying_stage_unfilled_or_unknown_slot_keys"] == [
        "beta",
        "delta",
        "epsilon",
        "unlinked-checkpoint-proof",
    ]
    assert {
        "slot_filled:alpha",
        "slot_unfilled:beta",
        "slot_unknown:delta",
        "slot_unknown:epsilon",
        "slot_unknown:unlinked-checkpoint-proof",
    } <= set(cast(list[str], payload["derivation_reasons"]))
    tickets, proof_keys = _slot_request(connection)
    assert list(zip(tickets, proof_keys, strict=True)) == [
        (ticket_ids[0], "alpha"),
        (ticket_ids[1], "beta"),
        (ticket_ids[2], "delta"),
        (ticket_ids[3], "epsilon"),
    ]


def _link_row(
    ticket_id: UUID,
    proof_key: str,
    *,
    criterion_present: bool = True,
    stage_present: bool = True,
    proven: bool = False,
) -> dict[str, object]:
    return {
        "ticket_id": ticket_id,
        "proof_key": proof_key,
        "project_present": True,
        "criterion_present": criterion_present,
        "stage_present": stage_present,
        "proven": proven,
    }


def _reconcile_connection(
    criteria: list[dict[str, object]],
    slot_rows: list[dict[str, object]],
) -> tuple[MagicMock, MagicMock]:
    event_id = uuid4()
    definition = {
        "event_id": event_id,
        "project_key": "fixture-project",
        "checkpoint_definition_id": uuid4(),
        "checkpoint_key": "fixture-checkpoint",
        "checkpoint_label": "Fixture checkpoint",
        "outcome": "Fixture outcome",
        "accountable_owner": "fixture-owner",
        "applicable_states": [state.value for state in DeliveryState],
        "catalog_revision": "fixture-revision",
    }
    results = [
        _result(),
        _result(),
        _result(),
        _result(rows=[{"event_id": event_id}]),
        _result(rows=[definition]),
        _result(rowcount=0),
        _result(row={"value": 10}),
        _result(rows=[{"minimum": 1, "maximum": 10, "count": 10}]),
        _result(
            row={
                "acceptance_position": 10,
                "health": "CURRENT",
                "blocked_outbox_id": None,
            }
        ),
        _result(rows=[{"event_id": event_id}]),
        _result(row={"value": 0}),
        _result(row=None),
        _result(row={"due": None}),
        _result(rows=criteria),
        _result(rows=slot_rows),
        _result(
            rows=[
                {
                    "ticket_id": criteria[0]["proof_ticket_id"],
                    "lane": "complete",
                    "delivery_facts": ["staging_verified"],
                }
            ]
        ),
        _result(rows=[]),
        _result(rowcount=1),
        _result(),
    ]
    connection = MagicMock()
    connection.execute.side_effect = results
    connection.info.transaction_status = psycopg.pq.TransactionStatus.IDLE
    connection.autocommit = True
    connection.closed = False
    context = MagicMock()
    context.__enter__.return_value = connection
    return connection, context


def _result(
    *,
    row: dict[str, object] | None = None,
    rows: list[dict[str, object]] | None = None,
    rowcount: int = 0,
) -> Mock:
    result = Mock()
    result.fetchone.return_value = row
    result.fetchall.return_value = [] if rows is None else rows
    result.rowcount = rowcount
    return result


def _stored_payload(connection: MagicMock) -> dict[str, object]:
    call = next(
        item
        for item in connection.execute.call_args_list
        if "INSERT INTO project_delivery_projection_rows" in item.args[0]
    )
    params = cast(tuple[object, object, object, object], call.args[1])
    return cast(dict[str, object], cast(Jsonb, params[3]).obj)


def _slot_request(connection: MagicMock) -> tuple[list[UUID], list[str]]:
    """Recover the configured (ticket, proof key) links the slot query asked for."""

    call = next(
        item
        for item in connection.execute.call_args_list
        if "FROM unnest(%s::uuid[], %s::text[])" in item.args[0]
    )
    tickets, proof_keys, *_ = cast(
        tuple[list[UUID], list[str], object, object, object, object], call.args[1]
    )
    return tickets, proof_keys


def test_explicit_criteria_and_blockers_drive_done_without_checkpoint_special_cases() -> None:
    facts = _facts()
    row = derive_project_delivery_row(_definition(), facts)

    assert row.headline_state is DeliveryState.BLOCKED
    assert row.underlying_maturity is DeliveryState.VERIFIED
    assert (row.proven_criteria, row.declared_criteria) == (5, 6)
    assert (
        row.qualifying_stage_slots_filled,
        row.qualifying_stage_slots_required,
    ) == (1, 3)
    assert row.qualifying_stage_unfilled_or_unknown_slot_keys == (
        "approval-receipt",
        "archive-proof",
    )
    assert row.confidence == "development_degraded"
    assert row.health == "CP3_D_NOT_PROVEN"
    assert "criterion_missing:cp3_d" in row.derivation_reasons
    assert "effective_blocker:cp3_d" in row.derivation_reasons
    assert "slot_unfilled:approval-receipt" in row.derivation_reasons
    assert "slot_unknown:archive-proof" in row.derivation_reasons

    complete = derive_project_delivery_row(
        _definition(),
        replace(
            facts,
            proven_criteria=frozenset(_CRITERIA),
            effective_blockers=(),
            qualifying_stage_slots=tuple(
                replace(slot, state=EvidenceSlotState.FILLED)
                for slot in facts.qualifying_stage_slots
            ),
        ),
    )
    assert complete.headline_state is DeliveryState.DONE
    assert complete.confidence == "development_degraded"
    assert complete.health == "CP3_D_NOT_PROVEN"
    assert complete.qualifying_stage_unfilled_or_unknown_slot_keys == ()


def test_row_slot_coverage_never_comes_back_from_rendered_reasons() -> None:
    rendered = derive_project_delivery_row(_definition(), _facts())
    assert {"slot_unfilled:approval-receipt", "slot_unknown:archive-proof"} <= set(
        rendered.derivation_reasons
    )

    # A checkpoint that configures no qualifying-stage slot keeps its reasons; the
    # read path must publish the coverage it was given, never one recovered by
    # matching a slot name inside those rendered strings.
    unconfigured = replace(
        rendered,
        qualifying_stage_slots_filled=0,
        qualifying_stage_slots_required=0,
        qualifying_stage_unfilled_or_unknown_slot_keys=(),
    )

    assert (
        unconfigured.qualifying_stage_slots_filled,
        unconfigured.qualifying_stage_slots_required,
        unconfigured.qualifying_stage_unfilled_or_unknown_slot_keys,
    ) == (0, 0, ())
    payload = unconfigured.response_payload()
    assert payload["qualifying_stage_slots_filled"] == 0
    assert payload["qualifying_stage_slots_required"] == 0
    assert payload["qualifying_stage_unfilled_or_unknown_slot_keys"] == []


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
        "all_explicit_criteria_proven_with_degraded_durability",
        lambda facts: replace(
            facts,
            proven_criteria=frozenset(_CRITERIA),
            effective_blockers=(),
        ),
        None,
        DeliveryState.DONE,
        set(),
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
        "fully_done_when_source_complete_no_blockers",
        lambda facts: replace(
            facts,
            proven_criteria=frozenset(_CRITERIA),
            effective_blockers=(),
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
def test_fold_never_publishes_done_over_unproven_gapped_or_blocked_explicit_facts(
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
        assert row.confidence == "development_degraded"
        assert row.health == "CP3_D_NOT_PROVEN"
    elif facts.source_complete is False:
        assert row.freshness == "STATE_UNKNOWN"
        assert row.confidence == "STATE_UNKNOWN"
        assert row.health == "STATE_UNKNOWN"


def _definition() -> CheckpointDefinition:
    return CheckpointDefinition(
        key="Q3-close.2",
        label="Quarter close approval",
        outcome="The quarter close is approved and archived",
        accountable_owner="controller",
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
        qualifying_stage_slots=(
            EvidenceSlotFact("ledger-posted", EvidenceSlotState.FILLED),
            EvidenceSlotFact("approval-receipt", EvidenceSlotState.UNFILLED),
            EvidenceSlotFact("archive-proof", EvidenceSlotState.UNKNOWN),
        ),
    )
