"""Captured codex substrate, and where each sample actually came from.

An untested monitor pattern is not a monitor, and a pattern tested only against a sample its
own author wrote is not tested. So every case carries `captured` and `provenance`, and the
cases that could not be taken off a live pane say so rather than borrowing the credibility of
the ones that could.

The live captures below were read with `tmux capture-pane -p` off a real `codex-cli 0.147.0`
TUI started on a throwaway socket and directory for the purpose. The raw `~/.codex` chain on
this host is dead, which is why the auth samples here are the real thing and the working
samples are not. The cap sample is the provider's own message, read out of a recorded session
rollout on this host.

Two of these exist because they are the pairs that fool a classifier. The healthy status panel
and the cap message carry the *same* `chatgpt.com/codex/settings/usage` URL, so a URL-shaped
cap marker reports a resting account as a spent one. And this status line ships **both** a
percent-remaining and a percent-consumed item, so a reader anchored on a bare percentage
inverts whichever half of the fleet it did not happen to test against.
"""

from __future__ import annotations

from ctower_runner_sdk.conformance import CorpusCase

__all__ = ["CODEX_CORPUS", "captured_cases"]

_LIVE = "captured 2026-08-19T21:38Z from a codex-cli 0.147.0 TUI on tmux -L t3codexcap"
_ROLLOUT = "captured verbatim from a recorded ~/.codex/sessions rollout error payload"
_COMPOSED = "composed from the status-line items codex-cli 0.147.0 itself ships"

# The captured status line: the model the launcher asked for, then the directory. The model is
# on screen and is still not serving truth — it is the launch argument, rendered back.
_STATUS_LINE = "  gpt-5.6-sol max · /tmp/t3-codex-cap"

CODEX_CORPUS: tuple[CorpusCase, ...] = (
    CorpusCase(
        label="a fresh composer with no run-state text is idle",
        # The composer glyph is escaped rather than pasted: it is ambiguous with `>` on sight,
        # and a corpus sample must stay byte-exact to the capture it claims to be.
        sample=f"\u203a Implement {{feature}}\n\n{_STATUS_LINE}",
        expected="idle",
        captured=True,
        provenance=f"{_LIVE}, the first prompt after the trust gate",
    ),
    CorpusCase(
        label="the startup banner names the model and proves nothing about a turn",
        sample=(
            "╭───────────────────────────────────────────────╮\n"
            "│ >_ OpenAI Codex (v0.147.0)                    │\n"
            "│                                               │\n"
            "│ model:     gpt-5.6-sol max   /model to change │\n"
            "│ directory: /tmp/t3-codex-cap                  │\n"
            "╰───────────────────────────────────────────────╯"
        ),
        expected="idle",
        captured=True,
        provenance=f"{_LIVE}, the startup banner",
    ),
    CorpusCase(
        label="the healthy status panel carries the cap message's own usage URL",
        sample=(
            "│ Visit https://chatgpt.com/codex/settings/usage for up-to-date      │\n"
            "│ information on rate limits and credits                             │"
        ),
        expected="idle",
        captured=True,
        provenance=(
            f"{_LIVE}, the /status panel header — the false-positive vector for any "
            "URL-shaped or credits-shaped cap marker"
        ),
    ),
    CorpusCase(
        label="the substrate's own limits reading is absent, not available",
        sample=(
            "│  Token usage:          0 total  (0 input + 0 output)               │\n"
            "│  Limits:               data not available yet                      │\n"
            "╰────────────────────────────────────────────────────────────────────╯"
        ),
        expected="idle",
        captured=True,
        provenance=(
            f"{_LIVE}, the /status panel footer — this is why quota is never read off "
            "this pane and the pool is asked instead"
        ),
    ),
    CorpusCase(
        label="a refused refresh is dead auth while the composer still renders",
        sample=(
            "■ Your access token could not be refreshed. Please log out and sign in again.\n"
            f"\n\u203a Implement {{feature}}\n\n{_STATUS_LINE}"
        ),
        expected="dead_auth",
        captured=True,
        provenance=f"{_LIVE}, the answer to a submitted turn on a dead lineage",
    ),
    CorpusCase(
        label="an unparsed token is the same fact in the provider's other wording",
        sample=(
            "⚠ MCP client for `codex_apps` failed to start: "
            "unexpected server response: HTTP 401: {\n"
            '    "message": "Could not parse your authentication token. '
            'Please try signing in again.",\n'
            '    "code": "unauthorized_unknown"\n'
            "  }, when send initialize request"
        ),
        expected="dead_auth",
        captured=True,
        provenance=f"{_LIVE}, the startup handshake against the same dead lineage",
    ),
    CorpusCase(
        label="a spent window is capped and never dead auth",
        sample=(
            "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
            "to purchase more credits or try again at Aug 20th, 2026 5:29 AM."
        ),
        expected="capped",
        captured=True,
        provenance=(
            f"{_ROLLOUT} (codex_error_info usage_limit_exceeded) — the fleet's own "
            "crew-health tool lists this phrasing under DEAD_AUTH and this classifier "
            "deliberately does not: auth is not quota, and one word loses the reset"
        ),
    ),
    CorpusCase(
        label="the run-state text is the working marker on this harness",
        sample=f"Working (2m 14s)\n{_STATUS_LINE} · Esc to interrupt · Context 71% left",
        expected="working",
        captured=False,
        provenance=(
            f"{_COMPOSED}; this host's chain is dead, so no live turn could be captured, "
            "and the markers are the binary's own run-state and interrupt items"
        ),
    ),
    CorpusCase(
        label="a large-window lane at a high absolute token count is healthy",
        sample=(
            "Working (11m 03s)\n"
            f"{_STATUS_LINE} · Esc to interrupt · 295k tokens used · Context 71% left"
        ),
        expected="working",
        captured=False,
        provenance=f"{_COMPOSED}; the absolute counter is deliberately not a saturation source",
    ),
    CorpusCase(
        label="percent-remaining is inverted before the threshold is applied",
        sample=f"{_STATUS_LINE} · Esc to interrupt · Context 8% left",
        expected="saturated",
        captured=False,
        provenance=f"{_COMPOSED}; `Context 0% left` is that item's own placeholder text",
    ),
    CorpusCase(
        label="the same status line configured the other way reports consumption directly",
        sample=f"{_STATUS_LINE} · Esc to interrupt · Context 94% used",
        expected="saturated",
        captured=False,
        provenance=(
            f"{_COMPOSED}; `Context 0% used` is the sibling item, and a reader that "
            "assumed one form would invert every pane configured with the other"
        ),
    ),
    CorpusCase(
        label="a coverage percentage in scrolled output is not a context reading",
        sample="TOTAL                        4211    210    95%   Required coverage of 90% reached",
        expected="idle",
        captured=False,
        provenance="composed false-positive vector for the percentage anchor",
    ),
)


def captured_cases() -> tuple[CorpusCase, ...]:
    """The subset read verbatim off a real substrate."""

    return tuple(case for case in CODEX_CORPUS if case.captured)
