"""Claude-Code-private pane reading. Nothing in this module crosses the seam.

What a reading *means* is `classify_state`'s answer, identical for every binding. What this
module owns is the harness-private half — which bytes on this substrate say cap, dead auth,
saturation, or work — and four rules, each paid for by a recorded incident on this fleet.

**Cap and dead auth are decided before any working marker.** The Claude limit menu's
`Enter to confirm · Esc to cancel` line matches the generic `· esc` working pattern, which is
how a rate-limit-dead lane counted as working for hours on the critical path.

**The percentage is the portable signal, and on this harness it is inverted.** Claude Code
prints `Context left until auto-compact: N%` — percent LEFT. Reading it as used turns a lane
with 8% remaining into a lane reported as 8% consumed, which is the healthy answer for the
failing case. The absolute `23.2k tokens` counter beside it is deliberately not a saturation
source: a large-window lane at the same count is healthy, so the count's units prove nothing.

**A cap phrasing belongs in this list, not in a note.** The list was extended once and lost,
because the repair was left in a shared repository's working tree and a later commit
overwrote it.

**The boot banner is not a cap.** `N usage limit resets available` is a startup notice about
windows that have already reset, and it carries the substring `usage limit`.
"""

from __future__ import annotations

import hashlib
import re

from ctower_runner_sdk.facts import LivenessState
from ctower_runner_sdk.policy import classify_state

__all__ = [
    "CAP_MARKERS",
    "DEAD_AUTH_MARKERS",
    "WORKING_MARKERS",
    "classify_pane",
    "context_used_pct",
    "pane_digest",
]

# Every phrasing this fleet has actually seen mean "this lane is capped".
CAP_MARKERS: tuple[str, ...] = (
    "wait for limit",
    "hit your usage limit",
    "upgrade your plan",
    "/usage-credits",
    "switch models",
    "out of credits",
    "add credits with",
)

# A Claude Code pane that lost its grant says so in the composer rather than by failing.
DEAD_AUTH_MARKERS: tuple[str, ...] = ("not logged in", "run /login", "invalid api key")

# Narrow panes truncate the status line to `· esc…`, which is why the bare marker is matched
# beside the full hint. These are Claude-shaped and not hermes-shaped: a timer-glyph pattern
# once read five working hermes lanes as idle, and the mirror-image mistake is available here.
WORKING_MARKERS: tuple[str, ...] = ("esc to interrupt", "· esc", "• esc")

# The startup notice counts windows that have RESET. Stripped before the cap match so the
# substring "usage limit" inside it can never be read as a cap.
_BOOT_BANNER = re.compile(r"\d+\s+usage limit resets available", re.IGNORECASE)

_REACHED_LIMIT = re.compile(r"reached your [A-Za-z0-9.\- ]*limit", re.IGNORECASE)

# "N shells still running" with no esc-marker is working, not idle: the turn ended but the
# gate run it started continues, and the seat resumes when that completes.
_RUNNING_SHELL = re.compile(r"\d+ shells? (still )?running|[·•] \d+ shell", re.IGNORECASE)

_CONTEXT_LEFT = re.compile(r"context left until auto-compact:\s*(\d{1,3})%", re.IGNORECASE)

_FULL = 100


def context_used_pct(pane: str) -> int | None:
    """Return the percentage of the window CONSUMED, or `None` when no bar is on screen.

    The inversion is the whole point: this harness reports what is left. Anchoring on the
    phrase rather than on a bare percentage is also what keeps a `95%` coverage line in
    scrolled output from tripping saturation.
    """

    matches = _CONTEXT_LEFT.findall(pane)
    return _FULL - int(matches[-1]) if matches else None


def pane_digest(pane: str) -> str:
    """Digest one captured pane. Digests are persisted between sweeps; pane text never is."""

    return hashlib.sha256(pane.encode("utf-8")).hexdigest()


def classify_pane(
    pane: str, *, saturation_percent: int, pane_changed: bool = False
) -> LivenessState:
    """Classify one captured pane against this binding's own declared window.

    `pane_changed` is a digest delta against the previous sweep, and it is the marker-free
    fallback rather than a first-class signal: first sight establishes the baseline only, so
    an unchanged pane stays idle.
    """

    lowered = pane.lower()
    used = context_used_pct(pane)
    return classify_state(
        dead_auth=any(marker in lowered for marker in DEAD_AUTH_MARKERS),
        capped=_is_capped(lowered),
        saturated=used is not None and used >= saturation_percent,
        working_marker=_is_working(pane, lowered),
        pane_changed=pane_changed,
    )


def _is_capped(lowered: str) -> bool:
    body = _BOOT_BANNER.sub(" ", lowered)
    return any(marker in body for marker in CAP_MARKERS) or bool(_REACHED_LIMIT.search(body))


def _is_working(pane: str, lowered: str) -> bool:
    return any(marker in lowered for marker in WORKING_MARKERS) or bool(_RUNNING_SHELL.search(pane))
