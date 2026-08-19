"""Codex-private pane reading. Nothing in this module crosses the seam.

What a reading *means* is `classify_state`'s answer, identical for every binding. What this
module owns is the harness-private half — which bytes on this substrate say cap, dead auth,
saturation, or work — and three rules this harness in particular forces.

**Auth is not quota, and this substrate says both in one breath.** `You've hit your usage
limit … purchase more credits` is a spent window that returns at a stated time; `Your access
token could not be refreshed` is a dead lineage that no waiting repairs. The fleet's own
crew-health tool collapsed the first into its dead-auth list, and a collapsed reading sends the
reader to a re-mint ceremony that burns a fresh single-use device flow against a credential
that was never broken.

**The percentage arrives in two opposite forms.** This CLI ships a percent-*remaining* status
item and a percent-*consumed* one, and which is on screen is configuration. A reader that
assumed either form would report a lane with 8% left as 8% consumed — the healthy answer for
the failing case — on every pane configured the other way. Both are read, and only the phrase
is anchored on, which is also what keeps a `95%` coverage line in scrolled output from
tripping saturation.

**A cap marker may not be a URL.** The healthy `/status` panel prints the same
`chatgpt.com/codex/settings/usage` link the cap message does, so the marker is the sentence
and never the link.
"""

from __future__ import annotations

import re

from ctower_runner_sdk.facts import LivenessState
from ctower_runner_sdk.policy import classify_state

__all__ = [
    "CAP_MARKERS",
    "DEAD_AUTH_MARKERS",
    "WORKING_MARKERS",
    "classify_pane",
    "context_used_pct",
]

# Every phrasing this fleet has actually seen mean "this window is spent". New phrasings belong
# here, in the classifier — the last extension of a list like this was lost because the repair
# was left in a shared repository's working tree and a later commit overwrote it.
CAP_MARKERS: tuple[str, ...] = (
    "hit your usage limit",
    "purchase more credits",
    "quota exceeded",
    "usage limited",
    "limited by budget",
    "out of credits",
    "upgrade to plus",
)

# A codex lane that lost its grant says so in words, while the composer keeps rendering.
DEAD_AUTH_MARKERS: tuple[str, ...] = (
    "access token could not be refreshed",
    "could not parse your authentication token",
    "log out and sign in again",
    "please try signing in again",
    "refresh token was revoked",
)

# The run-state text and the interrupt hint. These are codex-shaped and not hermes-shaped: a
# timer-glyph pattern once read five working hermes lanes as idle, and the mirror-image mistake
# is available here for anyone who reuses that pattern without looking.
WORKING_MARKERS: tuple[str, ...] = ("working (", "esc to interrupt", "thinking")

_CONTEXT_USED = re.compile(r"context\s+(\d{1,3})\s*%\s*used", re.IGNORECASE)
_CONTEXT_LEFT = re.compile(
    r"context\s+(\d{1,3})\s*%\s*left|(\d{1,3})\s*%\s*context\s+left", re.IGNORECASE
)

_FULL = 100


def context_used_pct(pane: str) -> int | None:
    """Return the percentage of the window CONSUMED, or `None` when nothing states it.

    The consumed form is read first because it needs no arithmetic; the remaining form is
    inverted. Anchoring on the word rather than on a bare percentage is what keeps a coverage
    line out of this reading entirely.
    """

    consumed = _CONTEXT_USED.findall(pane)
    if consumed:
        return int(consumed[-1])
    remaining = _CONTEXT_LEFT.findall(pane)
    if not remaining:
        return None
    phrase, prefix = remaining[-1]
    return _FULL - int(phrase or prefix)


def classify_pane(
    pane: str, *, saturation_percent: int, pane_changed: bool = False
) -> LivenessState:
    """Classify one captured pane against this binding's own declared window.

    This answers for the SUBSTRATE only. When the pool disagrees with it — exhaustion arrives
    as a non-retryable 401 on the first real call while this pane still renders a healthy
    composer — the binding reports the pool's fact instead, because the pane is the one that
    cannot see the credential.
    """

    lowered = pane.lower()
    used = context_used_pct(pane)
    return classify_state(
        dead_auth=any(marker in lowered for marker in DEAD_AUTH_MARKERS),
        capped=any(marker in lowered for marker in CAP_MARKERS),
        saturated=used is not None and used >= saturation_percent,
        working_marker=any(marker in lowered for marker in WORKING_MARKERS),
        pane_changed=pane_changed,
    )
