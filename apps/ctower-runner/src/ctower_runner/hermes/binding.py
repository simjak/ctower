"""The `hermes` binding — the first real Adapter over the seam.

It spawns through a profile directory whose own config owns model and reasoning effort,
reads serving truth from the gateway log while the footer proves only the request, classifies
pool errors as dead auth, and observes the engine's pool rather than running a second one.

Everything harness-private stops here. What leaves this object is typed facts: a state, a
percentage, a model observation with its source, a refusal by name.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ctower_runner.hermes.liveness import classify_pane, context_used_pct, footer_model
from ctower_runner.hermes.pool import HermesPool
from ctower_runner.hermes.substrate import (
    GatewayLogPort,
    SupervisorPort,
    WorkspacePort,
    WritebackPort,
)
from ctower_runner_sdk.attempt import AttemptPin, BriefBundle, SeatRef, WorkspaceContext
from ctower_runner_sdk.credentials import Lease, MeterObservation
from ctower_runner_sdk.facts import (
    ArtifactSet,
    DispatchReceipt,
    Handoff,
    LivenessFact,
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
    terminate_after_receipt,
    writeback_refusal,
)
from ctower_runner_sdk.refusals import Refusal, substrate_unobservable
from ctower_runner_sdk.seam import CollectReason, CredentialRef, TeardownOrder
from ctower_runner_sdk.spec import HarnessSpec

__all__ = ["HERMES_PROBE", "HermesBinding"]

# The exact probe named in every fact this binding produces and in its unobservable refusal.
HERMES_PROBE = "hermes-capture-pane"

_HERMES_PROGRAM = "hermes"


class HermesBinding:
    """One hermes profile, bound to one attempt at a time."""

    def __init__(
        self,
        spec: HarnessSpec,
        *,
        supervisor: SupervisorPort,
        gateway: GatewayLogPort,
        workspace: WorkspacePort,
        writeback_port: WritebackPort,
        pool: HermesPool,
        boundary: DispatchBoundary,
        clock: Callable[[], datetime],
    ) -> None:
        self._spec = spec
        self._supervisor = supervisor
        self._gateway = gateway
        self._workspace = workspace
        self._writeback = writeback_port
        self._pool = pool
        self._boundary = boundary
        self._clock = clock

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

        Order matters at every step. The credential is resolved before the guard because an
        exhausted pool must dispatch nothing at all; the guard clears before the launch
        because that is its whole point; and the receipt is returned only after the declared
        ACK predicate is observed, because delivery is not acknowledgement — a brief has sat
        unread in a composer while the crew read as idle.
        """

        lease = self._pool.acquire(model_ref=self._spec.probe.model_ref, tier=attempt.profile_ref)
        if isinstance(lease, Refusal):
            return lease
        pinned = attempt.with_lease(lease.lease_id)
        decision = self._boundary.clear(self._plan(pinned, seat, context), self._clock())
        if isinstance(decision, Refusal):
            return decision
        self._supervisor.launch(self._plan(pinned, seat, context), pinned)
        command_id = self._supervisor.deliver_input(pinned, brief.text)
        pane = self._supervisor.observe(pinned, 0)
        if command_id is None or pane is None or brief.digest in pane:
            return _unacknowledged(brief, pane)
        self._pool.meter(lease, MeterObservation(event="spawn", model_ref=lease.model_ref))
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
                probe=substrate_unobservable(HERMES_PROBE).name,
                observed_at=self._clock(),
                evidence=f"epoch {attempt.epoch}",
            )
        served, conflict = serving_observation(self._spec, self._readings(attempt, pane))
        return LivenessFact(
            state=classify_pane(pane, saturation_percent=self._spec.context_window_percent),
            probe=HERMES_PROBE,
            observed_at=self._clock(),
            served_model=served,
            context_used_pct=context_used_pct(pane),
            conflict=conflict,
            ladder=ladder_disposition(attempt, None if served is None else served.value),
            evidence=f"epoch {attempt.epoch} cursor {after_cursor}",
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
        receipt = teardown_receipt(
            order,
            artifacts=artifacts,
            state=self.liveness(attempt, 0).state,
            sole_work_unpushed=bool(head_sha) and not pushed,
            basis=f"{self._spec.key} profile {attempt.profile_ref}",
            expires_at=self._clock(),
            nudge_offered=True,
        )
        return terminate_after_receipt(receipt, attempt, self._supervisor.terminate)

    def lease_for(self, attempt: AttemptPin) -> Lease | Refusal:
        """Resolve the credential this attempt would ride, without dispatching anything."""

        return self._pool.acquire(model_ref=self._spec.probe.model_ref, tier=attempt.profile_ref)

    def _plan(self, attempt: AttemptPin, seat: SeatRef, context: WorkspaceContext) -> ExecutionPlan:
        return ExecutionPlan(
            harness_ref=attempt.harness_ref,
            profile_ref=attempt.profile_ref,
            composition_digest=attempt.composition_digest,
            program=_HERMES_PROGRAM,
            argv=(seat.seat_key,),
            worktree_path=context.worktree_path,
        )

    def _context(self, attempt: AttemptPin) -> WorkspaceContext:
        return WorkspaceContext(
            worktree_path=f"/attempt/{attempt.attempt_id}",
            branch=f"attempt/{attempt.attempt_id}",
            base_ref="origin/main",
        )

    def _readings(self, attempt: AttemptPin, pane: str) -> tuple[ModelObservation, ...]:
        at = self._clock()
        readings = []
        served = self._gateway.served_model(attempt)
        if served is not None:
            readings.append(
                ModelObservation(
                    value=served, source="gateway_log", proves="serving", observed_at=at
                )
            )
        requested = footer_model(pane)
        if requested is not None:
            readings.append(
                ModelObservation(
                    value=requested, source="pane_footer", proves="request", observed_at=at
                )
            )
        return tuple(readings)


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

    Two saturated lanes were once reaped without ever writing a status file; their pushed
    branches carried the work, and the continuation lanes reconstructed from the diff. The
    seat that would have written the handoff is precisely the seat too saturated to write
    one, so this never depends on its cooperation.
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
