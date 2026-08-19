"""CT-I1-042 acceptance — the `claude-code` binding's own half, before the seam lands.

This harness ships neither a credential pool nor an in-session fallback, so ctower PROVIDES
both layers. Everything proven here is binding-private and therefore independent of
CT-I1-041: how a Claude Code pane is read, where its serving truth comes from, what a
ctower-operated rotation is allowed to do, and why a failover on this harness is a new
attempt rather than a swap.

The seam-facing half — the `HarnessBinding` implementation, the shared conformance suite,
and the two-real-bindings publication proof — is deliberately absent and marked at each
integration point. It arrives on the rebase onto the landed seam.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from ctower_runner.claude_code.corpus import CLAUDE_CODE_CORPUS, CorpusCase
from ctower_runner.claude_code.liveness import context_used_pct, pane_digest, read_pane
from ctower_runner.claude_code.pool import (
    PROVIDED_POOL_VERBS,
    ConfigHome,
    ConfigHomeStore,
    RotationOutcome,
    believe_entry_state,
    rotate,
)
from ctower_runner.claude_code.refusal import Refusal
from ctower_runner.claude_code.spawn import (
    AttemptComposition,
    SpawnPlan,
    failover,
    spawn_path_refusal,
)
from ctower_runner.claude_code.spec import (
    CLAUDE_CODE_KEY,
    CLAUDE_CODE_SATURATION_PERCENT,
    TRANSCRIPT_STALE_AFTER,
    digest_of,
    harness_spec_document,
    layer_roles,
)
from ctower_runner.claude_code.transcript import (
    newest_transcript,
    served_model,
    transcript_slug,
)

__all__: tuple[str, ...] = ()

_NOW = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
_ARTIFACT = digest_of(b"claude-code-artifact-under-test")
_CONFIG = digest_of(b"claude-code-config-home-under-test")

# The harness reports what is LEFT, so each of these is the consumed half of its own pane.
_USED_AT_8_LEFT = 92
_USED_AT_77_LEFT = 23

# The generation the live account has reached by the time the rotation is asked for.
_LIVE_GENERATION = 9
_HEALTHY_FOOTER = (
    "✻ Newspapering… (6m 21s · ↑ 23.2k tokens · thought for 2s)\n"
    "  ⏵⏵ bypass permissions on (shift+tab to cycle) · esc to interrupt · ← 1 agent\n"
)


def _document() -> dict[str, object]:
    return harness_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)


def _section(name: str) -> dict[str, object]:
    section = _document()[name]
    assert isinstance(section, dict)
    return section


def _turn(model: str) -> str:
    return json.dumps({"type": "assistant", "message": {"model": model}})


def _store() -> ConfigHomeStore:
    """Three subscriptions, three config homes. Topology A: one account per home."""

    return ConfigHomeStore(
        homes={
            "home-a": ConfigHome("home-a", "one@example.test", "~/.mc/claude/home-a", 7),
            "home-b": ConfigHome("home-b", "two@example.test", "~/.mc/claude/home-b", 3),
            "home-c": ConfigHome("home-c", "three@example.test", "~/.mc/claude/home-c", 1),
        },
        live_slug="home-a",
        last_live_generation={"one@example.test": 7, "two@example.test": 3},
    )


def _composition(account_slug: str = "home-a") -> AttemptComposition:
    return AttemptComposition(
        harness_key=CLAUDE_CODE_KEY,
        spec_revision=1,
        artifact_digest=_ARTIFACT,
        config_digest=_CONFIG,
        account_slug=account_slug,
    )


# --- The answered survey and the roles it forces -----------------------------------------


def test_survey_is_answered_and_forces_provide_on_both_layers() -> None:
    survey = _section("survey")
    assert survey["native_pool"] is False
    assert survey["native_fallback"] is False
    assert layer_roles(survey) == {"pool": "provide", "fallback": "provide"}


def test_document_declares_every_field_the_row_names() -> None:
    document = _document()
    required = (
        "key",
        "revision",
        "artifact_digest",
        "config_digest",
        "input_protocol",
        "output_protocol",
        "capabilities",
        "ack_predicate",
        "liveness_sources",
        "context_window_percent",
        "probe",
        "pool",
        "survey",
        "layers",
    )
    assert document["key"] == CLAUDE_CODE_KEY
    assert [name for name in required if name not in document] == []


def test_the_declared_layers_match_the_survey_so_never_both_is_checkable() -> None:
    assert _document()["layers"] == layer_roles(_section("survey"))


def test_the_pool_declares_the_hook_a_rotation_is_incomplete_without() -> None:
    assert _section("pool")["cache_invalidation_hook"] == "config-home-respawn"


def test_served_model_is_declared_from_the_transcript_and_never_from_a_footer() -> None:
    sources = _document()["liveness_sources"]
    assert isinstance(sources, list)
    serving = [item for item in sources if item["fact"] == "served_model"]
    assert [item["source"] for item in serving if item["proves"] == "serving"] == [
        "session_transcript"
    ]
    assert "pane_footer" not in {item["source"] for item in serving}


# --- Liveness: cap and saturation before any working marker ------------------------------


def test_the_limit_menu_is_capped_even_though_it_matches_the_working_pattern() -> None:
    """The regression the row names: `Esc to cancel` matched the generic working pattern.

    A rate-limit-dead lane counted as working for hours on the critical path.
    """

    pane = (
        "You've reached your Opus limit · resets 6pm\n"
        "  1. Switch models  2. Upgrade your plan\n"
        "  Enter to confirm · Esc to cancel\n"
    )
    assert read_pane(pane, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT).state == "capped"


def test_out_of_credits_text_is_capped() -> None:
    pane = "You are out of credits. Add credits with /usage-credits to continue.\n"
    assert read_pane(pane, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT).state == "capped"


def test_the_boot_banner_reset_notice_is_not_a_cap() -> None:
    pane = "2 usage limit resets available\n" + _HEALTHY_FOOTER
    assert read_pane(pane, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT).state == "working"


def test_the_context_bar_reports_used_not_left() -> None:
    """Claude Code prints percent LEFT. Reading it as used inverts the whole signal."""

    assert context_used_pct("Context left until auto-compact: 8%") == _USED_AT_8_LEFT
    assert context_used_pct("Context left until auto-compact: 77%") == _USED_AT_77_LEFT
    assert context_used_pct(_HEALTHY_FOOTER) is None


def test_a_pane_at_or_past_the_declared_window_is_saturated_over_its_working_marker() -> None:
    pane = "Context left until auto-compact: 8%\n" + _HEALTHY_FOOTER
    reading = read_pane(pane, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT)
    assert reading.state == "saturated"
    assert reading.context_used_pct == _USED_AT_8_LEFT


def test_a_healthy_lane_at_the_same_absolute_token_count_is_not_flagged() -> None:
    """`23.2k tokens` is an absolute counter; only the percentage decides saturation."""

    pane = "Context left until auto-compact: 77%\n" + _HEALTHY_FOOTER
    reading = read_pane(pane, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT)
    assert reading.state == "working"
    assert reading.context_used_pct == _USED_AT_77_LEFT


def test_a_coverage_percentage_in_scrolled_output_does_not_trip_saturation() -> None:
    pane = "TOTAL      1204     41    97%\nRequired test coverage of 95% reached.\n"
    reading = read_pane(pane + _HEALTHY_FOOTER, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT)
    assert reading.context_used_pct is None
    assert reading.state == "working"


def test_a_running_shell_with_no_interrupt_hint_is_working() -> None:
    pane = (
        "✻ Sautéed for 3m 30s · 1 shell still running\n"
        "  ⏵⏵ bypass permissions on · 1 shell · ← 1 agent · ↓ to manage\n"
    )
    assert read_pane(pane, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT).state == "working"


def test_a_logged_out_pane_is_dead_auth_and_never_working() -> None:
    pane = "Not logged in · Run /login\n" + _HEALTHY_FOOTER
    assert read_pane(pane, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT).state == "dead_auth"


def test_a_marker_free_pane_is_working_only_on_a_hash_delta() -> None:
    pane = "  Maya republish.\n"
    quiet = read_pane(pane, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT)
    moving = read_pane(pane, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT, pane_changed=True)
    assert quiet.state == "idle"
    assert moving.state == "working"
    assert pane_digest(pane) != pane_digest(pane + "x")


@pytest.mark.parametrize("case", CLAUDE_CODE_CORPUS, ids=lambda case: case.label)
def test_every_captured_corpus_case_classifies_to_its_recorded_state(case: CorpusCase) -> None:
    reading = read_pane(case.sample, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT)
    assert reading.state == case.expected
    assert case.provenance


def test_the_corpus_covers_every_state_this_binding_can_report() -> None:
    assert {case.expected for case in CLAUDE_CODE_CORPUS} == {
        "capped",
        "saturated",
        "working",
        "idle",
        "dead_auth",
    }


# --- Served model: the transcript under the pane's cwd -----------------------------------


def test_the_transcript_directory_is_the_panes_cwd_slug() -> None:
    assert transcript_slug("/srv/projects/ctower/.worktrees/t2-claude") == (
        "-srv-projects-ctower--worktrees-t2-claude"
    )


def test_the_newest_transcript_wins_and_an_empty_directory_is_none() -> None:
    entries = (
        ("older.jsonl", _NOW - timedelta(minutes=30)),
        ("newer.jsonl", _NOW - timedelta(minutes=2)),
    )
    assert newest_transcript(entries) == "newer.jsonl"
    assert newest_transcript(()) is None


def test_the_most_recent_real_assistant_turn_is_serving_truth() -> None:
    lines = (_turn("claude-opus-5"), _turn("claude-sonnet-5"))
    reading = served_model(lines, age=timedelta(minutes=3))
    assert reading.model == "claude-sonnet-5"
    assert not reading.is_unknown()


def test_synthetic_turns_are_skipped_rather_than_reported() -> None:
    lines = (_turn("claude-opus-5"), _turn("<synthetic>"), _turn("<synthetic>"))
    assert served_model(lines, age=timedelta(minutes=3)).model == "claude-opus-5"


def test_an_all_synthetic_transcript_is_unknown_by_name() -> None:
    reading = served_model((_turn("<synthetic>"),), age=timedelta(minutes=3))
    assert reading.is_unknown()
    assert "synthetic" in reading.basis


def test_a_transcript_stale_beyond_one_hour_proves_nothing() -> None:
    lines = (_turn("claude-opus-5"),)
    assert served_model(lines, age=TRANSCRIPT_STALE_AFTER + timedelta(seconds=1)).is_unknown()
    assert served_model(lines, age=TRANSCRIPT_STALE_AFTER).model == "claude-opus-5"


def test_an_absent_transcript_is_unknown_and_never_a_guess() -> None:
    reading = served_model((), age=timedelta(minutes=1))
    assert reading.is_unknown()
    assert reading.model is None


def test_an_unparseable_line_is_stepped_over_rather_than_ending_the_read() -> None:
    lines = ("{not json", _turn("claude-opus-5"))
    assert served_model(lines, age=timedelta(minutes=1)).model == "claude-opus-5"


# --- The provided pool: topology A, and what a ctower rotation may do ---------------------


def test_one_config_home_per_account_and_no_two_accounts_share_one() -> None:
    homes = tuple(_store().homes.values())
    assert len({home.config_dir for home in homes}) == len(homes)
    assert len({home.account_identity for home in homes}) == len(homes)


def test_rotation_writes_the_live_credential_back_before_it_swaps() -> None:
    """The `refresh_token_reused` regression: a stale slot killed the codex snapshots."""

    store = _store()
    outcome = rotate(
        store, target_slug="home-b", holder="engineer-t2", live_generation=_LIVE_GENERATION
    )
    assert isinstance(outcome, RotationOutcome)
    assert outcome.steps[0] == "write-back live -> slot home-a"
    assert outcome.steps[1] == "swap-in slot home-b"
    assert store.homes["home-a"].refresh_generation == _LIVE_GENERATION
    assert store.live_slug == "home-b"


def test_a_snapshot_older_than_the_live_generation_is_refused_and_nothing_swaps() -> None:
    store = _store()
    store.homes["home-b"] = ConfigHome("home-b", "two@example.test", "~/.mc/claude/home-b", 2)
    outcome = rotate(
        store, target_slug="home-b", holder="engineer-t2", live_generation=_LIVE_GENERATION
    )
    assert isinstance(outcome, Refusal)
    assert outcome.name == "rotation-refused-stale-generation"
    assert store.live_slug == "home-a"
    assert store.journal == ("write-back live -> slot home-a",)


def test_a_second_holder_is_refused_before_anything_is_written() -> None:
    store = _store()
    store.holder = "engineer-t1"
    outcome = rotate(
        store, target_slug="home-b", holder="engineer-t2", live_generation=_LIVE_GENERATION
    )
    assert isinstance(outcome, Refusal)
    assert outcome.name == "rotation-refused-concurrent-holder"
    assert store.journal == ()
    assert store.live_slug == "home-a"


def test_no_entry_state_is_believed_before_the_invalidation_hook_completes() -> None:
    store = _store()
    outcome = rotate(
        store,
        target_slug="home-b",
        holder="engineer-t2",
        live_generation=_LIVE_GENERATION,
        invalidate=False,
    )
    assert isinstance(outcome, RotationOutcome)
    assert not outcome.hook_completed
    refusal = believe_entry_state(outcome, observed_state="available")
    assert isinstance(refusal, Refusal)
    assert refusal.name == "rotation-incomplete"


def test_an_entry_state_after_the_hook_is_believed_and_the_hook_is_journalled() -> None:
    store = _store()
    outcome = rotate(
        store, target_slug="home-b", holder="engineer-t2", live_generation=_LIVE_GENERATION
    )
    assert isinstance(outcome, RotationOutcome)
    assert outcome.hook_completed
    assert outcome.steps[-1] == "invalidate config-home-respawn"
    assert believe_entry_state(outcome, observed_state="available") == "available"


def test_the_provided_pool_interface_has_no_copy_path() -> None:
    forbidden = ("copy", "install", "snapshot", "import")
    assert "request_mint" in PROVIDED_POOL_VERBS
    assert [verb for verb in PROVIDED_POOL_VERBS if any(bad in verb for bad in forbidden)] == []


# --- Spawn: the wrapper's own refusal, and failover as a new attempt ----------------------


def test_the_wrapper_spawn_path_refuses_on_its_own_rather_than_on_argv() -> None:
    """`bin/mux`'s basename(argv0) check cannot see through a mktemp wrapper script."""

    plan = SpawnPlan(
        program="claude",
        wrapper_script="/tmp/claude-crew-engineer.XXXX.sh",  # noqa: S108
        declared_harness=CLAUDE_CODE_KEY,
        guard_basis="launched_argv",
    )
    refusal = spawn_path_refusal(plan)
    assert isinstance(refusal, Refusal)
    assert refusal.name == "harness-spawn-argv-unverifiable"


def test_a_plan_guarded_on_its_own_declaration_is_not_refused() -> None:
    plan = SpawnPlan(
        program="claude",
        wrapper_script="/tmp/claude-crew-engineer.XXXX.sh",  # noqa: S108
        declared_harness=CLAUDE_CODE_KEY,
        guard_basis="declared_plan",
    )
    assert spawn_path_refusal(plan) is None


def test_failover_after_a_checkpoint_is_a_new_attempt_with_a_different_pin() -> None:
    before = _composition()
    after = failover(before, to_account_slug="home-b", checkpointed=True)
    assert isinstance(after, AttemptComposition)
    assert after.pin() != before.pin()
    assert after.account_slug == "home-b"


def test_an_in_session_swap_is_refused_because_this_harness_has_no_rung() -> None:
    refusal = failover(_composition(), to_account_slug="home-b", checkpointed=False)
    assert isinstance(refusal, Refusal)
    assert refusal.name == "harness-in-session-swap-refused"


def test_every_refusal_carries_observed_meaning_and_action() -> None:
    store = _store()
    store.holder = "engineer-t1"
    refusal = rotate(
        store, target_slug="home-b", holder="engineer-t2", live_generation=_LIVE_GENERATION
    )
    assert isinstance(refusal, Refusal)
    body = refusal.to_mapping()
    assert all(body[field] for field in ("observed", "meaning", "action"))
