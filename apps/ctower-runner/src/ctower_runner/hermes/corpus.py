"""Captured hermes substrate output, and the state each sample must classify to.

Every `captured=True` sample below was read verbatim off a live hermes pane on the fleet's
shared tmux socket on 2026-08-19; the provenance names the session it came from. They are
here because the first saturation detector written for this fleet matched nothing at all —
`█+` is a byte quantifier in this locale and silently failed against the real multibyte
footer — and it would have reported a clean fleet forever. An untested monitor pattern is
not a monitor, so a classifier without a corpus is decoration.

The `captured=False` samples are composed in the captured shape, and say so. Two classes
could not be read live: no lane was saturated or capped during the capture window. Their
numbers are the recorded incident's own — 178K against a 131.1K window — rather than
invented ones, and the shape is byte-for-byte the shape above them.
"""

from __future__ import annotations

from ctower_runner_sdk.conformance import CorpusCase

__all__ = ["HERMES_CORPUS", "captured_cases"]

_LIVE = "captured 2026-08-19 from tmux -L mc session"
_COMPOSED = "composed in the captured footer shape"

HERMES_CORPUS: tuple[CorpusCase, ...] = (
    CorpusCase(
        label="large-window lane at a high absolute token count is healthy",
        sample=" ⚕ gpt-5.6-sol │ 295K/1.1M │ [███░░░░░░░] 28% │ 🗜️  2 │ 8h 46m │ ⏲ 17m 54s │ ✓...",
        expected="working",
        captured=True,
        provenance=f"{_LIVE} mc-review-3928-monitor",
    ),
    CorpusCase(
        label="timer glyph proves working where an esc hint would not",
        sample=" ⚕ gpt-5.6-luna │ 63.1K/1.1M │ [█░░░░░░░░░] 6% │ 🗜️  4 │ 42m │ ⏲ 2m 36s │ ✓ 0s...",
        expected="working",
        captured=True,
        provenance=f"{_LIVE} mc-engineer-keda-podload",
    ),
    CorpusCase(
        label="the second timer glyph is the same fact",
        sample=" ⚕ gpt-5.6-luna │ 124K/1.1M │ [█░░░░░░░░░] 12% │ 🗜️  23 │ 22h 57m │ ⏱ 7m 40s │...",
        expected="working",
        captured=True,
        provenance=f"{_LIVE} mc-engineer-qa-canary",
    ),
    CorpusCase(
        label="a footer with no compression counter still parses",
        sample=" ⚕ gpt-5.6-sol │ 182K/1.1M │ [██░░░░░░░░] 17% │ 23m │ ⏲ 15m 59s │ ✓ 7m │ ⚠ YOLO",
        expected="working",
        captured=True,
        provenance=f"{_LIVE} mc-review-3939-binary",
    ),
    CorpusCase(
        label="a lane between turns shows the banner and no timer",
        sample="╭─ ⚕ Hermes ───────────────────────────────────────────────────────────────────╮",
        expected="idle",
        captured=True,
        provenance=f"{_LIVE} mc-engineer-probe-fk",
    ),
    CorpusCase(
        label="a coverage percentage in scrolled output is not a context bar",
        sample="TOTAL                        4211    210    95%   Required coverage of 90% reached",
        expected="idle",
        captured=False,
        provenance="composed false-positive vector for the percentage anchor",
    ),
    CorpusCase(
        label="at the declared threshold the lane is saturated, timer or not",
        sample=" ⚕ gpt-5.6-sol │ 118K/131.1K │ [█████████░] 90% │ ⏲ 4m 02s │ ✓ 2m",
        expected="saturated",
        captured=False,
        provenance=f"{_COMPOSED}; threshold case for the 90% floor",
    ),
    CorpusCase(
        label="past the window the lane is saturated while it is still emitting",
        sample=" ⚕ gpt-5.6-sol │ 178K/131.1K │ [██████████] 136% │ ⏲ 3m 12s │ ✓ 1m",
        expected="saturated",
        captured=False,
        provenance=f"{_COMPOSED}; numbers from the 2026-08-16 CSO-gate incident",
    ),
    CorpusCase(
        label="a limit banner is capped even while the timer advances",
        sample=(
            " ⚕ gpt-5.6-sol │ 40K/1.1M │ [█░░░░░░░░░] 4% │ ⏲ 0m 11s\n"
            "You've reached your gpt-5.6-sol limit · Upgrade your plan to continue"
        ),
        expected="capped",
        captured=False,
        provenance=f"{_COMPOSED}; phrasings from the committed fleet cap classifier",
    ),
    CorpusCase(
        label="out of credits is a cap, not a slowdown",
        sample="hermes: request failed — you are out of credits. Add credits with /usage-credits",
        expected="capped",
        captured=False,
        provenance=f"{_COMPOSED}; phrasings from the committed fleet cap classifier",
    ),
    CorpusCase(
        label="a pool error is dead auth, whatever the substrate says",
        sample="hermes: credential pool: no available entries (401, non-retryable)",
        expected="dead_auth",
        captured=False,
        provenance=f"{_COMPOSED}; the engine's own pool-exhaustion wording",
    ),
)


def captured_cases() -> tuple[CorpusCase, ...]:
    """The subset read verbatim off a real substrate."""

    return tuple(case for case in HERMES_CORPUS if case.captured)
