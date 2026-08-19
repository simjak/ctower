"""Rotation completion, probe validity, and the hold-one-cycle bar.

Two rules dominate this module. A rotation is **incomplete until its declared
cache-invalidation hook completes** — a stale proxy once translated `usage_limit_reached`
into `No available credentials` for an entire night, and cached state can burn a fresh
single-use refresh token. And a probe is only evidence when it is drawn from the pool's own
entries, sized to the declared workload, taken after invalidation, aimed at the model the
seats run, and classified on the response **body**: a 403 carrying a challenge page is a
reachability fact, and a status-code-only classifier that maps 401, 402, 403, and 429 to
one word is not a state source at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ctower_runner_sdk.credentials import EntryState, ProbeReading, ProbeResponse
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.spec import ProbeShape

__all__ = [
    "FlapWindow",
    "RotationEvent",
    "classify_probe",
    "record_rotation",
]

_CHALLENGE_MARKERS = ("cf_chl", "challenge-platform", "Just a moment", "Attention Required")
_UNKNOWN_BASIS = "the probe measured something other than the seats' rung"

# Named, because a status-code-only classifier is refused as a state source and these four
# must stay visibly distinct: revoked, unfunded, challenged, and capped are four answers.
_SERVED = 200
_UNAUTHORIZED = 401
_PAYMENT_REQUIRED = 402
_RATE_LIMITED = 429


@dataclass(frozen=True, slots=True)
class RotationEvent:
    """One completed rotation, attributed to the layer it actually happened on.

    `layer` is not decoration. Collapsing layers is how a cross-provider failover gets
    recorded as a rotation and a judgment lane quietly changes family: layer 1 is the same
    subscription serving again, layer 2 is a different vendor answering.
    """

    reason: str
    layer: Literal["pool", "fallback"]
    hook: str
    entry_identity: str | None
    completed_at: datetime
    context_rereads: int

    def to_mapping(self) -> dict[str, object]:
        return {
            "completed_at": self.completed_at.isoformat(),
            "context_rereads": self.context_rereads,
            "entry_identity": self.entry_identity,
            "hook": self.hook,
            "layer": self.layer,
            "reason": self.reason,
        }


def record_rotation(
    *,
    reason: str,
    layer: Literal["pool", "fallback"],
    hook: str,
    hook_completed: bool,
    entry: EntryState,
    completed_at: datetime,
) -> RotationEvent | Refusal:
    """Record a rotation, or refuse it by name. No entry state survives a refusal.

    A rotation costs one full-price context re-read, so it is metered rather than treated
    as free — which is what makes a strategy chosen for fairness visibly more expensive
    than one chosen to exhaust an entry first.
    """

    if entry.reach_state == "edge-challenged":
        return Refusal(
            name="rotation-refused-unreachable",
            observed=f"{_subject(entry)} is edge-challenged, not credential-faulted",
            meaning="every entry behind this egress is equally unreachable",
            action="escalate on the infra plane and fall back cross-provider; do not rotate",
            detail=(("reach", entry.reach_state),),
        )
    if not hook_completed:
        return Refusal(
            name="rotation-incomplete",
            observed=f"the {hook} invalidation hook has not completed",
            meaning="any state read now comes from a cache the rotation already invalidated",
            action=f"complete {hook}, then re-observe; the pre-hook observation is discarded",
            detail=(("hook", hook),),
        )
    return RotationEvent(
        reason=reason,
        layer=layer,
        hook=hook,
        entry_identity=entry.subscription_identity,
        completed_at=completed_at,
        context_rereads=1,
    )


def classify_probe(shape: ProbeShape, response: ProbeResponse) -> ProbeReading | Refusal:
    """Classify a probe response on its body, or say `unknown` by name."""

    if shape.classified_on == "status_line":
        return Refusal(
            name="pool-probe-classifier-refused",
            observed="the declared classifier reads the status line only",
            meaning="401, 402, 403, and 429 mean four different things and one word loses all four",
            action="classify on the response body, or report unknown",
            detail=(("classified_on", shape.classified_on),),
        )
    invalid = _invalidity(shape, response)
    if invalid is not None:
        return ProbeReading(auth="unknown", quota="unknown", reach="unknown", basis=invalid)
    return _reading(response)


def _invalidity(shape: ProbeShape, response: ProbeResponse) -> str | None:
    if not response.drawn_from_pool:
        return "the probe was not drawn from this pool's own entries"
    if not response.after_invalidation:
        return "the probe was taken before the cache-invalidation hook completed"
    if shape.workload_shape != "representative":
        return f"a {shape.workload_shape} probe cannot report a real window"
    if not shape.measures(response.model_ref):
        return _UNKNOWN_BASIS
    return None


def _reading(response: ProbeResponse) -> ProbeReading:
    body = response.body
    if any(marker in body for marker in _CHALLENGE_MARKERS):
        return ProbeReading(
            auth="unknown",
            quota="unknown",
            reach="edge-challenged",
            basis="the response body is a challenge page, so nothing about the credential is known",
        )
    if response.status_code == _SERVED and not body.strip():
        return ProbeReading(
            auth="unknown",
            quota="unknown",
            reach="unknown",
            basis="a 200 with empty content is a hang, never capacity",
        )
    return _status_reading(response.status_code, body)


def _status_reading(status_code: int, body: str) -> ProbeReading:
    if status_code == _SERVED:
        return ProbeReading(auth="healthy", quota="available", reach="ok", basis="served content")
    if status_code == _UNAUTHORIZED:
        return ProbeReading(
            auth="lineage-dead", quota="unknown", reach="ok", basis="refused the credential"
        )
    if status_code == _PAYMENT_REQUIRED:
        return ProbeReading(
            auth="healthy", quota="unfunded", reach="ok", basis="the prepaid balance is spent"
        )
    if status_code == _RATE_LIMITED:
        return ProbeReading(
            auth="healthy", quota="capped", reach="ok", basis="the window is spent, not the grant"
        )
    return ProbeReading(
        auth="unknown", quota="unknown", reach="unknown", basis=f"unclassified body for {body[:32]}"
    )


@dataclass(frozen=True, slots=True)
class FlapWindow:
    """A window returning to `available` holds one full observation cycle first.

    A substrate flipped alive twice in one morning and the second flip lasted two sweeps.
    Because the bar was enforced, briefs were staged and zero lanes were half-started.
    """

    consecutive_available: int
    required_cycles: int = 1

    def observe(self, *, available: bool) -> FlapWindow:
        return FlapWindow(
            consecutive_available=self.consecutive_available + 1 if available else 0,
            required_cycles=self.required_cycles,
        )

    def is_selectable(self) -> bool:
        return self.consecutive_available > self.required_cycles


def _subject(entry: EntryState) -> str:
    return entry.subscription_identity or f"{entry.provider_key} entry"
