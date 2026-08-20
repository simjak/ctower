"""CT-I1-042 acceptance — the `claude-code` binding, and what the second one earns.

The one shared conformance suite drives this binding through every cell it drives `hermes`
and the fault-injection fake through, unchanged. What is proven here is what that suite
deliberately does not know about: the publication verdict two real bindings unlock, the
provided-pool half of AC-HAD-10 and AC-HAD-11, this harness's own inverted context bar and
limit-menu regression, its transcript-shaped serving truth, and why a failover here is a new
attempt rather than a swap.

Everything below is deterministic: no clock, no randomness, no I/O, no network.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest

from ctower_runner.claude_code.binding import CLAUDE_CODE_PROBE, CLAUDE_CODE_WRAPPER
from ctower_runner.claude_code.corpus import CLAUDE_CODE_CORPUS, captured_cases
from ctower_runner.claude_code.liveness import classify_pane, context_used_pct, pane_digest
from ctower_runner.claude_code.pool import ClaudeCodePool, ConfigHome, ConfigHomeStore
from ctower_runner.claude_code.spawn import failover, wrapper_pin_refusal
from ctower_runner.claude_code.spec import (
    CLAUDE_CODE_KEY,
    CLAUDE_CODE_SATURATION_PERCENT,
    TRANSCRIPT_STALE_AFTER,
    digest_of,
    harness_spec_document,
)
from ctower_runner.claude_code.transcript import (
    SessionTranscript,
    newest_transcript,
    served_model,
    transcript_slug,
)
from ctower_runner.codex.route import CodexRegistrationAuthority
from ctower_runner.hermes.spec import harness_spec_document as hermes_spec_document
from ctower_runner_sdk.attempt import AttemptPin
from ctower_runner_sdk.conformance import CorpusCase
from ctower_runner_sdk.credentials import Lease
from ctower_runner_sdk.refusals import SEAM_MINTED, SPEC_OWNED, Refusal
from ctower_runner_sdk.registry import REQUIRED_REAL_BINDINGS, HarnessRegistry
from ctower_runner_sdk.rotation import RotationEvent
from ctower_runner_sdk.spec import HarnessSpec, parse_harness_spec
from ctower_runner_sdk.survey import derive_roles

__all__: tuple[str, ...] = ()

_NOW = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
_ARTIFACT = digest_of(b"claude-code-artifact-under-test")
_CONFIG = digest_of(b"claude-code-config-home-under-test")
_LEASE_ID = UUID("00000000-0000-4000-8000-000000000001")
_ATTEMPT_ID = UUID("00000000-0000-4000-8000-00000000000a")
_SUCCESSOR_ID = UUID("00000000-0000-4000-8000-00000000000c")
_PROFILE = "engineer"

# A value beside the readable fields that the projection allowlist must leave behind.
_ADJACENT = "ADJACENT-VALUE-THE-ALLOWLIST-MUST-LEAVE-BEHIND"

# The harness reports what is LEFT, so each of these is the consumed half of its own pane.
_USED_AT_8_LEFT = 92
_USED_AT_64_LEFT = 36
_DISTINCT_CLOCKS = 3
_MIN_CAPTURED_CASES = 4
_HOMES: tuple[str, ...] = ("home-a", "home-b", "home-c")


def _document(overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    document = harness_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)
    document.update(overrides or {})
    return document


def _fake_document() -> dict[str, object]:
    """A deterministic fake's declaration, in the shape the registry admits it under."""

    return _document(
        {
            "key": "fault-injection-fake",
            "input_protocol": {"kind": "in_process_fake", "submit_separately": False},
            "output_protocol": {"kind": "in_process_fake"},
            "ack_predicate": {"kind": "in_process_fake", "detail": "the fake acknowledges"},
            "liveness_sources": [
                {"fact": "served_model", "source": "in_process_fake", "proves": "serving"}
            ],
        }
    )


def _spec(overrides: Mapping[str, object] | None = None) -> HarnessSpec:
    parsed = parse_harness_spec(_document(overrides))
    assert isinstance(parsed, HarnessSpec), parsed
    return parsed


def _registration_route(
    document: Mapping[str, object] | None = None,
) -> CodexRegistrationAuthority:
    source = _document() if document is None else document
    parsed = parse_harness_spec(source)
    assert isinstance(parsed, HarnessSpec), parsed
    return CodexRegistrationAuthority(parsed)


def _record(identity: str, quota_state: str, reset_at: datetime, seed: str) -> dict[str, object]:
    """One account file's own metadata, credential fields included on purpose."""

    return {
        "provider_key": "anthropic-claude-code",
        "subscription_identity": identity,
        "entry_label": "claude",
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


def _store(
    *, live: str = "home-a", generations: tuple[int, int, int] = (1, 1, 1)
) -> ConfigHomeStore:
    """Three accounts, three clocks, two of them spent: the shape one word cannot express."""

    records = (
        _record("seat-one@example.test", "capped", _NOW + timedelta(hours=6), "a"),
        _record("seat-two@example.test", "capped", _NOW + timedelta(hours=8), "b"),
        _record("seat-three@example.test", "available", _NOW + timedelta(days=3), "c"),
    )
    homes = {
        slug: ConfigHome(
            slug=slug,
            account_identity=str(record["subscription_identity"]),
            config_dir=f"/srv/claude-homes/{slug}",
            refresh_generation=generation,
            entry=record,
        )
        for slug, record, generation in zip(_HOMES, records, generations, strict=True)
    }
    return ConfigHomeStore(homes=homes, live_slug=live)


def _pool(store: ConfigHomeStore, holder: str = "lane-one") -> ClaudeCodePool:
    return ClaudeCodePool(_spec(), store, _PROFILE, lambda: _NOW, lambda: _LEASE_ID, holder)


def _attempt(
    spec: HarnessSpec, *, harness_ref: str | None = None, composition_digest: str | None = None
) -> AttemptPin:
    return AttemptPin(
        attempt_id=_ATTEMPT_ID,
        epoch=1,
        harness_ref=spec.key if harness_ref is None else harness_ref,
        profile_ref=_PROFILE,
        spec_revision=spec.revision,
        composition_digest=(
            spec.composition_digest() if composition_digest is None else composition_digest
        ),
        intent_model=spec.probe.model_ref,
    )


# ---------------------------------------------------------------- AC-HAD-01: publication


def test_two_real_bindings_plus_one_fake_publish_the_seam() -> None:
    """The row's whole point: the second real binding is what earns publication."""

    registry = HarnessRegistry()

    registry.register(
        hermes_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG),
        "real",
        authority=_registration_route(
            hermes_spec_document(artifact_digest=_ARTIFACT, config_digest=_CONFIG)
        ),
    )
    registry.register(_document(), "real", authority=_registration_route())
    registry.register(
        _fake_document(),
        "fault_injection_fake",
        authority=_registration_route(_fake_document()),
    )

    assert registry.publication() is None
    assert registry.real_bindings() == ("claude-code", "hermes")
    assert len(registry.real_bindings()) >= REQUIRED_REAL_BINDINGS


def test_this_binding_alone_does_not_publish_the_seam() -> None:
    registry = HarnessRegistry()
    registry.register(_document(), "real", authority=_registration_route())
    registry.register(
        _fake_document(),
        "fault_injection_fake",
        authority=_registration_route(_fake_document()),
    )

    refusal = registry.publication()

    assert isinstance(refusal, Refusal)
    assert refusal.name == "harness-seam-unpublished"


def test_the_role_table_derives_provide_on_both_layers_from_the_answers() -> None:
    spec = _spec()

    assert spec.survey.native_pool is False
    assert spec.survey.native_fallback is False
    assert derive_roles(spec.survey) == spec.layers
    assert spec.layers.to_mapping() == {"fallback": "provide", "pool": "provide"}


def test_declaring_configure_over_a_layer_this_harness_lacks_is_refused() -> None:
    """`never both` in its own direction: a claimed native layer that is not there."""

    refusal = HarnessRegistry().register(
        _document({"layers": {"pool": "configure", "fallback": "provide"}}),
        "real",
        authority=_registration_route(),
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-layer-conflict"
    assert dict(refusal.detail)["derived_pool"] == "provide"


def test_an_unanswered_survey_question_refuses_rather_than_leaving_the_role_to_a_guess() -> None:
    survey = dict(cast("dict[str, object]", _document()["survey"]))
    survey.pop("rotation_cache")

    refusal = HarnessRegistry().register(
        _document({"survey": survey}), "real", authority=_registration_route()
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-survey-incomplete"


def test_the_declared_composition_is_pinned_by_key_revision_and_two_digests() -> None:
    spec = _spec()

    assert spec.composition_digest() == f"{CLAUDE_CODE_KEY}@{spec.revision}+{_ARTIFACT}+{_CONFIG}"
    assert spec.pool.cache_invalidation_hook == "config-home-respawn"
    assert spec.context_window_percent == CLAUDE_CODE_SATURATION_PERCENT


def test_serving_truth_is_the_transcript_and_the_launch_argv_proves_only_the_request() -> None:
    """The pane names no model at all, so nothing on screen may be read as agreement."""

    spec = _spec()
    serving = spec.serving_source()
    requests = [source for source in spec.liveness_sources if source.proves == "request"]

    assert serving is not None
    assert serving.source == "session_transcript"
    assert [source.source for source in requests] == ["launch_argv"]
    assert not [
        source
        for source in spec.liveness_sources
        if source.fact == "served_model" and source.source == "pane_footer"
    ]


# ------------------------------------------------------- AC-HAD-04: what the pane actually says


def test_the_limit_menu_is_capped_even_though_it_matches_the_working_pattern() -> None:
    """The regression this classifier exists for: `Esc to cancel` is not `esc to interrupt`."""

    menu = next(case for case in CLAUDE_CODE_CORPUS if "limit menu" in case.label)

    assert "Esc to cancel" in menu.sample
    assert _classify(menu.sample) == "capped"


def test_the_boot_banner_reset_notice_is_not_a_cap() -> None:
    banner = next(case for case in CLAUDE_CODE_CORPUS if "boot banner" in case.label)

    assert "usage limit" in banner.sample
    assert _classify(banner.sample) == "working"


def test_the_context_bar_reports_what_is_left_and_the_reader_inverts_it() -> None:
    assert context_used_pct("Context left until auto-compact: 8%") == _USED_AT_8_LEFT
    assert context_used_pct("Context left until auto-compact: 64%") == _USED_AT_64_LEFT
    assert context_used_pct("no bar on this pane") is None


def test_saturation_wins_over_a_working_marker_and_a_big_token_count_does_not_cause_it() -> None:
    saturated = next(case for case in CLAUDE_CODE_CORPUS if "percent LEFT" in case.label)
    healthy = next(case for case in CLAUDE_CODE_CORPUS if "absolute token count" in case.label)

    assert "esc to interrupt" in saturated.sample
    assert _classify(saturated.sample) == "saturated"
    assert "232k tokens" in healthy.sample
    assert _classify(healthy.sample) == "working"


def test_a_marker_free_pane_is_working_only_on_a_hash_delta() -> None:
    """First sight is a baseline, not evidence: an unchanged pane stays idle."""

    pane = "a pane with no marker this classifier knows"

    assert _classify(pane) == "idle"
    assert classify_pane(pane, saturation_percent=90, pane_changed=True) == "working"
    assert pane_digest(pane) != pane_digest(pane + " ")


@pytest.mark.parametrize("case", CLAUDE_CODE_CORPUS, ids=lambda item: item.label)
def test_every_corpus_case_classifies_to_its_recorded_state(case: CorpusCase) -> None:
    assert _classify(case.sample) == case.expected


def test_the_corpus_is_captured_substrate_and_says_so_where_it_is_not() -> None:
    captured = captured_cases()

    assert len(captured) >= _MIN_CAPTURED_CASES
    assert all("captured" in case.provenance for case in captured)
    assert all(case.provenance.strip() for case in CLAUDE_CODE_CORPUS)
    assert {case.expected for case in CLAUDE_CODE_CORPUS} == {
        "working",
        "idle",
        "capped",
        "saturated",
        "dead_auth",
    }


# ------------------------------------------------------------- AC-HAD-03: serving truth


def test_the_transcript_directory_is_the_panes_cwd_slug() -> None:
    assert transcript_slug("/srv/projects/ctower/.worktrees/t2") == (
        "-srv-projects-ctower--worktrees-t2"
    )


def test_the_newest_transcript_wins_and_an_empty_directory_is_none() -> None:
    entries = (("older.jsonl", _NOW - timedelta(hours=2)), ("newer.jsonl", _NOW))

    assert newest_transcript(entries) == "newer.jsonl"
    assert newest_transcript(()) is None


def test_the_most_recent_real_assistant_turn_is_serving_truth() -> None:
    reading = served_model(_turns("claude-sonnet-5", "claude-opus-5"), age=timedelta(minutes=1))

    assert reading.model == "claude-opus-5"
    assert not reading.is_unknown()


def test_synthetic_turns_are_stepped_over_and_an_all_synthetic_file_is_unknown() -> None:
    skipped = served_model(_turns("claude-opus-5", "<synthetic>"), age=timedelta(minutes=1))
    empty = served_model(_turns("<synthetic>", "<synthetic>"), age=timedelta(minutes=1))

    assert skipped.model == "claude-opus-5"
    assert empty.is_unknown()
    assert "synthetic" in empty.basis


def test_a_stale_or_absent_transcript_is_unknown_by_name_and_never_a_guess() -> None:
    stale = served_model(_turns("claude-opus-5"), age=TRANSCRIPT_STALE_AFTER + timedelta(minutes=1))
    absent = served_model((), age=timedelta(minutes=1))

    assert stale.is_unknown()
    assert absent.is_unknown()
    assert "proves nothing" in stale.basis


def test_an_unparseable_line_is_stepped_over_rather_than_ending_the_read() -> None:
    lines = (*_turns("claude-opus-5"), '{"type":"assistant","message":{"model":')

    assert served_model(lines, age=timedelta(minutes=1)).model == "claude-opus-5"


def test_the_transcript_port_reads_the_newest_file_under_this_attempts_worktree() -> None:
    spec = _spec()
    source = _Transcripts(
        {
            "-attempt-one": (("old.jsonl", _NOW - timedelta(days=1)), ("new.jsonl", _NOW)),
        },
        {"old.jsonl": _turns("claude-sonnet-5"), "new.jsonl": _turns("claude-opus-5")},
    )
    port = SessionTranscript(source, lambda _: "/attempt/one", lambda: _NOW)

    assert port.served_model(_attempt(spec)) == "claude-opus-5"
    assert port.reading(_attempt(spec)).basis == "the most recent real assistant turn"


def test_an_empty_transcript_directory_reports_unknown_and_names_the_slug() -> None:
    spec = _spec()
    port = SessionTranscript(_Transcripts({}, {}), lambda _: "/attempt/two", lambda: _NOW)

    reading = port.reading(_attempt(spec))

    assert reading.is_unknown()
    assert "-attempt-two" in reading.basis


# ------------------------------------------- AC-HAD-10 and AC-HAD-11: the pool ctower provides


def test_one_config_home_per_account_and_the_pool_reports_three_clocks() -> None:
    pool = _pool(_store())

    lease = pool.acquire(model_ref="claude-opus-5", tier=_PROFILE)
    rows = pool.limits()

    assert isinstance(lease, Lease), lease
    assert lease.entry.subscription_identity == "seat-three@example.test"
    assert lease.harness_key == CLAUDE_CODE_KEY
    assert len({row.quota_reset_at for row in rows}) == _DISTINCT_CLOCKS
    assert [row.quota_state for row in rows] == ["capped", "capped", "available"]


def test_observation_projects_the_allowlist_and_leaves_the_adjacent_token_behind() -> None:
    pool = _pool(_store())

    rows = pool.limits()
    lease = pool.acquire(model_ref="claude-opus-5", tier=_PROFILE)
    assert isinstance(lease, Lease), lease
    pool.meter(lease, {"event": "spawn", "model_ref": lease.model_ref})

    bodies = (str([row.to_mapping() for row in rows]), str(lease.to_mapping()), str(pool.metered))
    for body in bodies:
        assert _ADJACENT not in body
        assert "access_token" not in body
        assert "refresh_token" not in body


def test_rotation_writes_the_live_credential_back_before_it_swaps() -> None:
    """The `refresh_token_reused` regression: a snapshot goes stale the moment it is live."""

    store = _store()

    event = _pool(store).rotate("the live account was capped")

    assert isinstance(event, RotationEvent), event
    assert store.journal[0] == "write-back live -> slot home-a"
    assert store.journal[1] == "swap-in slot home-c"
    assert store.journal[2].startswith("invalidate config-home-respawn")
    assert store.live_slug == "home-c"
    assert (
        store.homes["home-a"].refresh_generation
        == store.last_live_generation["seat-one@example.test"]
    )


def test_a_snapshot_older_than_the_live_generation_is_refused_and_nothing_swaps() -> None:
    store = _store(generations=(1, 1, 1))
    store.last_live_generation["seat-three@example.test"] = 4

    refusal = _pool(store).rotate("the live account was capped")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-refused-stale-generation"
    assert store.live_slug == "home-a"
    assert not [step for step in store.journal if step.startswith("swap-in")]
    assert dict(refusal.detail)["live_generation"] == "4"


def test_a_second_holder_is_refused_before_anything_is_written() -> None:
    store = _store()
    store.holder = "lane-two"

    refusal = _pool(store, holder="lane-one").rotate("the live account was capped")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-refused-concurrent-holder"
    assert store.journal == []
    assert store.live_slug == "home-a"


def test_a_rotation_whose_hook_cannot_complete_is_incomplete_rather_than_done() -> None:
    store = _store()
    store.respawn_completes = False

    refusal = _pool(store).rotate("the live account was capped")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-incomplete"
    assert dict(refusal.detail)["hook"] == "config-home-respawn"
    assert store.journal[-1].endswith("incomplete")


def test_no_entry_state_is_believed_before_the_invalidation_hook_completes() -> None:
    store = _store()
    store.respawn_completes = False
    pool = _pool(store)
    pool.rotate("the live account was capped")

    refusal = pool.acquire(model_ref="claude-opus-5", tier=_PROFILE)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "pool-state-stale"
    assert refusal.name != "credential-pool-exhausted"


def test_a_completed_rotation_is_metered_at_exactly_one_context_reread() -> None:
    event = _pool(_store()).rotate("the live account was capped")

    assert isinstance(event, RotationEvent), event
    assert event.context_rereads == 1
    assert event.layer == "pool"
    assert event.entry_identity == "seat-three@example.test"


def test_the_provided_pool_interface_has_no_copy_path() -> None:
    """The absent verb is the design: a copied auth file replays a consumed refresh token."""

    verbs = {name for name in dir(_pool(_store())) if not name.startswith("_")}

    assert not [name for name in verbs if "copy" in name or "install" in name or "snapshot" in name]
    assert {"acquire", "meter", "limits", "rotate", "probe", "request_mint"} <= verbs


def test_a_mint_is_requested_against_this_harnesss_own_provider_and_never_performed() -> None:
    request = _pool(_store()).request_mint("seat-four@example.test")

    assert request.provider_key == "anthropic-claude-code"
    assert request.enactment == "operator-ceremony"


def test_an_exhausted_pool_refuses_with_the_whole_diagnosis_rather_than_one_word() -> None:
    store = _store()
    for slug in _HOMES:
        home = store.homes[slug]
        store.homes[slug] = replace(home, entry={**dict(home.entry), "quota_state": "capped"})

    refusal = _pool(store).acquire(model_ref="claude-opus-5", tier=_PROFILE)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "credential-pool-exhausted"
    assert dict(refusal.detail)["earliest_known_reset"] == (_NOW + timedelta(hours=6)).isoformat()
    assert _ADJACENT not in str(refusal.to_mapping())


# ----------------------------------------- AC-HAD-07 and AC-HAD-09: the wrapper and the failover


def test_the_wrapper_plan_names_the_launcher_the_guard_decides_about() -> None:
    assert CLAUDE_CODE_WRAPPER.endswith(".sh")
    assert CLAUDE_CODE_PROBE == "claude-code-capture-pane"


def test_an_attempt_pinned_to_another_composition_dispatches_nothing() -> None:
    spec = _spec()
    observed = "  Claude-Code/FORK v2  "

    refusal = wrapper_pin_refusal(
        spec, _attempt(spec, harness_ref=observed, composition_digest="claude-code@1+sha256:x")
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-spec-digest-mismatch"
    assert dict(refusal.detail)["observed_harness_ref"] == observed


def test_an_attempt_pinned_to_this_spec_is_not_refused() -> None:
    spec = _spec()

    assert wrapper_pin_refusal(spec, _attempt(spec)) is None


def test_failover_after_a_checkpoint_is_a_new_attempt_and_never_a_later_epoch() -> None:
    spec = _spec()
    attempt = _attempt(spec)
    lease = _pool(_store()).acquire(model_ref="claude-opus-5", tier=_PROFILE)
    assert isinstance(lease, Lease), lease

    successor = failover(spec, attempt, successor_id=_SUCCESSOR_ID, lease=lease, checkpointed=True)

    assert not isinstance(successor, Refusal), successor
    assert successor.attempt_id != attempt.attempt_id
    assert successor.lease_id == lease.lease_id != attempt.lease_id
    assert not successor.supersedes(attempt)
    assert successor.intent_model == attempt.intent_model


def test_an_in_session_swap_is_refused_because_this_harness_declares_no_rung() -> None:
    spec = _spec()
    lease = _pool(_store()).acquire(model_ref="claude-opus-5", tier=_PROFILE)
    assert isinstance(lease, Lease), lease

    refusal = failover(
        spec, _attempt(spec), successor_id=_SUCCESSOR_ID, lease=lease, checkpointed=False
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-capability-unsupported"
    assert dict(refusal.detail)["layer"] == "fallback"
    assert "respawn" in refusal.action


def test_every_refusal_this_binding_raises_is_inside_the_seam_vocabulary() -> None:
    """A binding may not mint a private refusal name; the seam owns the whole vocabulary."""

    store = _store()
    store.holder = "lane-two"
    held = _pool(store).rotate("the live account was capped")
    stale_store = _store()
    stale_store.last_live_generation["seat-three@example.test"] = 4
    stale = _pool(stale_store).rotate("the live account was capped")

    for refusal in (held, stale):
        assert isinstance(refusal, Refusal), refusal
        assert refusal.name in SEAM_MINTED | SPEC_OWNED
        assert refusal.observed and refusal.meaning and refusal.action


def _classify(sample: str) -> str:
    return classify_pane(sample, saturation_percent=CLAUDE_CODE_SATURATION_PERCENT)


def _turns(*models: str) -> tuple[str, ...]:
    return tuple(json.dumps({"type": "assistant", "message": {"model": model}}) for model in models)


@dataclass(frozen=True, slots=True)
class _Transcripts:
    """One stated transcript directory. No filesystem, no clock, no ordering surprises."""

    listing: dict[str, tuple[tuple[str, datetime], ...]]
    bodies: dict[str, tuple[str, ...]]

    def entries(self, slug: str) -> tuple[tuple[str, datetime], ...]:
        return self.listing.get(slug, ())

    def lines(self, name: str) -> tuple[str, ...]:
        return self.bodies.get(name, ())
