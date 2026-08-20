"""Codex route identity, registration, and dispatch evidence acceptance tests."""

from __future__ import annotations

import dataclasses

import pytest
from _codex_fixtures import (
    _ARTIFACT,
    _CONFIG,
    _HEALTHY,
    _PROFILE,
    _SEAT,
    _attempt,
    _binding,
    _document,
    _Guard,
    _healthy_pane,
    _hermes_spec,
    _registration_route,
    _spawn,
    _spawn_attempt,
    _spec,
    _Supervisor,
    _unanswered,
)

from ctower_runner.codex.binding import CODEX_PROBE, CODEX_WRAPPER
from ctower_runner.codex.route import classify_route, mint_refusal
from ctower_runner.codex.spec import CODEX_KEY
from ctower_runner.hermes.spec import harness_spec_document as hermes_spec_document
from ctower_runner_sdk.facts import LivenessFact
from ctower_runner_sdk.guard import ExecutionPlan
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.registry import HarnessRegistry
from ctower_runner_sdk.survey import derive_roles

__all__: tuple[str, ...] = ()

# --- AC-HAD-01: the survey and `never both`, on both codex classes -------------------------


def test_the_direct_cli_derives_provide_on_both_layers_from_its_own_answers() -> None:
    spec = _spec()

    assert derive_roles(spec.survey) == spec.layers
    assert spec.layers.to_mapping() == {"pool": "provide", "fallback": "provide"}
    assert not spec.survey.native_pool
    assert not spec.survey.native_fallback


def test_the_routed_runtime_derives_configure_from_the_survey_of_the_harness_running_it() -> None:
    route = classify_route(runtime_ref="codex", spec=_hermes_spec())

    assert route.route_class == "runtime_under_harness"
    assert route.layers.to_mapping() == {"pool": "configure", "fallback": "configure"}
    assert route.harness_ref == "hermes"


@pytest.mark.parametrize(
    "layers",
    ({"pool": "configure", "fallback": "provide"}, {"pool": "provide", "fallback": "configure"}),
    ids=("pool", "fallback"),
)
def test_declaring_configure_over_a_layer_the_direct_cli_lacks_is_refused(
    layers: dict[str, str],
) -> None:
    refusal = HarnessRegistry().register(
        _document({"layers": layers}), "real", route=_registration_route()
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-layer-conflict"


def test_declaring_provide_over_the_routed_runtimes_hosted_pool_is_refused() -> None:
    """The routed class is hermes's row, and hermes has the layer. Providing it is `never both`.

    Two rotation policies over one credential set are not redundancy: they are a race over
    single-use refresh chains, which is what revoked every grant derived from one login at once.
    """

    hosted = hermes_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)
    hosted["layers"] = {"pool": "provide", "fallback": "configure"}

    refusal = HarnessRegistry().register(
        hosted, "real", route=_registration_route(_hermes_spec())
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-layer-conflict"
    assert dict(refusal.detail)["derived_pool"] == "configure"


@pytest.mark.parametrize("question", ("native_pool", "identity_proof", "egress_topology"))
def test_an_unanswered_survey_question_refuses_rather_than_leaving_the_role_to_a_guess(
    question: str,
) -> None:
    refusal = HarnessRegistry().register(
        _unanswered(_document(), question), "real", route=_registration_route()
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-survey-incomplete"


def test_an_unanswered_survey_on_the_hosting_harness_refuses_the_routed_class_too() -> None:
    hosted = hermes_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)

    refusal = HarnessRegistry().register(
        _unanswered(hosted, "native_fallback"),
        "real",
        route=_registration_route(_hermes_spec()),
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-survey-incomplete"


# --- the runtime-under-a-harness distinction ----------------------------------------------


def test_the_direct_cli_is_a_harness_and_pins_its_own_config_home_beside_it() -> None:
    route = classify_route(runtime_ref="/srv/codex-homes/jakit", spec=_spec())

    assert route.route_class == "direct_cli_harness"
    assert route.mints_a_harness_value()
    assert route.harness_ref == CODEX_KEY
    assert route.runtime_ref == "/srv/codex-homes/jakit"
    assert mint_refusal(route, CODEX_KEY) is None


@pytest.mark.parametrize("routed", ("codex", "gpt-5.6-sol", "deepseek-v4-pro"))
def test_no_second_harness_value_is_minted_for_anything_reached_as_a_runtime(
    routed: str,
) -> None:
    """The classification negative. A model is not a harness, and neither is a routed runtime.

    All three of these are reached through a hermes profile: one is the codex runtime, one is
    the model that runtime serves, one is a model on another rung entirely. Naming any of them
    a harness would mint a value with no artifact, config home, or credential lineage to pin.
    """

    route = classify_route(runtime_ref=routed, spec=_hermes_spec())

    refusal = mint_refusal(route, routed)

    assert not route.mints_a_harness_value()
    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-runtime-not-a-harness"
    assert dict(refusal.detail)["proposed_harness_ref"] == routed
    assert dict(refusal.detail)["resolved_harness_ref"] == "hermes"


@pytest.mark.parametrize("proposed_key", ("gpt-5.6-sol", "deepseek-v4-pro"))
def test_registration_chokepoint_refuses_model_and_vendor_keys_without_mutation(
    proposed_key: str,
) -> None:
    route = classify_route(runtime_ref="/srv/codex-homes/seat-three", spec=_spec())
    document = _document({"key": proposed_key})
    registry = HarnessRegistry()

    refusal = registry.register(document, "real", route=route)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-runtime-not-a-harness"
    assert registry.real_bindings() == ()
    assert registry.resolve(proposed_key).name == "harness-spec-unknown"


def test_a_refused_runtime_leaves_the_registry_with_the_bindings_it_already_had() -> None:
    registry = HarnessRegistry()
    hosted = hermes_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)
    registry.register(hosted, "real", route=_registration_route(_hermes_spec()))
    registry.register(_document(), "real", route=_registration_route())
    route = classify_route(runtime_ref="deepseek-v4-pro", spec=_hermes_spec())

    assert mint_refusal(route, "deepseek-v4-pro") is not None
    assert registry.real_bindings() == ("codex", "hermes")
    assert isinstance(registry.resolve("deepseek-v4-pro"), Refusal)


def test_the_plan_carries_the_runtime_reference_and_the_model_as_separate_arguments() -> None:
    """`harness_ref` and the runtime reference are both pinned, and the model is neither.

    A launcher that folded the model into its own identity is what produced a phantom harness
    category; here the config home is `profile_ref` and the model is an argument on the argv.
    """

    guard = _Guard()

    receipt = _spawn(_binding(pane=_healthy_pane(), guard=guard))

    assert not isinstance(receipt, Refusal), receipt
    plan = guard.plans[0]
    assert plan.program == CODEX_WRAPPER
    assert plan.harness_ref == CODEX_KEY
    assert plan.profile_ref == _PROFILE
    assert plan.credential_identity == _HEALTHY
    assert plan.credential_home == "/srv/codex-homes/seat-three"
    assert plan.argv == (
        _SEAT,
        "--config-home",
        "/srv/codex-homes/seat-three",
        "--model",
        _spec().probe.model_ref,
    )
    assert _spec().probe.model_ref not in (plan.harness_ref, plan.profile_ref)


def test_spawn_refuses_when_the_pane_still_contains_delivered_text_without_its_digest() -> None:
    supervisor = _Supervisor("build the row")

    refusal = _spawn(_binding(pane="build the row", supervisor=supervisor))

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-dispatch-unacknowledged"


def test_spawn_refuses_when_intent_model_differs_from_the_revision_pinned_probe() -> None:
    supervisor = _Supervisor(_healthy_pane())
    attempt = dataclasses.replace(_attempt(), intent_model="gpt-5.6-terra")

    refusal = _spawn_attempt(_binding(pane=_healthy_pane(), supervisor=supervisor), attempt)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-dispatch-model-mismatch"
    assert not supervisor.launched


@pytest.mark.parametrize(
    ("pin_field", "forged_value"),
    (
        ("harness_ref", "gpt-5.6-sol"),
        ("spec_revision", 999),
        ("composition_digest", "codex@999+sha256:forged"),
    ),
    ids=("harness", "revision", "composition"),
)
def test_spawn_refuses_each_mismatched_composition_pin_before_lease_or_guard(
    pin_field: str, forged_value: object
) -> None:
    supervisor = _Supervisor(_healthy_pane())
    guard = _Guard()
    attempt = dataclasses.replace(_attempt(), **{pin_field: forged_value})

    refusal = _spawn_attempt(
        _binding(pane=_healthy_pane(), supervisor=supervisor, guard=guard), attempt
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-dispatch-pin-mismatch"
    assert f"attempt_{pin_field}" in dict(refusal.detail)
    assert not supervisor.launched
    assert not guard.plans


def test_spawn_refuses_a_combined_forged_composition_before_any_dispatch_side_effect() -> None:
    supervisor = _Supervisor(_healthy_pane())
    guard = _Guard()
    attempt = dataclasses.replace(
        _attempt(),
        harness_ref="gpt-5.6-sol",
        spec_revision=999,
        composition_digest="codex@999+sha256:forged",
    )

    refusal = _spawn_attempt(
        _binding(pane=_healthy_pane(), supervisor=supervisor, guard=guard), attempt
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-dispatch-pin-mismatch"
    details = dict(refusal.detail)
    assert details["attempt_harness_ref"] == "gpt-5.6-sol"
    assert details["attempt_spec_revision"] == "999"
    assert details["attempt_composition_digest"] == "codex@999+sha256:forged"
    assert not supervisor.launched
    assert not guard.plans


def test_request_observation_reads_the_model_from_the_guarded_launch_argv() -> None:
    attempt = _attempt()
    plan = ExecutionPlan(
        harness_ref=CODEX_KEY,
        profile_ref=_PROFILE,
        composition_digest=attempt.composition_digest,
        program=CODEX_WRAPPER,
        argv=(_SEAT, "--config-home", "/srv/codex-homes/seat-three", "--model", "gpt-5.6-terra"),
        worktree_path="/srv/attempt",
        credential_identity=_HEALTHY,
        credential_home="/srv/codex-homes/seat-three",
    )

    request = next(
        reading
        for reading in _binding(pane=_healthy_pane())._readings(attempt, plan)
        if reading.proves == "request"
    )

    assert request.source == "launch_argv"
    assert request.value == "gpt-5.6-terra"


# --- AC-HAD-03: the launch-argv column ----------------------------------------------------


def test_the_launch_argv_proves_the_request_and_the_rollout_proves_serving() -> None:
    spec = _spec()
    serving = spec.serving_source()

    argv = [item for item in spec.liveness_sources if item.source == "launch_argv"]

    assert serving is not None
    assert serving.source == "session_transcript"
    assert [item.proves for item in argv] == ["request"]
    assert not [
        item
        for item in spec.liveness_sources
        if item.fact == "served_model" and item.source == "pane_footer"
    ]


def test_a_downgrade_under_an_agreeing_status_bar_is_recorded_as_a_conflict() -> None:
    binding = _binding(pane=_healthy_pane(), served="gpt-5.6-luna")
    receipt = _spawn(binding)
    assert not isinstance(receipt, Refusal), receipt

    fact = binding.liveness(_attempt(), 0)

    assert isinstance(fact, LivenessFact)
    assert fact.served_model is not None
    assert fact.served_model.is_serving_truth()
    assert fact.served_model.value == "gpt-5.6-luna"
    assert fact.conflict is not None
    assert "launch_argv" in fact.conflict


def test_an_unreadable_pane_is_named_and_never_guessed() -> None:
    fact = _binding(pane=None).liveness(_attempt(), 0)

    assert fact.state == "unknown"
    assert fact.probe == f"substrate-unobservable:{CODEX_PROBE}"
    assert not fact.counts_as_working()
