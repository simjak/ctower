"""RED-first unit contract for the complete Phase-1 ConsoleViewGrant decision."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from ctower_kernel.console import (
    ConsoleGlobalSwitchCommand,
    ConsoleGrantFacts,
    ConsoleGrantIdentifiers,
    ConsoleOutputBatch,
    ConsolePolicy,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleViewGrant,
    decide_view_grant,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

__all__: tuple[str, ...] = ()

NOW = datetime(2026, 8, 10, 22, 0, tzinfo=UTC)
TENANT_ID = UUID("10000000-0000-0000-0000-000000000001")
PRINCIPAL_ID = UUID("20000000-0000-0000-0000-000000000001")
BINDING_ID = UUID("30000000-0000-0000-0000-000000000001")
HUMAN_SESSION_ID = UUID("40000000-0000-0000-0000-000000000001")
ALLOWANCE_ID = UUID("50000000-0000-0000-0000-000000000001")
WORK_SESSION_ID = UUID("60000000-0000-0000-0000-000000000001")
TICKET_ID = UUID("70000000-0000-0000-0000-000000000001")
RUNTIME_ATTEMPT_ID = UUID("80000000-0000-0000-0000-000000000001")
GRANT_ID = UUID("90000000-0000-0000-0000-000000000001")
NONCE = UUID("a0000000-0000-0000-0000-000000000001")


def _policy(**changes: int | str) -> ConsolePolicy:
    values: dict[str, Any] = {
        "grant_ttl_seconds": 300,
        "maximum_continuous_view_seconds": 1_800,
        "revocation_poll_seconds": 5,
        "decoded_chunk_bytes": 16 * 1024,
        "delivery_window_bytes": 1024 * 1024,
        "delivery_window_seconds": 60,
        "replay_window_bytes": 1024 * 1024,
        "replay_window_seconds": 60,
        "pending_bytes": 256 * 1024,
        "denial_limit": 3,
        "denial_window_seconds": 300,
        "suspension_seconds": 900,
        "policy_revision": "console-phase1-r1",
    }
    values.update(changes)
    return ConsolePolicy(**values)


def _session_ref(**changes: object) -> ConsoleSessionRef:
    values: dict[str, Any] = {
        "tenant_id": TENANT_ID,
        "project_key": "ctower",
        "seat_principal_id": PRINCIPAL_ID,
        "crew_name": "engineer-console-p1",
        "assignment_ticket_id": TICKET_ID,
        "assignment_kind": "implementation",
        "assignment_interval_sequence": 1,
        "recorded_work_session_id": WORK_SESSION_ID,
        "runtime_attempt_id": RUNTIME_ATTEMPT_ID,
        "runner_id": "mission-control",
        "runner_epoch": 7,
        "adapter_key": "tmux-v1",
        "opaque_backend_ref": "crew:engineer-console-p1",
        "backend_incarnation": "$9:1786400000",
    }
    values.update(changes)
    return ConsoleSessionRef(**values)


def _facts(**changes: object) -> ConsoleGrantFacts:
    ref = _session_ref()
    values: dict[str, Any] = {
        "actor": Actor(
            PRINCIPAL_ID,
            TENANT_ID,
            PrincipalKind.VIEWER,
            project_grants=frozenset({"ctower"}),
            human_binding_id=BINDING_ID,
            human_session_id=HUMAN_SESSION_ID,
        ),
        "allowance_id": ALLOWANCE_ID,
        "session_ref": ref,
        "allowlist_active": True,
        "assignment_current": True,
        "session_join_current": True,
        "adapter_registered": True,
        "global_kill_switch_enabled": False,
        "sensitivity_class": "restricted",
        "loop_kind": "standard",
        "observed_project_key": "ctower",
        "observed_runtime_attempt_id": RUNTIME_ATTEMPT_ID,
        "observed_runner_id": "mission-control",
        "observed_runner_epoch": 7,
        "observed_backend_ref": "crew:engineer-console-p1",
        "observed_backend_incarnation": "$9:1786400000",
        "session_revoked": False,
        "suspended_until": None,
        "human_session_current": True,
        "human_binding_current": True,
    }
    values.update(changes)
    return ConsoleGrantFacts(**values)


def _ids() -> ConsoleGrantIdentifiers:
    return ConsoleGrantIdentifiers(grant_id=GRANT_ID, nonce=NONCE)


def _grant(**changes: object) -> ConsoleViewGrant:
    outcome = decide_view_grant(_facts(), _ids(), policy=_policy(), now=NOW)
    assert isinstance(outcome, ConsoleViewGrant)
    return replace(outcome, **cast(dict[str, Any], changes))


def _code(facts: ConsoleGrantFacts, *, previous: ConsoleViewGrant | None = None) -> str:
    outcome = decide_view_grant(
        facts,
        _ids(),
        policy=_policy(),
        now=NOW,
        previous_grant=previous,
    )
    assert isinstance(outcome, RecordProblem)
    return outcome.code


def test_policy_has_no_implicit_defaults_and_enforces_every_phase1_ceiling() -> None:
    with pytest.raises(TypeError):
        ConsolePolicy()  # type: ignore[call-arg]
    for field, value in (
        ("grant_ttl_seconds", 301),
        ("maximum_continuous_view_seconds", 1_801),
        ("revocation_poll_seconds", 6),
        ("decoded_chunk_bytes", 16 * 1024 + 1),
        ("delivery_window_bytes", 1024 * 1024 + 1),
        ("delivery_window_seconds", 61),
        ("replay_window_bytes", 1024 * 1024 + 1),
        ("replay_window_seconds", 61),
        ("pending_bytes", 256 * 1024 + 1),
    ):
        with pytest.raises(ValueError, match=field):
            _policy(**{field: value})


def test_exact_visible_facts_mint_a_one_use_five_minute_bound_grant() -> None:
    grant = _grant()
    assert grant.actor_principal_id == PRINCIPAL_ID
    assert grant.human_binding_id == BINDING_ID
    assert grant.human_session_id == HUMAN_SESSION_ID
    assert grant.allowance_id == ALLOWANCE_ID
    assert grant.not_before == NOW
    assert grant.expires_at == NOW + timedelta(minutes=5)
    assert grant.maximum_uses == 1
    assert grant.policy_revision == "console-phase1-r1"
    assert grant.continuous_view_started_at == NOW


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"allowlist_active": False}, "console-session-not-allowed"),
        ({"assignment_current": False}, "console-assignment-stale"),
        ({"session_join_current": False}, "console-session-join-stale"),
        ({"adapter_registered": False}, "console-adapter-unregistered"),
        ({"global_kill_switch_enabled": True}, "console-globally-disabled"),
        ({"session_revoked": True}, "console-session-revoked"),
        ({"human_session_current": False}, "console-reauthentication-required"),
        ({"human_binding_current": False}, "console-reauthentication-required"),
        ({"sensitivity_class": "regulated"}, "console-sensitivity-refused"),
        ({"loop_kind": "bh-loop"}, "console-loop-kind-refused"),
    ],
)
def test_missing_or_forbidden_authority_facts_are_typed_refusals(
    change: dict[str, object], code: str
) -> None:
    assert _code(_facts(**change)) == code


def test_commander_and_foreign_project_are_absent_not_viewable() -> None:
    commander = replace(_facts().actor, kind=PrincipalKind.COMMANDER)
    assert _code(_facts(actor=commander)) == "console-role-refused"
    foreign = replace(_facts().actor, project_grants=frozenset({"other-project"}))
    assert _code(_facts(actor=foreign)) == "console-project-refused"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"observed_project_key": "other-project"}, "console-project-fence-mismatch"),
        (
            {"observed_runtime_attempt_id": UUID("80000000-0000-0000-0000-000000000002")},
            "console-runtime-attempt-fenced",
        ),
        ({"observed_runner_id": "replacement"}, "console-runner-fenced"),
        ({"observed_runner_epoch": 8}, "console-runner-epoch-fenced"),
        ({"observed_backend_ref": "crew:replacement"}, "console-backend-fenced"),
        ({"observed_backend_incarnation": "$10:1786400100"}, "console-incarnation-fenced"),
    ],
)
def test_live_project_runtime_runner_epoch_and_backend_fences_are_exact(
    change: dict[str, object], code: str
) -> None:
    assert _code(_facts(**change)) == code


def test_renewal_redecides_and_retains_the_original_continuous_view_start() -> None:
    previous = _grant(expires_at=NOW + timedelta(seconds=30))
    next_ids = ConsoleGrantIdentifiers(
        grant_id=UUID("90000000-0000-0000-0000-000000000002"),
        nonce=UUID("a0000000-0000-0000-0000-000000000002"),
    )
    renewed = decide_view_grant(
        _facts(), next_ids, policy=_policy(), now=NOW, previous_grant=previous
    )
    assert isinstance(renewed, ConsoleViewGrant)
    assert renewed.renewed_from_grant_id == previous.grant_id
    assert renewed.continuous_view_started_at == previous.continuous_view_started_at


def test_expired_grant_and_thirty_minute_chain_cannot_be_renewed() -> None:
    expired = _grant(expires_at=NOW)
    assert _code(_facts(), previous=expired) == "console-grant-expired"
    exhausted = _grant(continuous_view_started_at=NOW - timedelta(minutes=30))
    assert _code(_facts(), previous=exhausted) == "console-continuous-view-limit"


def test_three_denials_suspend_the_actor_for_fifteen_minutes() -> None:
    assert _code(_facts(suspended_until=NOW + timedelta(minutes=15))) == "console-actor-suspended"


def test_session_ref_is_strict_and_never_accepts_a_wildcard_or_unbounded_value() -> None:
    with pytest.raises(ValueError, match="project_key"):
        _session_ref(project_key="*")
    with pytest.raises(ValueError, match="runner_epoch"):
        _session_ref(runner_epoch=0)
    with pytest.raises(ValueError, match="opaque_backend_ref"):
        _session_ref(opaque_backend_ref="x" * 257)


@pytest.mark.parametrize(
    ("change", "message", "error"),
    [
        ({"tenant_id": "not-a-uuid"}, "UUID fields", TypeError),
        ({"crew_name": "*"}, "crew_name", ValueError),
        ({"assignment_kind": "*"}, "assignment_kind", ValueError),
        ({"assignment_interval_sequence": 0}, "interval_sequence", ValueError),
        ({"backend_incarnation": ""}, "backend_incarnation", ValueError),
    ],
)
def test_session_reference_rejects_each_unbounded_identity_shape(
    change: dict[str, object], message: str, error: type[Exception]
) -> None:
    with pytest.raises(error, match=message):
        _session_ref(**change)


def test_policy_and_stream_values_reject_malformed_metadata() -> None:
    with pytest.raises(ValueError, match="policy_revision"):
        _policy(policy_revision="*")
    with pytest.raises(ValueError, match="source_cursor"):
        ConsoleOutputBatch(payload=b"", source_cursor=-1)
    with pytest.raises(ValueError, match="present together"):
        ConsoleOutputBatch(payload=b"", source_cursor=0, gap=True)


def test_control_fact_reasons_must_be_present_and_bounded() -> None:
    with pytest.raises(ValueError, match="revocation reason"):
        ConsoleSessionRevocation(ALLOWANCE_ID, "")
    with pytest.raises(ValueError, match="kill-switch reason"):
        ConsoleGlobalSwitchCommand(enabled=True, reason="x" * 501)


def test_browser_binding_and_renewal_identity_are_exact() -> None:
    unbound = replace(_facts().actor, human_binding_id=None)
    assert _code(_facts(actor=unbound)) == "console-browser-session-required"
    previous = _grant(human_binding_id=UUID("30000000-0000-0000-0000-000000000002"))
    assert _code(_facts(), previous=previous) == "console-renewal-binding-mismatch"
