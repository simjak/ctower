"""The `codex` binding — the direct CLI as a real Adapter over the seam.

It spawns through a wrapper that names the config home and carries `--model` on the argv,
reads serving truth from the session rollout that home recorded, treats the launch argument as
the request and never as corroboration, and rides the pool ctower provides for it by wrapping
the fleet's existing ceremonies.

One rule here belongs to no other binding. **When the pool and the substrate disagree, this
reports the pool.** Exhaustion on this harness arrives as a non-retryable 401 on the first real
call while a separate liveness probe still reports the substrate alive — probe path and pool
path are different paths — and a sentinel that read the substrate said `codex=alive` while
every reviewer seat was dying. Two review turns were lost to that reading. So a pane that looks
healthy over a pool with nothing selectable is `dead_auth`, and the fact says which side it
came from.

The three ways to be un-credentialed are one lane state on purpose. A revoked lineage, a spent
window, and an unfunded balance are indistinguishable from the seat's side and identical in
consequence — money is a liveness condition — so all three end here as `dead_auth`, which is
the state `reap` refuses and preserves for resume. The pool keeps them apart on three axes,
where the difference decides which ceremony is right; the lane does not need to.

Everything harness-private stops in this object. What leaves is typed facts: a state, a
percentage, a model observation with its source, a refusal by name.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from ctower_runner.codex.liveness import classify_pane, context_used_pct
from ctower_runner.codex.pool import CodexPool
from ctower_runner.codex.substrate import (
    RolloutPort,
    SupervisorPort,
    WorkspacePort,
    WritebackPort,
)
from ctower_runner_sdk.attempt import AttemptPin, BriefBundle, SeatRef, WorkspaceContext
from ctower_runner_sdk.credentials import MeterObservation
from ctower_runner_sdk.facts import (
    ArtifactSet,
    DispatchReceipt,
    Handoff,
    LivenessFact,
    LivenessState,
    ModelObservation,
    TeardownReceipt,
    WritebackFact,
    WritebackReceipt,
)
from ctower_runner_sdk.guard import DispatchBoundary, ExecutionPlan
from ctower_runner_sdk.policy import (
    collect_refusal,
    ladder_disposition,
    serving_observation,
    teardown_receipt,
    writeback_refusal,
)
from ctower_runner_sdk.refusals import Refusal, substrate_unobservable
from ctower_runner_sdk.seam import CollectReason, CredentialRef, TeardownOrder
from ctower_runner_sdk.spec import HarnessSpec

__all__ = ["CODEX_POOL_PROBE", "CODEX_PROBE", "CODEX_WRAPPER", "CodexBinding"]

# The exact probe named in every fact this binding produces and in its unobservable refusal.
CODEX_PROBE = "codex-capture-pane"

# The other probe. It is named separately because the whole point of this binding is that the
# two can disagree, and a fact that cannot say which one answered is not evidence of either.
CODEX_POOL_PROBE = "codex-pool-state"

# The generated launcher. It is named in the plan the guard decides about, and it carries the
# config home and the model as separate arguments — the runtime reference and the request.
CODEX_WRAPPER = "codex-wrapper.sh"


class CodexBinding:
    """One codex config home, bound to one attempt at a time."""

    def __init__(
        self,
        spec: HarnessSpec,
        *,
        supervisor: SupervisorPort,
        rollout: RolloutPort,
        workspace: WorkspacePort,
        writeback_port: WritebackPort,
        pool: CodexPool,
        boundary: DispatchBoundary,
        clock: Callable[[], datetime],
    ) -> None:
        self._spec = spec
        self._supervisor = supervisor
        self._rollout = rollout
        self._workspace = workspace
        self._writeback = writeback_port
        self._pool = pool
        self._boundary = boundary
        self._clock = clock
        self._launched_plans: dict[tuple[UUID, int], ExecutionPlan] = {}

    @property
    def spec(self) -> HarnessSpec:
        return self._spec

    def spawn(
        self,
        attempt: AttemptPin,
        seat: SeatRef,
        brief: BriefBundle,
        context: WorkspaceContext,
    ) -> DispatchReceipt | Refusal:
        """Resolve a credential, clear the guard, deliver, and believe only an ACK.

        The credential is resolved first because on this harness an exhausted pool must
        dispatch nothing at all — including inside the window where a flapped account has not
        yet held its observation cycle, when the brief is staged and no pane is started. The
        guard clears before the launch because that is its whole point, and the receipt exists
        only once the composer is observed clear: this TUI collapses a long brief into a pasted
        block that one submit does not flush, and a brief sitting there reads as an idle lane.
        """

        preflight_refusal = _spawn_preflight_refusal(self._spec, attempt)
        if preflight_refusal is not None:
            return preflight_refusal
        lease = self._pool.acquire(model_ref=self._spec.probe.model_ref, tier=attempt.profile_ref)
        if isinstance(lease, Refusal):
            return lease
        identity = lease.entry.subscription_identity
        home = self._pool.home_for(identity)
        if isinstance(home, Refusal):
            return home
        pinned = attempt.with_lease(
            lease.lease_id, credential_identity=identity, credential_home=home
        )
        plan = self._plan(pinned, seat, context)
        decision = self._boundary.clear(plan, self._clock())
        if isinstance(decision, Refusal):
            return decision
        self._supervisor.launch(plan, pinned)
        self._launched_plans[(pinned.attempt_id, pinned.epoch)] = plan
        command_id = self._supervisor.deliver_input(pinned, brief.text)
        pane = self._supervisor.observe(pinned, 0)
        if command_id is None or pane is None or brief.text in pane:
            return _unacknowledged(brief, pane)
        self._pool.meter(
            lease, MeterObservation(event="spawn", model_ref=lease.model_ref)
        )
        return DispatchReceipt(
            attempt_id=str(pinned.attempt_id),
            composition_digest=pinned.composition_digest,
            acknowledged_at=self._clock(),
            ack_evidence=self._spec.ack_predicate.detail,
            guard_decision_id=decision.decision_id,
            durable_command_id=command_id,
        )

    def liveness(self, attempt: AttemptPin, after_cursor: int) -> LivenessFact:
        """Report a state, its percentage, and its served model — never a boolean."""

        pane = self._supervisor.observe(attempt, after_cursor)
        if pane is None:
            return LivenessFact(
                state="unknown",
                probe=substrate_unobservable(CODEX_PROBE).name,
                observed_at=self._clock(),
                evidence=f"epoch {attempt.epoch}",
            )
        plan = self._launched_plans.get((attempt.attempt_id, attempt.epoch))
        served, conflict = serving_observation(self._spec, self._readings(attempt, plan))
        substrate = classify_pane(pane, saturation_percent=self._spec.context_window_percent)
        state, probe, basis = self._reconcile(substrate)
        return LivenessFact(
            state=state,
            probe=probe,
            observed_at=self._clock(),
            served_model=served,
            context_used_pct=context_used_pct(pane),
            conflict=conflict,
            ladder=ladder_disposition(attempt, None if served is None else served.value),
            evidence=f"epoch {attempt.epoch} cursor {after_cursor}{basis}",
        )

    def collect(self, attempt: AttemptPin, reason: CollectReason) -> ArtifactSet | Refusal:
        """Derive the artifact set from committed refs and durable records only."""

        context = self._context(attempt)
        refusal = collect_refusal(self._workspace.dirty_paths(context))
        if refusal is not None:
            return refusal
        head_sha, pushed = self._workspace.head(context)
        return ArtifactSet(
            branch=context.branch,
            head_sha=head_sha,
            pushed=pushed,
            gate_output_paths=self._workspace.gate_outputs(context),
            status_artifact_path=self._workspace.status_artifact(context),
            handoff=_handoff(reason, context.branch, head_sha),
        )

    def writeback(
        self,
        attempt: AttemptPin,
        seat: SeatRef,
        seat_credential: CredentialRef,
        facts: tuple[WritebackFact, ...],
    ) -> WritebackReceipt | Refusal:
        """File every fact as the seat, and report the server's answer verbatim."""

        refusal = writeback_refusal(seat_credential, seat, facts)
        if refusal is not None:
            return refusal
        principal, answer = self._writeback.file(
            attempt,
            seat_credential.seat_key,
            tuple((fact.scope, fact.kind) for fact in facts),
        )
        return WritebackReceipt(
            actor_principal_id=principal,
            accepted=tuple(fact.kind for fact in facts if fact.scope != "transition"),
            transition_requests=tuple(fact.kind for fact in facts if fact.scope == "transition"),
            server_answer=answer,
        )

    def teardown(self, attempt: AttemptPin, order: TeardownOrder) -> TeardownReceipt | Refusal:
        """Preserve the work and the continuation, then stop."""

        collected = self.collect(attempt, "checkpoint")
        artifacts = None if isinstance(collected, Refusal) else collected
        head_sha, pushed = self._workspace.head(self._context(attempt))
        return teardown_receipt(
            order,
            artifacts=artifacts,
            state=self.liveness(attempt, 0).state,
            sole_work_unpushed=bool(head_sha) and not pushed,
            basis=f"{self._spec.key} config home for {attempt.profile_ref}",
            expires_at=self._clock(),
            nudge_offered=True,
        )

    def _reconcile(self, substrate: LivenessState) -> tuple[LivenessState, str, str]:
        """Report the pool's fact over the substrate's when the two disagree.

        A pane cannot see a credential. When the pool holds nothing selectable, the lane is
        dead however healthy the composer looks, and the fact names which probe answered so
        that the disagreement is readable rather than merely resolved.
        """

        if not self._pool.exhausted() or substrate == "dead_auth":
            return substrate, CODEX_PROBE, ""
        return (
            "dead_auth",
            CODEX_POOL_PROBE,
            f"; pool has no selectable entry while the substrate reads {substrate}",
        )

    def _plan(self, attempt: AttemptPin, seat: SeatRef, context: WorkspaceContext) -> ExecutionPlan:
        """The exact plan the guard decides about, with both references on it.

        `profile_ref` is the config home that carries the credential lineage and `--model` is
        the request; they are separate arguments because a launcher named after the model it
        was asked for is how a phantom harness category is born.
        """

        return ExecutionPlan(
            harness_ref=attempt.harness_ref,
            profile_ref=attempt.profile_ref,
            composition_digest=attempt.composition_digest,
            program=CODEX_WRAPPER,
            argv=(
                seat.seat_key,
                "--config-home",
                attempt.credential_home or "",
                "--model",
                self._spec.probe.model_ref,
            ),
            worktree_path=context.worktree_path,
            credential_identity=attempt.credential_identity,
            credential_home=attempt.credential_home,
        )

    def _context(self, attempt: AttemptPin) -> WorkspaceContext:
        return WorkspaceContext(
            worktree_path=f"/attempt/{attempt.attempt_id}",
            branch=f"attempt/{attempt.attempt_id}",
            base_ref="origin/main",
        )

    def _readings(
        self, attempt: AttemptPin, plan: ExecutionPlan | None = None
    ) -> tuple[ModelObservation, ...]:
        """Serving truth from the rollout, and the request from the launched argv.

        A request observation is only called `launch_argv` when the exact plan that cleared the
        guard is available. Before a dispatch exists, the durable intent remains useful as a
        request-only observation, but it is explicitly not launch provenance.
        """

        at = self._clock()
        readings: list[ModelObservation] = []
        if plan is not None:
            requested = _model_from_argv(plan.argv)
            if requested is not None:
                readings.append(
                    ModelObservation(
                        value=requested,
                        source="launch_argv",
                        proves="request",
                        observed_at=at,
                    )
                )
        elif attempt.intent_model:
            readings.append(
                ModelObservation(
                    value=attempt.intent_model,
                    source="spawn_intent",
                    proves="request",
                    observed_at=at,
                )
            )
        served = self._rollout.served_model(attempt)
        if served is not None:
            readings.append(
                ModelObservation(
                    value=served, source="session_transcript", proves="serving", observed_at=at
                )
            )
        return tuple(readings)


def _model_from_argv(argv: tuple[str, ...]) -> str | None:
    """Read one model request from the exact argv that crossed the guard."""

    positions = [index for index, value in enumerate(argv) if value == "--model"]
    if len(positions) != 1:
        return None
    position = positions[0] + 1
    if position >= len(argv) or not argv[position]:
        return None
    return argv[position]


def _intent_model_mismatch(intent: str, expected: str) -> Refusal:
    return Refusal(
        name="harness-dispatch-model-mismatch",
        observed=f"the attempt requests {intent!r}, but the pinned probe measures {expected!r}",
        meaning="the guarded launch and the durable spawn intent would describe different models",
        action="seat a new attempt against the revision-pinned model before dispatch",
        detail=(("intent_model", intent), ("probe_model", expected)),
    )


def _composition_pin_refusal(spec: HarnessSpec, attempt: AttemptPin) -> Refusal | None:
    """Reject an attempt that is not pinned to this binding before acquiring anything."""

    expected_digest = spec.composition_digest()
    mismatches: list[str] = []
    if attempt.harness_ref != spec.key:
        mismatches.append("harness_ref")
    if attempt.spec_revision != spec.revision:
        mismatches.append("spec_revision")
    if attempt.composition_digest != expected_digest:
        mismatches.append("composition_digest")
    if not mismatches:
        return None
    return Refusal(
        name="harness-dispatch-pin-mismatch",
        observed=f"the attempt has mismatched composition pins: {', '.join(mismatches)}",
        meaning=(
            "an attempt may dispatch only the harness, revision, and composition "
            "it was seated for"
        ),
        action="seat a new attempt against the registered spec; no lease or guard is consumed",
        detail=(
            ("mismatched_fields", ",".join(mismatches)),
            ("attempt_harness_ref", attempt.harness_ref),
            ("expected_harness_ref", spec.key),
            ("attempt_spec_revision", str(attempt.spec_revision)),
            ("expected_spec_revision", str(spec.revision)),
            ("attempt_composition_digest", attempt.composition_digest),
            ("expected_composition_digest", expected_digest),
        ),
    )


def _spawn_preflight_refusal(spec: HarnessSpec, attempt: AttemptPin) -> Refusal | None:
    """Run all zero-side-effect composition checks before pool acquisition."""

    pin_refusal = _composition_pin_refusal(spec, attempt)
    if pin_refusal is not None:
        return pin_refusal
    if attempt.intent_model != spec.probe.model_ref:
        return _intent_model_mismatch(attempt.intent_model, spec.probe.model_ref)
    return None


def _unacknowledged(brief: BriefBundle, pane: str | None) -> Refusal:
    return Refusal(
        name="harness-dispatch-unacknowledged",
        observed=(
            "the substrate was unobservable after delivery"
            if pane is None
            else "the composer still holds the brief after submit"
        ),
        meaning="a brief sitting in a composer reads as idle and is indistinguishable from done",
        action="clear the composer and re-deliver; no session-start fact was recorded",
        detail=(("brief_digest", brief.digest),),
    )


def _handoff(reason: CollectReason, branch: str, head_sha: str) -> Handoff:
    """Everything a successor needs, derived from the branch rather than from the seat.

    The seat that would have written the handoff is precisely the seat too saturated to write
    one, so this never depends on its cooperation. Two lanes were once reaped without ever
    writing a status file; their pushed branches carried the work.
    """

    return Handoff(
        done=f"committed through {head_sha} on {branch}",
        in_progress=f"collection reason {reason}",
        not_started="anything absent from the pushed diff",
        next_three_steps=(
            f"read the diff of {branch}",
            "re-run the designated suite at that head",
            "report the closing lines",
        ),
    )
