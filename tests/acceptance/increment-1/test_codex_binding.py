"""CT-I1-043 acceptance — the `codex` binding and the category it refuses.

The one shared conformance suite drives this binding through every cell it drives `hermes` and
the fault-injection fake through, unchanged. What is proven here is what that suite
deliberately does not know about: that a runtime routed through another harness mints no
harness value of its own, that the launch argv is a request record and never serving truth,
that the pool's fact beats the substrate's when the two disagree, that a window returning to
`available` stages the brief instead of launching it, and that every mutating credential verb
answers a question with usage rather than a side effect.

Everything below is deterministic: no clock, no randomness, no I/O, no network.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from ctower_runner.codex.binding import CODEX_POOL_PROBE, CODEX_PROBE, CODEX_WRAPPER, CodexBinding
from ctower_runner.codex.ceremonies import (
    CEREMONIES,
    QUESTION_FLAGS,
    Ceremony,
    CeremonyInvocation,
    CeremonyOutcome,
    UsageAnswer,
    ceremony_for,
    mutating_ceremonies,
    plan_ceremony,
)
from ctower_runner.codex.corpus import CODEX_CORPUS, captured_cases
from ctower_runner.codex.liveness import classify_pane, context_used_pct
from ctower_runner.codex.pool import CodexAccount, CodexPool, ConfigHomeStore
from ctower_runner.codex.route import classify_route, mint_refusal
from ctower_runner.codex.spec import (
    CODEX_KEY,
    CODEX_SATURATION_PERCENT,
    digest_of,
    harness_spec_document,
)
from ctower_runner.hermes.spec import harness_spec_document as hermes_spec_document
from ctower_runner_sdk.attempt import AttemptPin, BriefBundle, SeatRef, WorkspaceContext
from ctower_runner_sdk.conformance import CorpusCase
from ctower_runner_sdk.credentials import ProbeResponse, project_entry
from ctower_runner_sdk.facts import LivenessFact
from ctower_runner_sdk.guard import DispatchBoundary, ExecutionPlan, GuardDecision
from ctower_runner_sdk.refusals import SEAM_MINTED, SPEC_OWNED, Refusal
from ctower_runner_sdk.registry import HarnessRegistry
from ctower_runner_sdk.rotation import RotationEvent
from ctower_runner_sdk.spec import HarnessSpec, parse_harness_spec
from ctower_runner_sdk.survey import derive_roles

__all__: tuple[str, ...] = ()

_NOW = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
_ARTIFACT = digest_of(b"codex-cli-artifact-under-test")
_CONFIG = digest_of(b"codex-config-home-under-test")
_LEASE_ID = UUID("00000000-0000-4000-8000-000000000001")
_ATTEMPT_ID = UUID("00000000-0000-4000-8000-00000000000a")
_PROFILE = "engineer"
_SEAT = "engineer-t3"
_PROJECT = "ctower"
_GUARD_VERSION = 3

# A value beside the readable fields that the projection allowlist must leave behind.
_ADJACENT = "ADJACENT-VALUE-THE-ALLOWLIST-MUST-LEAVE-BEHIND"
_TOKEN_FIELDS = ("access_token", "refresh_token")

_HEALTHY = "seat-three@example.test"
_SPENT = "seat-one@example.test"
_RESTING = "seat-two@example.test"
_IDENTITIES = (_SPENT, _RESTING, _HEALTHY)

_USED_AT_8_LEFT = 92
_DISTINCT_CLOCKS = 3
_MIN_CAPTURED_CASES = 4
_STALE_GENERATION = 1
_LIVE_GENERATION = 4


def _document(overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    document = harness_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)
    document.update(overrides or {})
    return document


def _spec(overrides: Mapping[str, object] | None = None) -> HarnessSpec:
    parsed = parse_harness_spec(_document(overrides))
    assert isinstance(parsed, HarnessSpec), parsed
    return parsed


def _hermes_spec() -> HarnessSpec:
    parsed = parse_harness_spec(
        hermes_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)
    )
    assert isinstance(parsed, HarnessSpec), parsed
    return parsed


def _record(identity: str, quota_state: str, reset_at: datetime, seed: str) -> dict[str, object]:
    """One account file's own metadata, credential fields included on purpose."""

    return {
        "provider_key": "openai-codex",
        "subscription_identity": identity,
        "entry_label": "codex",
        "registration_state": "enrolled",
        "auth_state": "healthy",
        "quota_state": quota_state,
        "quota_reset_at": reset_at,
        "reach_state": "ok",
        "request_count": 12,
        "last_status_observed": "ok" if quota_state == "available" else "exhausted",
        "secret_fingerprint": "sha256:" + seed * 64,
        "access_token": _ADJACENT,
        "refresh_token": _ADJACENT,
    }


def _store(*, quotas: tuple[str, str, str] = ("capped", "capped", "available")) -> ConfigHomeStore:
    """Three accounts, three clocks, two resting: the shape one word cannot express."""

    records = (
        _record(_SPENT, quotas[0], _NOW + timedelta(hours=5), "a"),
        _record(_RESTING, quotas[1], _NOW + timedelta(hours=8), "b"),
        _record(_HEALTHY, quotas[2], _NOW + timedelta(days=3), "c"),
    )
    accounts = {
        identity: CodexAccount(
            account_identity=identity,
            codex_home=f"/srv/codex-homes/{identity.split('@')[0]}",
            refresh_generation=_LIVE_GENERATION,
            entry=record,
        )
        for identity, record in zip(_IDENTITIES, records, strict=True)
    }
    return ConfigHomeStore(accounts=accounts, live_identity=_SPENT)


class _Ceremonies:
    """Every ceremony this binding asked for, and the answer each one gave."""

    def __init__(self, outcome: CeremonyOutcome | None = None) -> None:
        self._outcome = outcome
        self.asked: list[CeremonyInvocation] = []

    def run(self, invocation: CeremonyInvocation) -> CeremonyOutcome:
        self.asked.append(invocation)
        if self._outcome is not None:
            return self._outcome
        return CeremonyOutcome(
            ceremony=invocation.ceremony,
            installed_identity=_HEALTHY,
            installed_generation=_LIVE_GENERATION + 1,
            hook_completed=True,
        )


def _pool(
    store: ConfigHomeStore | None = None,
    ceremonies: _Ceremonies | None = None,
) -> CodexPool:
    return CodexPool(
        _spec(),
        store or _store(),
        ceremonies or _Ceremonies(),
        _PROFILE,
        lambda: _NOW,
        lambda: _LEASE_ID,
    )


class _Supervisor:
    """D10's process control, answering from a stated pane. Every launch is recorded."""

    def __init__(self, pane: str | None) -> None:
        self._pane = pane
        self.launched: list[str] = []

    def launch(self, plan: ExecutionPlan, attempt: AttemptPin) -> str:
        self.launched.append(plan.normalized_digest())
        return f"pane-{attempt.attempt_id}"

    def observe(self, attempt: AttemptPin, after_cursor: int) -> str | None:
        del attempt, after_cursor
        return self._pane

    def deliver_input(self, attempt: AttemptPin, text: str) -> str | None:
        return f"cmd-{attempt.attempt_id}-{len(text)}"

    def terminate(self, attempt: AttemptPin) -> None:
        del attempt


class _Rollout:
    """The session rollout this attempt's config home recorded. Serving truth, or nothing."""

    def __init__(self, served: str | None) -> None:
        self._served = served

    def served_model(self, attempt: AttemptPin) -> str | None:
        del attempt
        return self._served


class _Workspace:
    """Committed refs only. Pane text can never reach an artifact slot through here."""

    def dirty_paths(self, context: WorkspaceContext) -> tuple[str, ...]:
        del context
        return ()

    def head(self, context: WorkspaceContext) -> tuple[str, bool]:
        del context
        return "1" * 40, True

    def gate_outputs(self, context: WorkspaceContext) -> tuple[str, ...]:
        return (f"{context.branch}/just-verify.log",)

    def status_artifact(self, context: WorkspaceContext) -> str | None:
        del context
        return "status.md"


class _Writeback:
    """The generated client, as the runner reaches it. No record-tier connection."""

    def file(
        self, attempt: AttemptPin, credential_ref: str, facts: tuple[tuple[str, str], ...]
    ) -> tuple[str, str]:
        del attempt, facts
        return f"principal-{credential_ref}", "accepted"


class _Guard:
    """A guard that allows the exact plan it is shown, and keeps the plan it was shown."""

    def __init__(self) -> None:
        self.plans: list[ExecutionPlan] = []

    def decide(self, plan: ExecutionPlan) -> GuardDecision:
        self.plans.append(plan)
        return GuardDecision(
            decision_id="decision-1",
            verdict="allow",
            plan_digest=plan.normalized_digest(),
            guard_version=_GUARD_VERSION,
            expires_at=_NOW + timedelta(hours=1),
        )


class _Receipts:
    def record(self, decision: GuardDecision, plan: ExecutionPlan) -> bool:
        del decision, plan
        return True


def _attempt() -> AttemptPin:
    spec = _spec()
    return AttemptPin(
        attempt_id=_ATTEMPT_ID,
        epoch=1,
        harness_ref=CODEX_KEY,
        profile_ref=_PROFILE,
        spec_revision=spec.revision,
        composition_digest=spec.composition_digest(),
        intent_model=spec.probe.model_ref,
    )


def _binding(
    *,
    pane: str | None,
    served: str | None = None,
    pool: CodexPool | None = None,
    supervisor: _Supervisor | None = None,
    guard: _Guard | None = None,
) -> CodexBinding:
    return CodexBinding(
        _spec(),
        supervisor=supervisor or _Supervisor(pane),
        rollout=_Rollout(served or _spec().probe.model_ref),
        workspace=_Workspace(),
        writeback_port=_Writeback(),
        pool=pool or _pool(),
        boundary=DispatchBoundary(guard or _Guard(), _Receipts(), _GUARD_VERSION),
        clock=lambda: _NOW,
    )


def _spawn(binding: CodexBinding, text: str = "build the row") -> object:
    return binding.spawn(
        _attempt(),
        SeatRef(seat_key=_SEAT, engagement_label=_PROFILE, project_key=_PROJECT),
        BriefBundle(text=text, digest="sha256:" + "f" * 64, ack_detail="cleared"),
        WorkspaceContext(worktree_path="/srv/attempt", branch="feat/x", base_ref="origin/main"),
    )


def _healthy_pane() -> str:
    return next(case.sample for case in CODEX_CORPUS if case.expected == "working")


def _unanswered(document: dict[str, object], question: str) -> dict[str, object]:
    """The same document with exactly one survey answer removed."""

    survey = document["survey"]
    assert isinstance(survey, dict)
    return {**document, "survey": {key: value for key, value in survey.items() if key != question}}


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
    refusal = HarnessRegistry().register(_document({"layers": layers}), "real")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-layer-conflict"


def test_declaring_provide_over_the_routed_runtimes_hosted_pool_is_refused() -> None:
    """The routed class is hermes's row, and hermes has the layer. Providing it is `never both`.

    Two rotation policies over one credential set are not redundancy: they are a race over
    single-use refresh chains, which is what revoked every grant derived from one login at once.
    """

    hosted = hermes_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)
    hosted["layers"] = {"pool": "provide", "fallback": "configure"}

    refusal = HarnessRegistry().register(hosted, "real")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-layer-conflict"
    assert dict(refusal.detail)["derived_pool"] == "configure"


@pytest.mark.parametrize("question", ("native_pool", "identity_proof", "egress_topology"))
def test_an_unanswered_survey_question_refuses_rather_than_leaving_the_role_to_a_guess(
    question: str,
) -> None:
    refusal = HarnessRegistry().register(_unanswered(_document(), question), "real")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-survey-incomplete"


def test_an_unanswered_survey_on_the_hosting_harness_refuses_the_routed_class_too() -> None:
    hosted = hermes_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)

    refusal = HarnessRegistry().register(_unanswered(hosted, "native_fallback"), "real")

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


def test_a_refused_runtime_leaves_the_registry_with_the_bindings_it_already_had() -> None:
    registry = HarnessRegistry()
    hosted = hermes_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)
    registry.register(hosted, "real")
    registry.register(_document(), "real")
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
    assert plan.argv == (_SEAT, "--model", _spec().probe.model_ref)
    assert _spec().probe.model_ref not in (plan.harness_ref, plan.profile_ref)


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
    fact = _binding(pane=_healthy_pane(), served="gpt-5.6-luna").liveness(_attempt(), 0)

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


# --- AC-HAD-04: this harness's own classifier ---------------------------------------------


@pytest.mark.parametrize("case", CODEX_CORPUS, ids=lambda item: item.label)
def test_every_corpus_case_classifies_to_its_recorded_state(case: CorpusCase) -> None:
    assert classify_pane(case.sample, saturation_percent=CODEX_SATURATION_PERCENT) == case.expected


def test_the_corpus_is_captured_substrate_and_says_so_where_it_is_not() -> None:
    captured = captured_cases()

    assert len(captured) >= _MIN_CAPTURED_CASES
    assert all("captured" in case.provenance for case in captured)
    assert all("composed" in case.provenance for case in CODEX_CORPUS if not case.captured)
    assert {case.expected for case in CODEX_CORPUS} >= {"capped", "saturated", "dead_auth"}


def test_the_status_line_ships_both_percentage_forms_and_only_one_is_a_direct_reading() -> None:
    """Percent-remaining and percent-consumed are both real items on this status line.

    A reader that assumed either form reports a lane with 8% left as 8% consumed — the healthy
    answer for the failing case — on every pane configured the other way.
    """

    left = "gpt-5.6-sol max · Context 8% left"
    used = "gpt-5.6-sol max · Context 92% used"

    assert context_used_pct(left) == _USED_AT_8_LEFT
    assert context_used_pct(used) == _USED_AT_8_LEFT
    assert classify_pane(left, saturation_percent=CODEX_SATURATION_PERCENT) == "saturated"
    assert classify_pane(used, saturation_percent=CODEX_SATURATION_PERCENT) == "saturated"


def test_a_spent_window_is_never_read_as_a_dead_lineage() -> None:
    """Auth is not quota, and this substrate says both in nearly one breath.

    A collapsed reading sends the reader to a re-mint ceremony that burns a fresh single-use
    device flow against a credential that was never broken, and loses the stated reset.
    """

    capped = next(case for case in CODEX_CORPUS if case.expected == "capped")
    dead = next(case for case in CODEX_CORPUS if case.expected == "dead_auth")

    assert classify_pane(capped.sample, saturation_percent=CODEX_SATURATION_PERCENT) == "capped"
    assert classify_pane(dead.sample, saturation_percent=CODEX_SATURATION_PERCENT) == "dead_auth"
    assert "usage limit" in capped.sample.lower()


# --- AC-HAD-10: the pool, and the pane that cannot see it ---------------------------------


def test_the_pool_fact_is_reported_over_a_healthy_pane_when_the_two_disagree() -> None:
    """A sentinel read the substrate and said `codex=alive` while every seat was dying.

    Exhaustion arrives as a non-retryable 401 on the first real call; the probe path and the
    pool path are different paths, and the pane is the one that cannot see the credential.
    """

    dry = _pool(_store(quotas=("capped", "capped", "capped")))
    pane = _healthy_pane()

    substrate = classify_pane(pane, saturation_percent=CODEX_SATURATION_PERCENT)
    fact = _binding(pane=pane, pool=dry).liveness(_attempt(), 0)

    assert substrate == "working"
    assert fact.state == "dead_auth"
    assert fact.probe == CODEX_POOL_PROBE
    assert "no selectable entry" in fact.evidence
    assert not fact.counts_as_working()


def test_a_pool_with_one_healthy_entry_leaves_the_substrate_fact_alone() -> None:
    fact = _binding(pane=_healthy_pane()).liveness(_attempt(), 0)

    assert fact.state == "working"
    assert fact.probe == CODEX_PROBE


def test_a_prepaid_402_is_dead_auth_because_money_is_a_liveness_condition() -> None:
    """Revoked, capped, and unfunded are one fact from the seat's side and one from the pool's.

    The pool keeps three axes apart because the difference decides which ceremony is right; the
    lane collapses them because the consequence is identical and `reap` must preserve all three.
    """

    reading = _pool().probe(
        ProbeResponse(
            status_code=402,
            body="out of credits",
            model_ref=_spec().probe.model_ref,
            drawn_from_pool=True,
            after_invalidation=True,
        )
    )
    unfunded = _pool(_store(quotas=("unfunded", "unfunded", "unfunded")))

    fact = _binding(pane=_healthy_pane(), pool=unfunded).liveness(_attempt(), 0)

    assert not isinstance(reading, Refusal), reading
    assert reading.auth == "healthy"
    assert reading.quota == "unfunded"
    assert fact.state == "dead_auth"


def test_an_exhausted_pool_refuses_with_the_whole_diagnosis_rather_than_one_word() -> None:
    refusal = _pool(_store(quotas=("capped", "capped", "capped"))).acquire(
        model_ref=_spec().probe.model_ref, tier=_PROFILE
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "credential-pool-exhausted"
    rows = dict(refusal.detail)
    assert rows["earliest_known_reset"] == (_NOW + timedelta(hours=5)).isoformat()
    assert rows[f"{_SPENT} quota"] == "capped"
    assert "wait for the provider" in refusal.action


def test_a_mixed_pool_acquires_from_its_healthy_account_and_reports_three_clocks() -> None:
    pool = _pool()

    lease = pool.acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)
    rows = pool.limits()

    assert not isinstance(lease, Refusal), lease
    assert lease.entry.subscription_identity == _HEALTHY
    assert len({row.quota_reset_at for row in rows}) == _DISTINCT_CLOCKS


def test_observation_projects_the_allowlist_and_leaves_the_adjacent_token_behind() -> None:
    pool = _pool()

    lease = pool.acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)
    rows = pool.limits()
    assert not isinstance(lease, Refusal), lease
    pool.meter(lease, {"event": "spawn", "model_ref": lease.model_ref})

    bodies = (str([row.to_mapping() for row in rows]), str(lease.to_mapping()), str(pool.metered))
    for body in bodies:
        assert _ADJACENT not in body
        assert not [field for field in _TOKEN_FIELDS if field in body]


def test_the_provided_pool_has_no_copy_path_and_no_writer_of_an_account_file() -> None:
    verbs = {name for name in dir(_pool()) if not name.startswith("_")}

    assert not [name for name in verbs if "copy" in name or "install" in name]
    assert not [name for name in verbs if "write" in name or "auth" in name]
    assert {"acquire", "limits", "rotate", "probe", "request_mint"} <= verbs


def test_a_mint_is_requested_through_the_ceremony_that_already_exists() -> None:
    request = _pool().request_mint(_HEALTHY)
    one_account = ceremony_for("enrol", _HEALTHY)
    every_account = ceremony_for("enrol")

    assert request.enactment == "operator-ceremony"
    assert request.provider_key == "openai-codex"
    assert not isinstance(one_account, Refusal), one_account
    assert not isinstance(every_account, Refusal), every_account
    assert one_account.ceremony == "codex-grant-ceremony"
    assert every_account.ceremony == "codex-auth-all"


def test_a_question_arriving_where_an_action_was_required_never_becomes_one() -> None:
    """The acting path refuses `--help` rather than falling through to its one invocation.

    An identity arrives from outside the binding, so this is the spelling that reproduces the
    incident: a mutating verb handed a question, with nothing declaring that it is one.
    """

    refusal = ceremony_for("enrol", "--help")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "credential-verb-unknown-flag"
    assert dict(refusal.detail)["unknown_argument"] == "--help"


# --- AC-HAD-11: rotation is wrapped, and a flap holds a cycle -----------------------------


def test_a_rotation_asks_the_fleets_own_ceremony_rather_than_running_a_fifth_policy() -> None:
    ceremonies = _Ceremonies()
    pool = _pool(ceremonies=ceremonies)

    event = pool.rotate("observed a non-retryable 401")

    assert isinstance(event, RotationEvent), event
    assert [invocation.ceremony for invocation in ceremonies.asked] == ["codex-rotate-fallback"]
    assert ceremonies.asked[0].argv == ()
    assert event.context_rereads == 1
    assert event.layer == "pool"


def test_the_ceremonys_own_generation_guard_is_surfaced_and_never_re_derived() -> None:
    """`codex-rotate-fallback` owns this guard, hardened the night a stale snapshot was installed.

    Every grant derived from that login was revoked at once and a review died mid-run. The pool
    reports the ceremony's verdict rather than forming a second opinion about the same chain.
    """

    refused = CeremonyOutcome(
        ceremony="codex-rotate-fallback",
        installed_identity=_HEALTHY,
        installed_generation=_STALE_GENERATION,
        hook_completed=True,
        refusal_name="stale-snapshot",
        detail=f"generation {_LIVE_GENERATION} was last live",
    )
    store = _store()

    outcome = _pool(store, _Ceremonies(refused)).rotate("observed a 401")

    assert isinstance(outcome, Refusal), outcome
    assert outcome.name == "rotation-refused-stale-generation"
    assert dict(outcome.detail)["ceremony"] == "codex-rotate-fallback"
    assert store.live_identity == _SPENT


def test_a_rotation_against_a_challenged_edge_is_refused_before_a_ceremony_is_asked() -> None:
    """No ceremony repairs a provider's edge, and this survey answers `egress_topology: shared`.

    Running one against it burns a fresh single-use device flow on a credential that was never
    broken, which is the exact failure the three-axis model exists to prevent.
    """

    store = _store()
    live = store.accounts[_SPENT]
    store.accounts[_SPENT] = dataclasses.replace(
        live, entry={**live.entry, "reach_state": "edge-challenged"}
    )
    ceremonies = _Ceremonies()

    refusal = _pool(store, ceremonies).rotate("observed a 403 challenge page")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-refused-unreachable"
    assert ceremonies.asked == []


def test_a_rotation_whose_hook_did_not_complete_is_incomplete_rather_than_done() -> None:
    incomplete = CeremonyOutcome(
        ceremony="codex-rotate-fallback",
        installed_identity=_HEALTHY,
        installed_generation=_LIVE_GENERATION + 1,
        hook_completed=False,
    )

    refusal = _pool(_store(), _Ceremonies(incomplete)).rotate("observed a 401")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-incomplete"
    assert dict(refusal.detail)["hook"] == "codex-home-respawn"


def test_no_entry_state_is_believed_before_the_invalidation_hook_completes() -> None:
    store = _store()
    store.hook_completed = False

    refusal = _pool(store).acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "pool-state-stale"
    assert refusal.name != "credential-pool-exhausted"


def test_a_window_returning_to_available_stages_the_brief_and_launches_nothing() -> None:
    """Two flips in one morning; the second lasted two sweeps. The bar is one full cycle.

    What matters is not only that `acquire` refuses but that nothing is started: the brief is
    staged and no pane exists to half-abandon when the window turns out to be the second flip.
    """

    pool = _pool()
    pool.observe_window(_HEALTHY, available=True)
    supervisor = _Supervisor(_healthy_pane())

    inside = _spawn(_binding(pane=None, pool=pool, supervisor=supervisor), "staged")
    pool.observe_window(_HEALTHY, available=True)
    after = pool.acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)

    assert isinstance(inside, Refusal), inside
    assert inside.name == "credential-pool-exhausted"
    assert supervisor.launched == []
    assert not isinstance(after, Refusal), after


# --- the unknown-flag law, on every mutating credential verb -------------------------------


@pytest.mark.parametrize("ceremony", mutating_ceremonies(), ids=lambda item: item.name)
def test_every_mutating_credential_verb_refuses_an_argument_it_cannot_read(
    ceremony: Ceremony,
) -> None:
    planned = plan_ceremony(ceremony, ("--force-rotate-everything",))

    assert isinstance(planned, Refusal), planned
    assert planned.name == "credential-verb-unknown-flag"
    assert dict(planned.detail)["ceremony"] == ceremony.name
    assert ceremony.usage in planned.action


@pytest.mark.parametrize("ceremony", mutating_ceremonies(), ids=lambda item: item.name)
@pytest.mark.parametrize("question", sorted(QUESTION_FLAGS))
def test_every_mutating_credential_verb_answers_a_question_with_usage(
    ceremony: Ceremony, question: str
) -> None:
    """`tools/codex-rotate-fallback --help` once rotated live credentials.

    The tool ignored the flag it could not read and fell through to its one real invocation.
    A question is answered by returning usage with nothing run.
    """

    answered = plan_ceremony(ceremony, (question,))

    assert isinstance(answered, UsageAnswer), answered
    assert answered.ceremony == ceremony.name
    assert answered.usage == ceremony.usage


def test_the_rotation_ceremony_declares_no_arguments_at_all() -> None:
    rotate = CEREMONIES["rotate"]

    assert isinstance(plan_ceremony(rotate, ()), CeremonyInvocation)
    assert isinstance(plan_ceremony(rotate, ("simasjak",)), Refusal)
    assert isinstance(plan_ceremony(CEREMONIES["cooldown"], ("cap",)), CeremonyInvocation)
    assert isinstance(plan_ceremony(CEREMONIES["cooldown"], ("nuke",)), Refusal)


# --- vocabulary and containment ------------------------------------------------------------


def test_every_refusal_this_binding_raises_is_inside_the_seam_vocabulary() -> None:
    raised = {
        "credential-pool-exhausted",
        "credential-verb-unknown-flag",
        "harness-dispatch-unacknowledged",
        "harness-runtime-not-a-harness",
        "pool-state-stale",
        "rotation-incomplete",
        "rotation-refused-stale-generation",
        "rotation-refused-unreachable",
    }

    assert raised <= SEAM_MINTED | SPEC_OWNED
    assert not SEAM_MINTED & SPEC_OWNED


def test_the_declared_composition_is_pinned_by_key_revision_and_two_digests() -> None:
    spec = _spec()

    assert spec.composition_digest() == f"{CODEX_KEY}@{spec.revision}+{_ARTIFACT}+{_CONFIG}"
    assert spec.pool.cache_invalidation_hook == "codex-home-respawn"
    assert spec.probe.measures(spec.probe.model_ref)


def test_the_pool_entry_is_keyed_by_identity_and_a_label_carries_no_authority() -> None:
    rows = _pool().limits()

    assert {row.subscription_identity for row in rows} == set(_IDENTITIES)
    assert len({row.entry_label for row in rows}) == 1
    assert project_entry(_record(_HEALTHY, "available", _NOW, "c")).entry_label == "codex"
