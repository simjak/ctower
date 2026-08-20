"""Captured Claude Code substrate, and where each sample actually came from.

An untested monitor pattern is not a monitor, and a pattern tested only against a sample its
own author wrote is not tested. So every case carries `captured` and `provenance`, and the
cases that could not be taken off a live pane say so rather than borrowing the credibility of
the ones that could.

The live captures below were read read-only with `tmux -L mc capture-pane -p` on the fleet's
shared socket, and the provenance names the session each one came from.
"""

from __future__ import annotations

from ctower_runner_sdk.conformance import CorpusCase

__all__ = ["CLAUDE_CODE_CORPUS", "captured_cases"]

_SWEEP = "captured 2026-08-19T13:59Z from tmux -L mc session"
_LATER = "captured 2026-08-19T19:19Z from tmux -L mc session"
_COMPOSED = "composed in the captured pane shape"

# The footer every Claude Code pane on this fleet carries while a turn is running. It names a
# permission mode, an agent count, and an interrupt hint — and no model, which is why serving
# truth on this harness comes from the transcript and never from what is on screen.
_WORKING_FOOTER = "  ⏵⏵ bypass permissions on (shift+tab to cycle) · esc to interrupt · ← 1 agent"

CLAUDE_CODE_CORPUS: tuple[CorpusCase, ...] = (
    CorpusCase(
        label="the interrupt hint is the working marker on this harness",
        sample=(
            "✻ Newspapering… (6m 21s · ↑ 23.2k tokens · thought for 2s)\n" + _WORKING_FOOTER + "\n"
        ),
        expected="working",
        captured=True,
        provenance=f"{_SWEEP} mc-engineer-t2-claude-adapter",
    ),
    CorpusCase(
        label="a composer holding queued messages under a working footer is still working",
        sample=(
            "\u276f\u00a0Press up to edit queued messages\n"
            "  ⏵⏵ bypass permissions on (shift+tab to cycle) · esc to interrupt · ← 1 agent\n"
        ),
        expected="working",
        captured=True,
        provenance=(
            f"{_LATER} commander-ctower-fable — text sitting in the composer is not the same "
            "fact as an idle lane, and only the footer separates them"
        ),
    ),
    CorpusCase(
        label="a running shell with no interrupt hint is working, not idle",
        sample=(
            "✻ Sautéed for 3m 30s · 1 shell still running\n"
            "  ⏵⏵ bypass permissions on · 1 shell · ← 1 agent · ↓ to manage\n"
        ),
        expected="working",
        captured=True,
        provenance=(
            f"{_SWEEP} mc-commander-manibo — the turn ended while its gate run continues, "
            "which read as idle before the running-shell marker existed"
        ),
    ),
    CorpusCase(
        label="an empty composer with no interrupt hint is idle",
        # The composer prompt is escaped rather than pasted: the captured glyph is ambiguous
        # with `>` on sight, and a corpus sample must stay byte-exact to the capture.
        sample="\u276f \n  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← 1 agent\n",
        expected="idle",
        captured=True,
        provenance=f"{_SWEEP} mc-engineer-correspondents-grant",
    ),
    CorpusCase(
        label="the same footer without the interrupt hint is idle",
        sample=(
            "✻ Crunched for 57m 13s\n"
            "\u276f\u00a0\n"
            "  ⏵⏵ bypass permissions on (shift+tab to cycle) · PR #534 · ← 1 agent\n"
        ),
        expected="idle",
        captured=True,
        provenance=(
            f"{_LATER} mc-engineer-534-repair2 — the elapsed-time line survives the turn that "
            "produced it, so a spinner phrase alone never proves a lane is working"
        ),
    ),
    CorpusCase(
        label="a coverage percentage in scrolled output is not a context reading",
        sample="TOTAL                        4211    210    95%   Required coverage of 90% reached",
        expected="idle",
        captured=False,
        provenance=f"{_COMPOSED}; composed false-positive vector for the percentage anchor",
    ),
    CorpusCase(
        label="dead auth wins under a footer that says the lane is working",
        sample="                    Not logged in · Run /login\n" + _WORKING_FOOTER + "\n",
        expected="dead_auth",
        captured=True,
        provenance=(
            f"{_SWEEP} commander-ctower-fable — the pane carries the interrupt hint and no "
            "live grant at the same time, so the working marker must not win"
        ),
    ),
    CorpusCase(
        label="the in-band limit response is capped",
        sample=(
            "You've reached your Fable 5 limit. "
            "Run /usage-credits to continue or switch models with /model.\n"
        ),
        expected="capped",
        captured=True,
        provenance=(
            "captured from the director's own live one-shot response, recorded in "
            "mission-control state/inbox.jsonl — the account's capacity file read `alive` "
            "at that moment"
        ),
    ),
    CorpusCase(
        label="the limit menu that matched the generic working pattern",
        sample=(
            "You've reached your Fable 5 limit.\n"
            "  1. Switch models  2. Upgrade your plan\n"
            "  Enter to confirm · Esc to cancel\n"
        ),
        expected="capped",
        captured=False,
        provenance=(
            f"{_COMPOSED}; reconstructed from the incident preserved in mission-control "
            "tools/ctower-beat-watchdog — the menu's `Esc to cancel` line matched the generic "
            "working pattern and a rate-limit-dead lane counted as working for hours. No "
            "capped pane was live at either capture window"
        ),
    ),
    CorpusCase(
        label="the boot banner counts windows that already reset and is not a cap",
        sample="  2 usage limit resets available\n" + _WORKING_FOOTER + "\n",
        expected="working",
        captured=False,
        provenance=(
            f"{_COMPOSED}; the startup notice carries the substring `usage limit`, which is "
            "why it is stripped before the cap match rather than matched by it"
        ),
    ),
    CorpusCase(
        label="the context bar is percent LEFT, so 8% remaining is saturated",
        sample="Context left until auto-compact: 8%\n" + _WORKING_FOOTER + "\n",
        expected="saturated",
        captured=False,
        provenance=(
            f"{_COMPOSED}; the line mission-control tools/context-check reads off live Claude "
            "Code panes, over a captured footer. No pane was near auto-compact at either "
            "capture window"
        ),
    ),
    CorpusCase(
        label="a large absolute token count on a full window is healthy",
        sample=(
            "✻ Newspapering… (6m 21s · ↑ 232k tokens)\n"
            "Context left until auto-compact: 64%\n" + _WORKING_FOOTER + "\n"
        ),
        expected="working",
        captured=False,
        provenance=(
            f"{_COMPOSED}; the counter-fixture for the percentage rule — ten times the token "
            "count of the healthy capture above, and healthy for exactly the same reason"
        ),
    ),
)


def captured_cases() -> tuple[CorpusCase, ...]:
    """The subset read verbatim off a real substrate."""

    return tuple(case for case in CLAUDE_CODE_CORPUS if case.captured)
