"""Refusal names for the harness-adapter seam, minted once and checked against SPEC.

A refusal is an exact name with zero mutation, never an exception string and never a
silently smaller result. Where SPEC already owns a name the seam reuses it verbatim;
refusal-name overlap was a P1 finding on an adjacent spec, so `SEAM_MINTED` below is the
complete list of names this seam introduces and nothing else may be raised across it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "SEAM_MINTED",
    "SPEC_OWNED",
    "Refusal",
    "substrate_unobservable",
]

# Names SPEC already owns. The seam reuses the spelling rather than minting a synonym.
SPEC_OWNED: frozenset[str] = frozenset(
    {
        "checkpoint-uncollectable",
        "credential-pool-exhausted",
        "harness-dispatch-unacknowledged",
        "project-scope-denied",
        "role-resolution-unavailable",
        "rotation-incomplete",
        "workflow-stage-role-not-permitted",
    }
)

# Names this seam introduces. Every one is `<subject>-<condition>`, matching the house
# vocabulary, and none collides with a name already in SPEC or the kernel. The set grows only
# when a binding introduces a condition no existing name states. The direct-CLI binding adds
# runtime-routing, unknown-credential-argument, and stale-generation refusals; the provided
# Claude pool adds the concurrent-holder refusal. Each carries a different remedy from
# `rotation-incomplete`, and collapsing any of them into it would send the reader to the wrong
# repair. Adding a synonym for a condition already named here is the failure this list exists
# to prevent.
SEAM_MINTED: frozenset[str] = frozenset(
    {
        "credential-verb-unknown-flag",
        "harness-capability-unsupported",
        "harness-credential-forbidden",
        "harness-credential-seat-mismatch",
        "harness-dispatch-blocked",
        "harness-dispatch-needs-operator",
        "harness-guard-decision-invalid",
        "harness-layer-conflict",
        "harness-receipt-undurable",
        "harness-runtime-not-a-harness",
        "harness-seam-unpublished",
        "harness-served-model-self-reported",
        "harness-spec-digest-mismatch",
        "harness-spec-incompatible",
        "harness-spec-revoked",
        "harness-spec-unknown",
        "harness-survey-incomplete",
        "harness-writeback-scope-refused",
        "park-basis-broken",
        "park-expired",
        "pool-probe-classifier-refused",
        "pool-state-stale",
        "rotation-refused-concurrent-holder",
        "rotation-refused-stale-generation",
        "rotation-refused-unreachable",
        "teardown-refused-dead-auth",
        "teardown-would-destroy-sole-work",
        "weight-table-unavailable",
    }
)

_UNOBSERVABLE = "substrate-unobservable"


@dataclass(frozen=True, slots=True)
class Refusal:
    """One refusal: a name, why it happened, and the facts a reader needs to act.

    `observed`, `meaning`, and `action` are separate because a diagnosis that states only
    what broke sends the reader to the wrong ceremony. `detail` carries typed subject rows
    (per-entry states, dirty paths, the earliest known reset) and never free-form prose
    that a caller would have to parse back.
    """

    name: str
    observed: str
    meaning: str
    action: str
    detail: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.name.startswith(f"{_UNOBSERVABLE}:"):
            return
        if self.name not in SPEC_OWNED and self.name not in SEAM_MINTED:
            raise ValueError(f"refusal name is outside the seam vocabulary: {self.name}")

    def to_mapping(self) -> dict[str, object]:
        return {
            "action": self.action,
            "detail": [{"subject": subject, "state": state} for subject, state in self.detail],
            "meaning": self.meaning,
            "name": self.name,
            "observed": self.observed,
        }


def substrate_unobservable(probe: str) -> Refusal:
    """Name the probe that could not read the substrate rather than guessing alive."""

    return Refusal(
        name=f"{_UNOBSERVABLE}:{probe}",
        observed=f"the {probe} probe returned nothing readable",
        meaning="the substrate's state is unknown, which is not the same as alive",
        action="re-probe, or treat this lane as STATE_UNKNOWN until a probe succeeds",
    )
