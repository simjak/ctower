"""Codex credential-pool, liveness, ceremony, and boundary acceptance tests."""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest
from _codex_fixtures import (
    _ADJACENT,
    _ARTIFACT,
    _CONFIG,
    _DISTINCT_CLOCKS,
    _HEALTHY,
    _IDENTITIES,
    _LIVE_GENERATION,
    _MIN_CAPTURED_CASES,
    _NOW,
    _PROFILE,
    _SEAT,
    _SPENT,
    _STALE_GENERATION,
    _TOKEN_FIELDS,
    _USED_AT_8_LEFT,
    _USED_AT_71_LEFT,
    _attempt,
    _binding,
    _Ceremonies,
    _healthy_pane,
    _pool,
    _record,
    _spawn,
    _spec,
    _store,
    _Supervisor,
)

from ctower_runner.codex.binding import CODEX_POOL_PROBE, CODEX_PROBE
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
from ctower_runner.codex.spec import CODEX_KEY, CODEX_SATURATION_PERCENT
from ctower_runner_sdk.conformance import CorpusCase
from ctower_runner_sdk.credentials import MeterObservation, ProbeResponse, project_entry
from ctower_runner_sdk.refusals import SEAM_MINTED, SPEC_OWNED, Refusal
from ctower_runner_sdk.rotation import RotationEvent

__all__: tuple[str, ...] = ()


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


def test_context_uses_the_bottommost_status_item_across_both_percentage_forms() -> None:
    pane = (
        "old status · Context 94% used\n"
        "\u203a keep the old line in scrollback\n"
        "current status · Esc to interrupt · Context 71% left"
    )

    assert context_used_pct(pane) == _USED_AT_71_LEFT


def test_prompt_context_prose_below_the_status_region_does_not_override_status_context() -> None:
    pane = (
        "Codex status · Context 71% left\n"
        "> explain why the old log says Context 99% used\n"
        "Thinking…"
    )

    assert context_used_pct(pane) == _USED_AT_71_LEFT
    assert classify_pane(pane, saturation_percent=CODEX_SATURATION_PERCENT) == "working"


def test_prompt_prose_does_not_turn_a_real_thinking_marker_into_a_cap() -> None:
    pane = "> explain the phrase out of credits\nThinking\u2026"

    assert classify_pane(pane, saturation_percent=CODEX_SATURATION_PERCENT) == "working"


def test_missing_rollout_serving_truth_is_unknown_not_as_intended() -> None:
    fact = _binding(pane=_healthy_pane(), served_missing=True).liveness(_attempt(), 0)

    assert fact.state == "working"
    assert fact.served_model is None
    assert fact.ladder == "unknown"


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


def test_a_pool_refuses_a_profile_outside_its_registered_pool_before_selection() -> None:
    refusal = _pool().acquire(model_ref=_spec().probe.model_ref, tier="reviewer")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-credential-profile-mismatch"


@pytest.mark.parametrize("mismatch", ("store-key", "account-identity", "projected-identity"))
def test_pool_identity_lineage_must_match_before_any_entry_is_selected(mismatch: str) -> None:
    store = _store()
    account = store.accounts[_HEALTHY]
    if mismatch == "store-key":
        store.accounts["wrong@example.test"] = store.accounts.pop(_HEALTHY)
    elif mismatch == "account-identity":
        store.accounts[_HEALTHY] = dataclasses.replace(
            account, account_identity="wrong@example.test"
        )
    else:
        store.accounts[_HEALTHY] = dataclasses.replace(
            account, entry={**account.entry, "subscription_identity": "wrong@example.test"}
        )

    refusal = _pool(store).acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "credential-identity-mismatch"


def test_observation_projects_the_allowlist_and_leaves_the_adjacent_token_behind() -> None:
    pool = _pool()

    lease = pool.acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)
    rows = pool.limits()
    assert not isinstance(lease, Refusal), lease
    pool.meter(lease, MeterObservation(event="spawn", model_ref=lease.model_ref))

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

    assert not isinstance(request, Refusal), request
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

    store = _store()
    refusal = _pool(store, _Ceremonies(incomplete)).rotate("observed a 401")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-incomplete"
    assert dict(refusal.detail)["hook"] == "codex-home-respawn"
    assert store.live_identity == _SPENT
    assert store.accounts[_HEALTHY].refresh_generation == _LIVE_GENERATION
    assert not store.hook_completed
    assert store.journal == ["ask codex-rotate-fallback"]
    blocked = _pool(store).acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)
    assert isinstance(blocked, Refusal), blocked
    assert blocked.name == "pool-state-stale"


class _ExplodingCeremonies(_Ceremonies):
    def run(self, invocation: CeremonyInvocation) -> CeremonyOutcome:
        self.asked.append(invocation)
        raise RuntimeError("ceremony process failed after unknown progress")


def test_a_ceremony_exception_returns_stale_refusal_and_blocks_reacquisition() -> None:
    store = _store()
    pool = _pool(store, _ExplodingCeremonies())

    refusal = pool.rotate("observed a 401")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-incomplete"
    assert store.live_identity == _SPENT
    assert store.accounts[_HEALTHY].refresh_generation == _LIVE_GENERATION
    assert not store.hook_completed
    blocked = pool.acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)
    assert isinstance(blocked, Refusal), blocked
    assert blocked.name == "pool-state-stale"


def test_a_success_shaped_stale_generation_is_refused_before_state_commit() -> None:
    stale = CeremonyOutcome(
        ceremony="codex-rotate-fallback",
        installed_identity=_HEALTHY,
        installed_generation=_STALE_GENERATION,
        hook_completed=True,
    )
    store = _store()

    refusal = _pool(store, _Ceremonies(stale)).rotate("observed a 401")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-refused-stale-generation"
    assert store.live_identity == _SPENT
    assert store.accounts[_HEALTHY].refresh_generation == _LIVE_GENERATION
    assert not store.hook_completed


def test_a_ceremony_returning_an_unknown_identity_is_refused_without_state_commit() -> None:
    unknown = CeremonyOutcome(
        ceremony="codex-rotate-fallback",
        installed_identity="not-registered@example.test",
        installed_generation=_LIVE_GENERATION + 1,
        hook_completed=True,
    )
    store = _store()

    refusal = _pool(store, _Ceremonies(unknown)).rotate("observed a 401")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-refused-unknown-identity"
    assert store.live_identity == _SPENT
    assert not store.hook_completed
    blocked = _pool(store).acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)
    assert isinstance(blocked, Refusal), blocked
    assert blocked.name == "pool-state-stale"


def test_acquire_ingests_raw_availability_and_holds_one_full_cycle_after_a_cap() -> None:
    store = _store(quotas=("capped", "capped", "capped"))
    pool = _pool(store)
    exhausted = pool.acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)
    assert isinstance(exhausted, Refusal), exhausted

    healthy = store.accounts[_HEALTHY]
    store.accounts[_HEALTHY] = dataclasses.replace(
        healthy, entry={**healthy.entry, "quota_state": "available"}
    )

    first_available = pool.acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)
    second_available = pool.acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)

    assert isinstance(first_available, Refusal), first_available
    assert first_available.name == "credential-pool-exhausted"
    assert not isinstance(second_available, Refusal), second_available


def test_mint_for_an_edge_challenged_identity_is_refused_before_a_request() -> None:
    store = _store()
    account = store.accounts[_HEALTHY]
    store.accounts[_HEALTHY] = dataclasses.replace(
        account, entry={**account.entry, "reach_state": "edge-challenged"}
    )

    refusal = _pool(store).request_mint(_HEALTHY)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "credential-mint-refused-unreachable"


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
    assert isinstance(plan_ceremony(CEREMONIES["cooldown"], ()), Refusal)
    assert isinstance(plan_ceremony(CEREMONIES["cooldown"], ("cap", "rotate")), Refusal)
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


def test_spawn_pins_the_selected_identity_and_home_into_the_attempt_and_guarded_plan() -> None:
    supervisor = _Supervisor(_healthy_pane())
    receipt = _spawn(_binding(pane=_healthy_pane(), supervisor=supervisor))

    assert not isinstance(receipt, Refusal), receipt
    assert supervisor.launched_attempts[0].credential_identity == _HEALTHY
    assert supervisor.launched_attempts[0].credential_home == "/srv/codex-homes/seat-three"
    plan = supervisor.launched_plans[0]
    assert plan.credential_identity == _HEALTHY
    assert plan.credential_home == "/srv/codex-homes/seat-three"
    assert plan.argv == (
        _SEAT,
        "--config-home",
        "/srv/codex-homes/seat-three",
        "--model",
        _spec().probe.model_ref,
    )
