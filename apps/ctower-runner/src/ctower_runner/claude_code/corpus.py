"""Captured Claude Code substrate, and where each sample actually came from.

An untested monitor pattern is not a monitor, and a pattern tested only against a sample its
own author wrote is not tested. So every case carries `captured` and `provenance`, and the
two cases that could not be taken from a live pane say so rather than borrowing the
credibility of the ones that could.

The live captures below were taken read-only with `tmux -L mc capture-pane -p` at
2026-08-19T13:59Z, across the fleet's own Claude Code panes.
"""

from __future__ import annotations

from dataclasses import dataclass

from ctower_runner.claude_code.liveness import PaneState

__all__ = ["CLAUDE_CODE_CORPUS", "CorpusCase"]

_SWEEP = "live tmux capture-pane, 2026-08-19T13:59Z"

# The footer every Claude Code pane on this fleet carries while a turn is running.
_WORKING_FOOTER = "  ⏵⏵ bypass permissions on (shift+tab to cycle) · esc to interrupt · ← 1 agent"


@dataclass(frozen=True, slots=True)
class CorpusCase:
    """One captured sample and the state this binding must read out of it.

    SEAM INTEGRATION (CT-I1-041): this shape feeds the shared conformance suite's captured
    corpus assertion once the seam lands.
    """

    label: str
    sample: str
    expected: PaneState
    captured: bool
    provenance: str


CLAUDE_CODE_CORPUS: tuple[CorpusCase, ...] = (
    CorpusCase(
        label="working-esc-interrupt",
        sample=(
            "✻ Newspapering… (6m 21s · ↑ 23.2k tokens · thought for 2s)\n" + _WORKING_FOOTER + "\n"
        ),
        expected="working",
        captured=True,
        provenance=f"{_SWEEP}, session mc-engineer-t2-claude-adapter",
    ),
    CorpusCase(
        label="working-running-shell-no-esc-hint",
        sample=(
            "✻ Sautéed for 3m 30s · 1 shell still running\n"
            "  ⏵⏵ bypass permissions on · 1 shell · ← 1 agent · ↓ to manage\n"
        ),
        expected="working",
        captured=True,
        provenance=(
            f"{_SWEEP}, session mc-commander-manibo — the turn ended while its gate run "
            "continues, which read as idle before the running-shell marker existed"
        ),
    ),
    CorpusCase(
        label="idle-empty-composer",
        # The composer prompt is escaped rather than pasted: the captured glyph is ambiguous
        # with `>` on sight, and a corpus sample must stay byte-exact to the capture.
        sample="\u276f \n  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← 1 agent\n",
        expected="idle",
        captured=True,
        provenance=f"{_SWEEP}, session mc-engineer-correspondents-grant",
    ),
    CorpusCase(
        label="dead-auth-under-a-working-footer",
        sample="                    Not logged in · Run /login\n" + _WORKING_FOOTER + "\n",
        expected="dead_auth",
        captured=True,
        provenance=(
            f"{_SWEEP}, session commander-ctower-fable — the pane carries the interrupt hint "
            "and no live grant at the same time, so the working marker must not win"
        ),
    ),
    CorpusCase(
        label="capped-in-band-limit-text",
        sample=(
            "You've reached your Fable 5 limit. "
            "Run /usage-credits to continue or switch models with /model.\n"
        ),
        expected="capped",
        captured=True,
        provenance=(
            "the director's live one-shot response, recorded in mission-control "
            "state/inbox.jsonl — the account's own capacity file read `alive` at that moment"
        ),
    ),
    CorpusCase(
        label="capped-menu-that-matched-the-working-pattern",
        sample=(
            "You've reached your Fable 5 limit.\n"
            "  1. Switch models  2. Upgrade your plan\n"
            "  Enter to confirm · Esc to cancel\n"
        ),
        expected="capped",
        captured=False,
        provenance=(
            "reconstructed from the incident preserved in mission-control "
            "tools/ctower-beat-watchdog — the menu's `Esc to cancel` line matched the generic "
            "working pattern and a rate-limit-dead lane counted as working for hours; no "
            "capped pane was live at capture time"
        ),
    ),
    CorpusCase(
        label="saturated-context-left-under-a-working-footer",
        sample="Context left until auto-compact: 8%\n" + _WORKING_FOOTER + "\n",
        expected="saturated",
        captured=False,
        provenance=(
            "the line mission-control tools/context-check reads off live Claude Code panes, "
            "over a captured footer; no pane was near auto-compact at capture time"
        ),
    ),
)
