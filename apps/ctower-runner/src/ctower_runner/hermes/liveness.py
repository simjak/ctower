"""Hermes-private pane reading. Nothing in this module crosses the seam.

Three rules, each paid for by an incident. **Cap and saturation are classified before any
working marker** — a limit menu once matched the generic working pattern and a rate-limit-
dead lane counted as working for hours on the critical path. **The percentage is the
portable signal** — the saturation threshold is read from the binding's declared window
percentage, never hard-coded, because a 1.1M-window lane at 295K is healthy at 28% while
178K against a 131.1K window is not at 136%. And **the percentage is anchored to the closing
bracket of the footer's bar**, so a `95%` line in a scrolled coverage run cannot trip it.
"""

from __future__ import annotations

import re

from ctower_runner_sdk.facts import LivenessState
from ctower_runner_sdk.policy import classify_state

__all__ = [
    "CAP_MARKERS",
    "POOL_DEAD_AUTH_MARKERS",
    "classify_pane",
    "context_used_pct",
    "footer_model",
]

# Every phrasing the fleet has actually seen mean "this lane is capped". New phrasings
# belong here, in the classifier — the last extension of this list was lost because the
# repair was left uncommitted in a shared working tree.
CAP_MARKERS: tuple[str, ...] = (
    "wait for limit",
    "hit your usage limit",
    "upgrade your plan",
    "/usage-credits",
    "switch models",
    "out of credits",
    "add credits with",
)

# Pool exhaustion presents as a non-retryable 401 while a separate substrate probe still
# reports the pane alive. `liveness` reports the POOL fact when the two disagree.
POOL_DEAD_AUTH_MARKERS: tuple[str, ...] = (
    "credential pool: no available entries",
    "non-retryable",
)

# Hermes footers carry a timer glyph rather than Claude Code's "esc to interrupt" hint.
# Five working hermes lanes once read as idle against a Claude-shaped pattern and fired a
# false floor breach every cycle.
_TIMER_MARKERS: tuple[str, ...] = ("⏲", "⏱")

_REACHED_LIMIT = re.compile(r"reached your [A-Za-z0-9.\- ]*limit", re.IGNORECASE)
_BAR_PERCENT = re.compile(r"\]\s*(\d{1,3})%")
_FOOTER_MODEL = re.compile(r"⚕\s+([A-Za-z][\w.\-]*)\s+│")


def context_used_pct(pane: str) -> int | None:
    """Read the footer bar's own percentage, or `None` when no bar is on screen.

    Anchoring on the bar's closing bracket is the whole control. The bar's blocks are
    deliberately not quantified: a block-count pattern is a byte quantifier in this locale
    and silently fails against the real multibyte footer.
    """

    matches = _BAR_PERCENT.findall(pane)
    return int(matches[-1]) if matches else None


def footer_model(pane: str) -> str | None:
    """Read the model the footer names. This is the REQUEST, never serving truth."""

    match = _FOOTER_MODEL.search(pane)
    return match.group(1) if match is not None else None


def classify_pane(
    pane: str, *, saturation_percent: int, pane_changed: bool = False
) -> LivenessState:
    """Classify one captured pane against this binding's own declared window."""

    lowered = pane.lower()
    used = context_used_pct(pane)
    return classify_state(
        dead_auth=all(marker in lowered for marker in POOL_DEAD_AUTH_MARKERS),
        capped=_is_capped(lowered),
        saturated=used is not None and used >= saturation_percent,
        working_marker=any(marker in pane for marker in _TIMER_MARKERS),
        pane_changed=pane_changed,
    )


def _is_capped(lowered: str) -> bool:
    return any(marker in lowered for marker in CAP_MARKERS) or bool(_REACHED_LIMIT.search(lowered))
