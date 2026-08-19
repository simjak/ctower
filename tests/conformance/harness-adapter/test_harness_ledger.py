"""AC-HAD-12 — the ledger and the generated configuration stay faithful to what happened.

Tokens are what the model consumed; credits are what the subscription paid. Only the second
answers "which model on which account drained this plan", and the two differ by far more
than a constant factor because providers weight per model and per direction. Everything else
here exists to make resilience visibly expensive rather than invisibly expensive.
"""

from __future__ import annotations

import pytest
from harness_doubles import BASE_TIME
from harness_subjects import build_hermes

from ctower_runner_sdk.credits import MTOK, ModelWeight, SpendRow, TokenUsage, WeightTable
from ctower_runner_sdk.ledger import (
    FALLBACK_CONTEXT_REREADS,
    ROTATION_CONTEXT_REREADS,
    TurnLedger,
    bypasses_explicit_provider,
)
from ctower_runner_sdk.refusals import Refusal

__all__: tuple[str, ...] = ()

_REVISION = 1
_WEIGHT_SPREAD = 25

# The operator's own dashboard figures: sol output is 25x luna output, which is exactly the
# ratio a token-counting ledger cannot see.
_WEIGHTS = (
    ModelWeight("openai-codex", "gpt-5.6-sol", 125_000, 12_500, 750_000),
    ModelWeight("openai-codex", "gpt-5.6-luna", 5_000, 500, 30_000),
)
_TABLE = WeightTable.from_rows(_REVISION, _WEIGHTS)


def _price(model_ref: str, tokens: TokenUsage, *, task_class: str = "main") -> SpendRow | Refusal:
    return _TABLE.price(
        model_ref=model_ref,
        subscription_identity="seat-one@example.test",
        task_class=task_class,
        tokens=tokens,
        expected_revision=_REVISION,
    )


def test_the_weight_spread_is_the_thing_a_token_count_cannot_see() -> None:
    sol, luna = _WEIGHTS

    assert sol.output_millicredits_per_mtok == luna.output_millicredits_per_mtok * _WEIGHT_SPREAD


def test_a_low_token_expensive_lane_outranks_a_high_token_cheap_one() -> None:
    expensive = _price("gpt-5.6-sol", TokenUsage(0, 0, 100_000))
    cheap = _price("gpt-5.6-luna", TokenUsage(0, 0, 1_000_000))

    assert not isinstance(expensive, Refusal)
    assert not isinstance(cheap, Refusal)
    assert expensive.millicredits > cheap.millicredits
    assert expensive.tokens.total() < cheap.tokens.total()


def test_credits_are_attributed_by_model_and_account_beside_the_raw_counts() -> None:
    row = _price("gpt-5.6-sol", TokenUsage(1_000_000, 0, 0))

    assert not isinstance(row, Refusal)
    assert row.millicredits == _WEIGHTS[0].input_millicredits_per_mtok
    assert row.to_mapping()["subscription_identity"] == "seat-one@example.test"
    assert row.to_mapping()["input_tokens"] == MTOK


def test_cached_input_is_priced_at_its_own_rate_and_not_at_the_fresh_one() -> None:
    fresh = _price("gpt-5.6-sol", TokenUsage(MTOK, 0, 0))
    cached = _price("gpt-5.6-sol", TokenUsage(0, MTOK, 0))

    assert not isinstance(fresh, Refusal)
    assert not isinstance(cached, Refusal)
    assert cached.millicredits < fresh.millicredits


def test_a_stale_weight_table_refuses_rather_than_silently_mispricing() -> None:
    refusal = _TABLE.price(
        model_ref="gpt-5.6-sol",
        subscription_identity=None,
        task_class="main",
        tokens=TokenUsage(1, 0, 0),
        expected_revision=_REVISION + 1,
    )

    assert isinstance(refusal, Refusal)
    assert refusal.name == "weight-table-unavailable"


def test_a_missing_weight_row_refuses_rather_than_pricing_at_zero() -> None:
    refusal = _price("a-model-nobody-priced", TokenUsage(1, 0, 0))

    assert isinstance(refusal, Refusal)
    assert refusal.name == "weight-table-unavailable"


def test_aux_spend_is_attributed_separately_from_the_main_line() -> None:
    main = _price("gpt-5.6-sol", TokenUsage(MTOK, 0, 0))
    aux = _price("gpt-5.6-luna", TokenUsage(MTOK, 0, 0), task_class="compression")

    assert not isinstance(main, Refusal)
    assert not isinstance(aux, Refusal)
    assert main.task_class != aux.task_class


def test_a_rotation_costs_one_context_reread_and_a_fallback_costs_two() -> None:
    ledger = TurnLedger()

    rotation = ledger.rotation(
        turn_id="turn-1", entry_identity="seat-two@example.test", at=BASE_TIME
    )
    fallback = ledger.fallback(turn_id="turn-1", provider_key="zai", at=BASE_TIME)

    assert rotation.context_rereads == ROTATION_CONTEXT_REREADS
    assert fallback is not None
    assert fallback.context_rereads == FALLBACK_CONTEXT_REREADS
    assert ledger.context_rereads() == ROTATION_CONTEXT_REREADS + FALLBACK_CONTEXT_REREADS


def test_a_same_provider_rotation_is_never_recorded_as_a_cross_provider_fallback() -> None:
    ledger = TurnLedger()

    rotation = ledger.rotation(
        turn_id="turn-1", entry_identity="seat-two@example.test", at=BASE_TIME
    )
    fallback = ledger.fallback(turn_id="turn-2", provider_key="zai", at=BASE_TIME)

    assert rotation.layer == "pool"
    assert fallback is not None
    assert fallback.layer == "fallback"


def test_a_fallback_is_turn_scoped_and_never_a_mode_the_seat_is_in() -> None:
    ledger = TurnLedger()

    first = ledger.fallback(turn_id="turn-1", provider_key="zai", at=BASE_TIME)
    again = ledger.fallback(turn_id="turn-1", provider_key="zai", at=BASE_TIME)
    next_turn = ledger.fallback(turn_id="turn-2", provider_key="zai", at=BASE_TIME)

    assert first is not None
    assert again is None
    assert next_turn is not None
    assert [event.turn_id for event in ledger.events] == ["turn-1", "turn-2"]


def test_a_skipped_retry_is_an_explicit_fact_and_not_an_absence() -> None:
    ledger = TurnLedger()

    event = ledger.retry_skipped(turn_id="turn-1", reset_at=BASE_TIME, at=BASE_TIME)

    assert event.kind == "retry_skipped"
    assert "did not retry primary" in event.detail
    assert event.context_rereads == 0


def test_a_compression_degradation_is_a_recorded_quality_event() -> None:
    ledger = TurnLedger()

    event = ledger.degradation(
        turn_id="turn-1", detail="compression degraded to no-summary", at=BASE_TIME
    )

    assert event.kind == "degradation"
    assert event.to_mapping()["detail"] == "compression degraded to no-summary"


@pytest.mark.parametrize(
    ("error_code", "bypasses"),
    (("402", True), ("daily-quota", True), ("connection", True), ("429", False), ("503", False)),
)
def test_a_capacity_error_bypasses_an_explicit_provider_and_a_transient_one_respects_it(
    error_code: str, *, bypasses: bool
) -> None:
    assert bypasses_explicit_provider(error_code) is bypasses


def test_the_generated_ladder_is_authored_config_and_no_environment_variable_can_alter_it() -> None:
    spec = build_hermes().binding.spec

    assert spec.survey.config_surface == "authored_config_only"
    assert spec.config_digest.startswith("sha256:")


def test_the_binding_never_writes_the_engines_own_auth_state() -> None:
    pool = build_hermes().pool
    verbs = {name for name in dir(pool) if not name.startswith("_")}

    assert not [name for name in verbs if "write" in name or "auth" in name]
    assert "limits" in verbs
