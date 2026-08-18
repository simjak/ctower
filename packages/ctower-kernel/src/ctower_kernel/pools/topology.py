"""The authored desired topology and the subscriptions' own credit weights.

This is ctower's registry, not a description of what happens to exist. It declares what
*should* exist per harness profile, so reconciliation against an observation yields typed
drift findings in both directions rather than silence: a desired-but-absent subscription is
`missing` and routes to its declared enactment path, and a present-but-undesired one is
`unregistered` and stays non-selectable pending an operator keep-or-evict.

Five subscriptions per hermes profile yield three provider rungs, and the arithmetic is the
layer split made visible: the three codex accounts are not three rungs, they are one rung
with three entries rotated *within* the provider, while the cross-provider chain has three
stops. Anything that models subscriptions and rungs as one list gets 5 = 3 and knows
something is wrong.

Enactment splits by subscription kind because that is what makes a finding actionable: a
missing API key is automation's problem, a missing OAuth grant is an item on the operator's
ceremony list. Ctower can *request* a mint and never perform one — there is deliberately no
path here that copies credential material, because a copied auth file replays a single-use
refresh token and the provider revokes every grant derived from that login at once.

Weights are provider-native credits per million tokens, carried as integer millicredits so
the wire contract stays exact-integer. They are what makes "which model on which account
drained this plan" answerable; tokens are not the billing unit and do not answer it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "TOPOLOGY_REVISION",
    "DesiredSubscription",
    "ModelWeight",
    "desired_profile",
    "model_weights",
]

TOPOLOGY_REVISION = 1

_OPERATOR_CEREMONY = "operator-ceremony"
_REFERENCE_WIRED = "secret-reference"


@dataclass(frozen=True, slots=True)
class DesiredSubscription:
    """One subscription a profile is supposed to hold, and how it gets wired."""

    provider_key: str
    subscription_identity: str | None
    enactment: str


@dataclass(frozen=True, slots=True)
class ModelWeight:
    """One model's provider-native cost, per direction, in millicredits per Mtok."""

    subscription_key: str
    model_ref: str
    input_millicredits_per_mtok: int
    cached_input_millicredits_per_mtok: int
    output_millicredits_per_mtok: int


# Each hermes persona profile: three codex accounts (its OWN device-flow mint of each —
# profiles x accounts interactive sign-ins, never one mint copied into many homes) plus a
# z.ai key and an Alibaba key. Five subscriptions, three rungs.
_HERMES_DESIRED: tuple[DesiredSubscription, ...] = (
    DesiredSubscription("openai-codex", "simonas@jakit.lt", _OPERATOR_CEREMONY),
    DesiredSubscription("openai-codex", "simonas@jakitlabs.com", _OPERATOR_CEREMONY),
    DesiredSubscription("openai-codex", "simasjak@gmail.com", _OPERATOR_CEREMONY),
    DesiredSubscription("zai", None, _REFERENCE_WIRED),
    DesiredSubscription("alibaba", None, _REFERENCE_WIRED),
)

# Claude Code holds one account per install and ships neither pooling nor an in-session
# ladder, so the three subscriptions are three per-seat credential homes; failover between
# them is a new attempt, never a mid-session swap.
_CLAUDE_CODE_DESIRED: tuple[DesiredSubscription, ...] = (
    DesiredSubscription("claude-code", "simonas@jakit.lt", _OPERATOR_CEREMONY),
    DesiredSubscription("claude-code", "simonas@jakitlabs.com", _OPERATOR_CEREMONY),
    DesiredSubscription("claude-code", "simasjak@gmail.com", _OPERATOR_CEREMONY),
)

_DESIRED: dict[str, tuple[DesiredSubscription, ...]] = {
    "hermes": _HERMES_DESIRED,
    "claude-code": _CLAUDE_CODE_DESIRED,
}

# Operator dashboards, 2026-08-17. Sol output is 25x luna output, which is the ratio the
# report exists to make visible before a lane is scheduled onto the expensive rung.
_WEIGHTS: tuple[ModelWeight, ...] = (
    ModelWeight("openai-codex", "gpt-5.6-sol", 125_000, 12_500, 750_000),
    ModelWeight("openai-codex", "gpt-5.6-terra", 50_000, 5_000, 300_000),
    ModelWeight("openai-codex", "gpt-5.6-luna", 5_000, 500, 30_000),
)


def desired_profile(harness_key: str) -> tuple[DesiredSubscription, ...]:
    """Return the authored desired subscription set for one harness."""

    return _DESIRED.get(harness_key, ())


def model_weights() -> tuple[ModelWeight, ...]:
    """Return every priced model in the registry, in authored order."""

    return _WEIGHTS
