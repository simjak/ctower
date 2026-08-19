"""AC-HAD-10 and AC-HAD-11 — three axes, one allowlist, and a probe that measured the rung.

AUTH is not QUOTA is not REACH. A capped account passes login and refuses work, a dead
lineage may sit on untouched quota, and an entry with both healthy can still be unreachable
because the provider's edge is challenging our egress. Every tool that has flattened those
into one status has eventually told someone to run the wrong ceremony — a re-mint against a
credential that was never broken, burning a fresh single-use device flow to no effect.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest
from ctower_contracts import validator_for
from harness_doubles import BASE_TIME, StubEngine, SubstrateState, lease_ids, pool_records
from harness_subjects import PROFILE_KEY, build_hermes, hermes_document, subjects

from ctower_runner.hermes.pool import HermesPool
from ctower_runner_sdk.conformance import ConformanceSubject
from ctower_runner_sdk.credentials import (
    ENTRY_ALLOWLIST,
    LEASE_SCHEMA_REF,
    CredentialPool,
    EntryState,
    Lease,
    ProbeResponse,
    exhaustion_refusal,
    project_entry,
    selectable,
)
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.rotation import FlapWindow, RotationEvent, classify_probe, record_rotation
from ctower_runner_sdk.spec import HarnessSpec, parse_harness_spec

__all__: tuple[str, ...] = ()

_RESET = BASE_TIME + timedelta(hours=6)
_ADJACENT = "ADJACENT-VALUE-THE-ALLOWLIST-MUST-LEAVE-BEHIND"
_TOKEN_FIELDS = ("access_token", "refresh_token")
_DISTINCT_CLOCKS = 3


def _spec() -> HarnessSpec:
    parsed = parse_harness_spec(hermes_document())
    assert isinstance(parsed, HarnessSpec), parsed
    return parsed


def _pool(*, lag: int = 0) -> HermesPool:
    state = SubstrateState(pane="", invalidation_lag_seconds=lag)
    engine = StubEngine(state, pool_records(_RESET), PROFILE_KEY)
    return HermesPool(_spec(), engine, PROFILE_KEY, lambda: BASE_TIME, lease_ids)


def _entry(**overrides: object) -> EntryState:
    base = project_entry(pool_records(_RESET)[2])
    return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]


@pytest.mark.parametrize("subject", subjects(), ids=lambda item: item.name)
def test_the_pool_interface_exposes_no_copy_verb(subject: ConformanceSubject) -> None:
    verbs = {name for name in dir(subject.pool) if not name.startswith("_")}
    protocol = {name for name in dir(CredentialPool) if not name.startswith("_")}

    assert not [name for name in verbs | protocol if "copy" in name or "install" in name]
    assert {"acquire", "meter", "limits", "rotate", "probe", "request_mint"} <= protocol


@pytest.mark.parametrize("subject", subjects(), ids=lambda item: item.name)
def test_every_lease_validates_against_the_contract_that_authored_its_shape(
    subject: ConformanceSubject,
) -> None:
    """A contract nothing validates against drifts from its producer silently.

    The lease is the only value the seam hands a binding about a credential, so the second
    binding builds against this shape. It reads the same on both planes because these are
    the kernel's own pool-observation names rather than a second vocabulary for one fact.
    """

    lease = subject.pool.acquire(model_ref=subject.binding.spec.probe.model_ref, tier=PROFILE_KEY)

    assert isinstance(lease, Lease), lease
    errors = sorted(
        validator_for(LEASE_SCHEMA_REF).iter_errors(lease.to_mapping()),
        key=lambda error: error.json_path,
    )
    assert not [f"{error.json_path}: {error.message}" for error in errors]


def test_a_mixed_pool_acquires_from_its_healthy_entry_and_reports_three_clocks() -> None:
    pool = _pool()

    lease = pool.acquire(model_ref="gpt-5.6-sol", tier=PROFILE_KEY)
    rows = pool.limits()

    assert isinstance(lease, Lease), lease
    assert lease.entry.subscription_identity == "seat-three@example.test"
    assert len({row.quota_reset_at for row in rows}) == _DISTINCT_CLOCKS
    assert [row.quota_state for row in rows] == ["capped", "capped", "available"]


def test_limits_returns_per_entry_rows_and_never_an_aggregate_verdict() -> None:
    rows = _pool().limits()

    assert all(isinstance(row, EntryState) for row in rows)
    assert not [name for name in dir(rows) if "verdict" in name or "status" in name]


def test_observation_projects_a_named_allowlist_and_leaves_the_adjacent_token_behind() -> None:
    raw = pool_records(_RESET)
    assert any(field in record for record in raw for field in _TOKEN_FIELDS)

    rows = _pool().limits()

    body = str([row.to_mapping() for row in rows])
    assert _ADJACENT not in body
    assert not [field for field in _TOKEN_FIELDS if field in body]
    assert set(rows[0].to_mapping()) == set(ENTRY_ALLOWLIST)


def test_an_entry_is_selectable_only_when_all_three_axes_and_its_registration_are_clear() -> None:
    assert selectable(_entry())
    assert not selectable(_entry(auth_state="lineage-dead"))
    assert not selectable(_entry(quota_state="unknown"))
    assert not selectable(_entry(reach_state="edge-challenged"))
    assert not selectable(_entry(registration_state="discovered"))


def test_a_discovered_identity_is_never_selectable_however_reachable_it_is() -> None:
    discovered = _entry(registration_state="discovered")

    assert not selectable(discovered)
    assert ("registration", "discovered") in discovered.blocking_axes()


def test_entries_are_keyed_by_identity_and_a_shared_label_hides_nothing() -> None:
    rows = _pool().limits()
    labels = [row.entry_label for row in rows]
    identities = [row.subscription_identity for row in rows]

    assert len(set(labels)) < len(set(identities))
    assert len(set(identities)) == len(rows)


def test_exhaustion_names_the_meaning_and_the_action_for_every_blocked_axis() -> None:
    refusal = exhaustion_refusal(
        (
            _entry(quota_state="capped", quota_reset_at=_RESET),
            _entry(reach_state="edge-challenged", quota_reset_at=_RESET + timedelta(hours=2)),
            _entry(auth_state="lineage-dead", quota_reset_at=None),
        )
    )

    assert refusal.name == "credential-pool-exhausted"
    assert "re-mint" in refusal.action
    assert "Never a mint" in refusal.action
    assert "wait for the provider" in refusal.action
    assert dict(refusal.detail)["earliest_known_reset"] == _RESET.isoformat()


def test_a_stale_pool_reading_is_never_classified_as_real_exhaustion() -> None:
    refusal = _pool(lag=30).acquire(model_ref="gpt-5.6-sol", tier=PROFILE_KEY)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "pool-state-stale"
    assert refusal.name != "credential-pool-exhausted"


def test_a_rotation_is_incomplete_until_its_declared_hook_completes() -> None:
    refusal = _pool(lag=30).rotate("observed a 429")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-incomplete"
    assert dict(refusal.detail)["hook"] == "pool-proxy-restart"


def test_a_completed_rotation_is_metered_at_exactly_one_context_reread() -> None:
    event = _pool().rotate("observed a 429")

    assert isinstance(event, RotationEvent), event
    assert event.context_rereads == 1
    assert event.layer == "pool"


def test_a_rotation_against_a_challenged_edge_is_refused_rather_than_attempted() -> None:
    refusal = record_rotation(
        reason="observed a 403",
        layer="pool",
        hook="pool-proxy-restart",
        hook_completed=True,
        entry=_entry(reach_state="edge-challenged"),
        completed_at=BASE_TIME,
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "rotation-refused-unreachable"
    assert "infra plane" in refusal.action


def test_a_challenge_page_is_a_reachability_fact_and_never_a_dead_lineage() -> None:
    reading = classify_probe(
        _spec().probe,
        ProbeResponse(
            status_code=403,
            body="<html>Just a moment... cf_chl_opt</html>",
            model_ref="gpt-5.6-sol",
            drawn_from_pool=True,
            after_invalidation=True,
        ),
    )

    assert not isinstance(reading, Refusal), reading
    assert reading.reach == "edge-challenged"
    assert reading.auth != "lineage-dead"


def test_a_401_is_a_dead_lineage_and_the_two_are_not_one_word() -> None:
    reading = classify_probe(
        _spec().probe,
        ProbeResponse(
            status_code=401,
            body='{"error":"invalid_grant"}',
            model_ref="gpt-5.6-sol",
            drawn_from_pool=True,
            after_invalidation=True,
        ),
    )

    assert not isinstance(reading, Refusal), reading
    assert reading.auth == "lineage-dead"
    assert reading.reach == "ok"


def test_a_200_with_empty_content_is_a_hang_and_never_capacity() -> None:
    reading = classify_probe(
        _spec().probe,
        ProbeResponse(
            status_code=200,
            body="   ",
            model_ref="gpt-5.6-sol",
            drawn_from_pool=True,
            after_invalidation=True,
        ),
    )

    assert not isinstance(reading, Refusal), reading
    assert reading.is_unknown()
    assert "hang" in reading.basis


def test_a_probe_aimed_at_another_model_reports_unknown_for_the_seats_rung() -> None:
    reading = classify_probe(
        _spec().probe,
        ProbeResponse(
            status_code=200,
            body="served",
            model_ref="some-other-model",
            drawn_from_pool=True,
            after_invalidation=True,
        ),
    )

    assert not isinstance(reading, Refusal), reading
    assert reading.is_unknown()
    assert "seats' rung" in reading.basis


@pytest.mark.parametrize(
    ("drawn", "after", "fragment"),
    (
        (False, True, "own entries"),
        (True, False, "before the cache-invalidation hook"),
    ),
)
def test_a_probe_from_outside_the_pool_or_before_invalidation_reports_unknown(
    *, drawn: bool, after: bool, fragment: str
) -> None:
    reading = classify_probe(
        _spec().probe,
        ProbeResponse(
            status_code=200,
            body="served",
            model_ref="gpt-5.6-sol",
            drawn_from_pool=drawn,
            after_invalidation=after,
        ),
    )

    assert not isinstance(reading, Refusal), reading
    assert reading.is_unknown()
    assert fragment in reading.basis


def test_a_one_token_probe_reports_unknown_rather_than_a_window() -> None:
    shape = dataclasses.replace(_spec().probe, workload_shape="single_token")

    reading = classify_probe(
        shape,
        ProbeResponse(
            status_code=200,
            body="served",
            model_ref="gpt-5.6-sol",
            drawn_from_pool=True,
            after_invalidation=True,
        ),
    )

    assert not isinstance(reading, Refusal), reading
    assert reading.is_unknown()


def test_a_status_code_only_classifier_is_refused_as_a_state_source() -> None:
    shape = dataclasses.replace(_spec().probe, classified_on="status_line")

    refusal = classify_probe(
        shape,
        ProbeResponse(
            status_code=402,
            body="out of credits",
            model_ref="gpt-5.6-sol",
            drawn_from_pool=True,
            after_invalidation=True,
        ),
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "pool-probe-classifier-refused"


def test_a_window_returning_to_available_holds_one_full_cycle_before_it_is_selectable() -> None:
    window = FlapWindow(consecutive_available=0)

    first = window.observe(available=True)
    second = first.observe(available=True)
    relapse = second.observe(available=False)

    assert not first.is_selectable()
    assert second.is_selectable()
    assert not relapse.is_selectable()


def test_a_flapping_entry_is_not_leased_until_it_holds_its_cycle() -> None:
    pool = _pool()
    pool.observe_window("seat-three@example.test", available=True)

    first = pool.acquire(model_ref="gpt-5.6-sol", tier=PROFILE_KEY)
    pool.observe_window("seat-three@example.test", available=True)
    second = pool.acquire(model_ref="gpt-5.6-sol", tier=PROFILE_KEY)

    assert isinstance(first, Refusal), first
    assert first.name == "credential-pool-exhausted"
    assert isinstance(second, Lease), second


def test_a_mint_is_requested_and_never_performed() -> None:
    request = build_hermes().pool.request_mint("seat-four@example.test")

    assert request.enactment == "operator-ceremony"
    assert request.subscription_identity == "seat-four@example.test"


def test_no_credential_value_reaches_a_lease_a_refusal_or_a_rotation_event() -> None:
    pool = _pool()

    lease = pool.acquire(model_ref="gpt-5.6-sol", tier=PROFILE_KEY)
    rotation = pool.rotate("observed a 429")
    exhausted = exhaustion_refusal((_entry(quota_state="capped"),))
    stale = _pool(lag=30).acquire(model_ref="gpt-5.6-sol", tier=PROFILE_KEY)

    assert isinstance(lease, Lease), lease
    assert isinstance(rotation, RotationEvent), rotation
    assert isinstance(stale, Refusal), stale
    bodies = (
        str(lease.to_mapping()),
        str(rotation.to_mapping()),
        str(exhausted.to_mapping()),
        str(stale.to_mapping()),
    )
    for body in bodies:
        assert _ADJACENT not in body
        assert not [field for field in _TOKEN_FIELDS if field in body]


def test_a_metered_observation_carries_no_credential_value_either() -> None:
    pool = _pool()
    lease = pool.acquire(model_ref="gpt-5.6-sol", tier=PROFILE_KEY)
    assert isinstance(lease, Lease), lease

    pool.meter(lease, {"event": "spawn", "model_ref": lease.model_ref})

    body = str(pool.metered)
    assert _ADJACENT not in body
    assert not [field for field in _TOKEN_FIELDS if field in body]
