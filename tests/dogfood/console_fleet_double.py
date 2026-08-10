#!/usr/bin/env python3
"""A tmux stand-in that answers exactly the listings this surface asks for.

The crew surface reads the live fleet through ``tmux``, so a render test that
used the real one would assert against whatever this host happened to be
running while it ran. ``CTOWER_UI_EXEC_TMUX`` exists for precisely this: every
interim source is overridable so an evidence driver can exercise it without
touching live state.

Four crews, because the ceremony has four different things to prove and each
needs a session the record answers differently for: the whole walk, a grant
that ends while nobody touches it, an incarnation the record has revoked, and a
mint the record refuses.

This answers by format string rather than by subcommand, because that is what
distinguishes the three listings the roster asks for. An unrecognised
invocation exits non-zero rather than answering empty: a source that silently
returned nothing would render as a fleet with no crews, which is the opposite
claim to the one this fixture is making.
"""

from __future__ import annotations

import sys

__all__ = ("CREWS",)

CREWS = (
    ("mc-engineer-371-console", "ctower"),
    ("mc-qa-m1-rerun2", "ctower"),
    ("mc-designer-3388-callcard", "manibo"),
    ("mc-review-390-verdict", "ctower"),
)
_CREATED = "1786000000"
_ACTIVITY = "1786003600"
_WORKTREE = "/srv/projects/ctower/.worktrees/r371-console"

_PANE = (
    "$ uv run pytest tests/acceptance/increment-1/test_console_eligibility.py -q\n"
    "...........................                                        [ 62%]\n"
    "1 failed, 37 passed in 18.42s\n"
    "$ "
)
_PANES = "#{session_name}\t#{pane_current_path}\t#{pane_current_command}\t#{pane_width}"
_LIVENESS = "#{session_name}\t#{session_created}\t#{session_activity}\t#{session_attached}"


def _listing(fmt: str) -> str | None:
    if fmt == "#{session_name}":
        return "\n".join(name for name, _ in CREWS)
    if fmt == _LIVENESS:
        return "\n".join(f"{name}\t{_CREATED}\t{_ACTIVITY}\t0" for name, _ in CREWS)
    if fmt == "#{session_name}\t#{@project}":
        return "\n".join(f"{name}\t{project}" for name, project in CREWS)
    return None


def _answer(argv: list[str]) -> str | None:
    """What this invocation lists, or `None` when it is not one this fixture knows."""
    if not argv:
        return None
    if argv[0] == "capture-pane":
        return _PANE
    if "-F" not in argv:
        return None
    fmt = argv[argv.index("-F") + 1]
    if argv[0] == "list-panes":
        panes = "\n".join(f"{name}\t{_WORKTREE}\tzsh\t120" for name, _ in CREWS)
        return panes if fmt == _PANES else None
    return _listing(fmt) if argv[0] == "list-sessions" else None


def main(argv: list[str]) -> int:
    answer = _answer(argv)
    if answer is None:
        return 2
    sys.stdout.write(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
