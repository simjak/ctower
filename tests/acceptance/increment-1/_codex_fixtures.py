"""Shared deterministic fixtures for the Codex acceptance boundary tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ctower_runner.codex.binding import CodexBinding
from ctower_runner.codex.ceremonies import CeremonyInvocation, CeremonyOutcome
from ctower_runner.codex.corpus import CODEX_CORPUS
from ctower_runner.codex.pool import CodexAccount, CodexPool, ConfigHomeStore
from ctower_runner.codex.spec import CODEX_KEY, digest_of, harness_spec_document
from ctower_runner.hermes.spec import harness_spec_document as hermes_spec_document
from ctower_runner_sdk.attempt import AttemptPin, BriefBundle, SeatRef, WorkspaceContext
from ctower_runner_sdk.facts import DispatchReceipt
from ctower_runner_sdk.guard import DispatchBoundary, ExecutionPlan, GuardDecision
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.registry import HarnessRegistry
from ctower_runner_sdk.spec import HarnessSpec, parse_harness_spec

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
_USED_AT_71_LEFT = 29
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


def registration_registry(*specs: HarnessSpec) -> HarnessRegistry:
    """Return the registry with its closed first-party admission source."""

    return HarnessRegistry()


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
        self.launched_plans: list[ExecutionPlan] = []
        self.launched_attempts: list[AttemptPin] = []

    def launch(self, plan: ExecutionPlan, attempt: AttemptPin) -> str:
        self.launched.append(plan.normalized_digest())
        self.launched_plans.append(plan)
        self.launched_attempts.append(attempt)
        return f"pane-{attempt.attempt_id}"

    def observe(self, attempt: AttemptPin, after_cursor: int) -> str | None:
        del attempt, after_cursor
        return self._pane

    def deliver_input(self, attempt: AttemptPin, text: str) -> str | None:
        return f"cmd-{attempt.attempt_id}-{len(text)}"

    def terminate(self, attempt: AttemptPin) -> bool:
        del attempt
        return True


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
    served_missing: bool = False,
    pool: CodexPool | None = None,
    supervisor: _Supervisor | None = None,
    guard: _Guard | None = None,
) -> CodexBinding:
    return CodexBinding(
        _spec(),
        supervisor=supervisor or _Supervisor(pane),
        rollout=_Rollout(None if served_missing else served or _spec().probe.model_ref),
        workspace=_Workspace(),
        writeback_port=_Writeback(),
        pool=pool or _pool(),
        boundary=DispatchBoundary(guard or _Guard(), _Receipts(), _GUARD_VERSION),
        clock=lambda: _NOW,
    )


def _spawn(binding: CodexBinding, text: str = "build the row") -> DispatchReceipt | Refusal:
    return _spawn_attempt(binding, _attempt(), text=text)


def _spawn_attempt(
    binding: CodexBinding, attempt: AttemptPin, *, text: str = "build the row"
) -> DispatchReceipt | Refusal:
    return binding.spawn(
        attempt,
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
