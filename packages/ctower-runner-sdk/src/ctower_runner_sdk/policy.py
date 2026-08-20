"""Seam policy every binding obeys identically, separated from harness-private reading.

A binding's job is to observe its own substrate. What that observation *means* — whether a
lane counts as working, whether a fact may be written, whether a lane may be reaped — is one
answer for every harness, so it lives here and is proven once by the shared conformance
suite. Anything below that reads a footer, a transcript, or a gateway log belongs inside a
binding and never crosses the seam.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from ctower_runner_sdk.attempt import AttemptPin, SeatRef
from ctower_runner_sdk.facts import (
    ArtifactSet,
    Handoff,
    LadderDisposition,
    LivenessState,
    ModelObservation,
    TeardownReceipt,
    WritebackFact,
)
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.seam import CredentialRef, TeardownOrder
from ctower_runner_sdk.spec import HarnessSpec

__all__ = [
    "TEARDOWN_TRIGGERS",
    "WRITEBACK_SCOPES",
    "LadderDisposition",
    "classify_state",
    "collect_refusal",
    "dispatch_pin_refusal",
    "input_refusal",
    "ladder_disposition",
    "serving_observation",
    "teardown_receipt",
    "terminate_after_receipt",
    "undeclared_source_refusal",
    "writeback_refusal",
]

# Exhaustive. A seat's authority ceiling is these three scopes and nothing wider.
WRITEBACK_SCOPES: frozenset[str] = frozenset({"capture", "transition", "evidence"})

# A lane in either of these states cannot be trusted to hold the evidence it cites, so the
# checkpoint order is issued before it stops rather than after someone notices.
TEARDOWN_TRIGGERS: frozenset[str] = frozenset({"saturated", "capped"})

_SEAT_SCOPE = "project-seat"


def classify_state(
    *, capped: bool, saturated: bool, dead_auth: bool, working_marker: bool, pane_changed: bool
) -> LivenessState:
    """Classify one lane, cap and saturation first.

    Precedence is the whole point. The limit menu once matched the generic working pattern
    and a rate-limit-dead lane counted as working for hours on the critical path; a lane at
    136% of its window had a live timer and was emitting tokens. Both are failures that
    render as the healthy state, so both are decided before any working marker is read.
    """

    if dead_auth:
        return "dead_auth"
    if capped:
        return "capped"
    if saturated:
        return "saturated"
    if working_marker or pane_changed:
        return "working"
    return "idle"


def dispatch_pin_refusal(spec: HarnessSpec, attempt: AttemptPin) -> Refusal | None:
    """Refuse a dispatch whose harness, revision, or composition is not this spec's.

    This is the seam's shared pre-lease, pre-guard boundary. A binding-specific launcher may
    have a different executable or serving source, but none may acquire a credential or ask a
    guard about an attempt that was seated against another composition. The revision check is
    deliberately independent of the digest: a stale revision must not become current merely
    because a caller forged a matching composition string.
    """

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
            "an attempt may dispatch only the harness, revision, and composition it was seated for"
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


def serving_observation(
    spec: HarnessSpec, readings: Sequence[ModelObservation]
) -> tuple[ModelObservation | None, str | None]:
    """Return this binding's serving truth and any conflict, never collapsing the two.

    A source that proves only the *request* is recorded as a conflict. A footer once read
    `gpt-5.6-terra` while the gateway served something else entirely: the record of what was
    requested is not evidence of what is serving.
    """

    declared = spec.serving_source()
    truth = next(
        (
            reading
            for reading in readings
            if declared is not None
            and reading.source == declared.source
            and reading.is_serving_truth()
        ),
        None,
    )
    requested = next((reading for reading in readings if reading.proves == "request"), None)
    if requested is None or truth is None or requested.value == truth.value:
        return truth, None
    return truth, f"{requested.source} shows the request {requested.value!r}, not serving truth"


def ladder_disposition(attempt: AttemptPin, served_model: str | None) -> LadderDisposition:
    """Say whether serving matches the ladder, substitutes, or remains unknown.

    A known fallback rung of the **durable spawn intent** is the never-stall ladder, not a
    substitution — anchoring "expected" to the latest ledger row instead reports the
    recovery as the violation. The exception is a judgment lane, where tolerance is zero:
    switching family under the same author assignment does not create reviewer
    independence, so any deviation there is a substitution however well the ladder worked.
    Missing serving truth is explicitly unknown, never evidence that the requested model served.
    """

    if served_model is None:
        return "unknown"
    if served_model == attempt.intent_model:
        return "as_intended"
    if attempt.judgment_lane:
        return "substitution"
    return "ladder" if served_model in attempt.declared_rungs else "substitution"


def undeclared_source_refusal(
    spec: HarnessSpec, readings: Sequence[ModelObservation]
) -> Refusal | None:
    """Refuse a serving claim from a source this binding never declared.

    A model's claim about itself is the specific case this exists for: a seat self-report
    satisfies neither serving truth nor a request record, and accepting one would let the
    thing being observed decide what the observation says.
    """

    declared = {source.source for source in spec.liveness_sources}
    undeclared = sorted({reading.source for reading in readings if reading.source not in declared})
    if not undeclared:
        return None
    return Refusal(
        name="harness-served-model-self-reported",
        observed=f"served-model readings from undeclared sources: {', '.join(undeclared)}",
        meaning="an undeclared source is a claim, and a seat's claim about itself is not evidence",
        action="declare the source in the HarnessSpec, or report the model as unknown",
        detail=tuple(("undeclared_source", source) for source in undeclared),
    )


def input_refusal(spec: HarnessSpec, state: LivenessState) -> Refusal | None:
    """Refuse input into a live turn unless this binding declares the interrupt capability.

    A reviewer an hour into a real finding was steered mid-turn because a liveness pattern
    from another harness read the lane as idle; the finding would have died with the turn.
    """

    if state != "working" or spec.declares("INTERRUPT_AND_RESUME"):
        return None
    return Refusal(
        name="harness-capability-unsupported",
        observed=f"{spec.key!r} declares no INTERRUPT_AND_RESUME and the lane is working",
        meaning="delivering into a live turn would destroy whatever that turn is holding",
        action="wait for the turn, or bind a harness that declares the interrupt capability",
        detail=(("capability", "INTERRUPT_AND_RESUME"),),
    )


def collect_refusal(dirty_paths: Sequence[str]) -> Refusal | None:
    """Refuse a collection from an uncommitted tree, naming exactly what is dirty.

    A watchdog repair once sat in a shared repository's working tree and was overwritten by
    a later commit while an audit reported it fixed for hours. A fix that is not committed
    is not a fix, and an audit that reads the working tree cannot tell the difference.
    """

    if not dirty_paths:
        return None
    return Refusal(
        name="checkpoint-uncollectable",
        observed=f"{len(dirty_paths)} uncommitted paths in the attempt's worktree",
        meaning="an uncommitted change is not derivable from any ref a successor can read",
        action="commit and push, then collect; a smaller artifact set is not the answer",
        detail=tuple(("dirty_path", path) for path in dirty_paths),
    )


def writeback_refusal(
    credential: CredentialRef, seat: SeatRef, facts: Sequence[WritebackFact]
) -> Refusal | None:
    """Refuse a writeback whose authority, seat, project, or scope is wrong. Zero mutation.

    One credential per seat is what makes `project-scope-denied` possible at all: with one
    identity behind many seats the server has nothing to check a claim against, which is how
    fifteen tickets were once filed under a wrong project key unrefusably.

    The seat and the credential arrive as two independent inputs, which is what makes that
    refusal reachable — and what makes this equality the only thing standing between them.
    A credential belonging to another seat in the right project satisfies every other check
    here and files one seat's work under another seat's identity: seats file as themselves.
    """

    if credential.scope != _SEAT_SCOPE:
        return Refusal(
            name="harness-credential-forbidden",
            observed=f"the adapter was presented a {credential.scope!r} credential",
            meaning="an adapter holding an operator or commander credential is a design failure",
            action="present the seat's own project-seat credential",
            detail=(("presented_scope", credential.scope),),
        )
    if credential.seat_key != seat.seat_key:
        return Refusal(
            name="harness-credential-seat-mismatch",
            observed="the credential presented belongs to a seat other than this attempt's",
            meaning="a fact under another seat's identity credits work to a seat that did none",
            action="present this seat's own project-seat credential",
        )
    if credential.project_key != seat.project_key:
        return Refusal(
            name="project-scope-denied",
            observed="the credential's project does not match the seat's project",
            meaning="this seat may not write into that project",
            action="use the seat's own project, or ask the operator for a scoped credential",
        )
    outside = sorted({fact.scope for fact in facts} - WRITEBACK_SCOPES)
    if not outside:
        return None
    return Refusal(
        name="harness-writeback-scope-refused",
        observed=f"facts outside the seat's authority ceiling: {', '.join(outside)}",
        meaning="capture, transition, and evidence are exhaustive, not a starting point",
        action="drop the out-of-scope facts; a stage change is emitted only as a request",
        detail=tuple(("scope", scope) for scope in outside),
    )


def teardown_receipt(
    order: TeardownOrder,
    *,
    artifacts: ArtifactSet | None,
    state: LivenessState,
    sole_work_unpushed: bool,
    basis: str | None = None,
    expires_at: datetime | None = None,
    nudge_offered: bool = False,
) -> TeardownReceipt | Refusal:
    """Stop a lane in a way that preserves both the work and the continuation."""

    if order == "park":
        return _park(basis, expires_at)
    if order == "reap":
        return _reap(state, artifacts, sole_work_unpushed=sole_work_unpushed, nudged=nudge_offered)
    return _checkpoint(artifacts)


def terminate_after_receipt(
    receipt: TeardownReceipt | Refusal,
    attempt: AttemptPin,
    terminate: Callable[[AttemptPin], bool | Refusal],
) -> TeardownReceipt | Refusal:
    """Stop exactly once after a successful receipt, and type every stop failure."""

    if isinstance(receipt, Refusal):
        return receipt
    try:
        stopped = terminate(attempt)
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit)):
            raise
        return _termination_refusal(attempt)
    if isinstance(stopped, Refusal):
        return stopped
    if stopped is not True:
        return _termination_refusal(attempt)
    return receipt


def _termination_refusal(attempt: AttemptPin) -> Refusal:
    return Refusal(
        name="harness-termination-failed",
        observed="the supervisor did not confirm termination",
        meaning="a receipt without a stopped lane permits concurrent work under stale ownership",
        action="repair the supervisor termination path; do not report the lane as stopped",
        detail=(("attempt_id", str(attempt.attempt_id)),),
    )


def _checkpoint(artifacts: ArtifactSet | None) -> TeardownReceipt | Refusal:
    if artifacts is None or not artifacts.is_complete():
        return Refusal(
            name="checkpoint-uncollectable",
            observed="the checkpoint order found no pushed branch to preserve",
            meaning="the branch is the handoff, and there is no branch",
            action="commit and push before stopping the lane",
        )
    if artifacts.handoff is None:
        return Refusal(
            name="checkpoint-uncollectable",
            observed="the checkpoint carries no handoff",
            meaning="a successor cannot reconstruct what is done, running, and next",
            action="write done / in progress / not started / next three steps",
            detail=tuple(("required_section", name) for name in _handoff_sections()),
        )
    return TeardownReceipt(order="checkpoint", artifacts=artifacts)


def _park(basis: str | None, expires_at: datetime | None) -> TeardownReceipt | Refusal:
    if not basis:
        return Refusal(
            name="park-basis-broken",
            observed="the park order carries no stated basis",
            meaning="a park with no basis cannot be re-proved and never expires on its own",
            action="state the basis the park rests on",
        )
    if expires_at is None:
        return Refusal(
            name="park-expired",
            observed="the park order carries no explicit expiry",
            meaning="a forgotten park would silence the floor indefinitely",
            action="set an explicit expiry; cheap to arm, self-expiring, broken by good news",
        )
    return TeardownReceipt(order="park", artifacts=None, basis=basis, expires_at=expires_at)


def _reap(
    state: LivenessState,
    artifacts: ArtifactSet | None,
    *,
    sole_work_unpushed: bool,
    nudged: bool,
) -> TeardownReceipt | Refusal:
    if sole_work_unpushed:
        return Refusal(
            name="teardown-would-destroy-sole-work",
            observed="this lane holds the only copy of unpushed work",
            meaning="reaping it destroys the work and the continuation at once",
            action="checkpoint first, then reap",
        )
    if state == "dead_auth":
        return Refusal(
            name="teardown-refused-dead-auth",
            observed="this lane is dead on auth, not dead on work",
            meaning="its pane is preserved for resume once the credential is refilled",
            action="offer the resume nudge; replace only a lane that cannot be resumed",
        )
    if not nudged:
        return Refusal(
            name="teardown-refused-dead-auth",
            observed="no resume nudge was offered before this replacement",
            meaning="a lane that ended a turn without delivering is offered one input first",
            action="offer the nudge, then reap only if it cannot be resumed",
        )
    return TeardownReceipt(order="reap", artifacts=artifacts, nudge_offered=True)


def _handoff_sections() -> tuple[str, ...]:
    return Handoff(
        done="", in_progress="", not_started="", next_three_steps=("", "", "")
    ).sections()
