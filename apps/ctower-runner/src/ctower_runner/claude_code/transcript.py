"""Serving truth for a harness whose panes carry no parseable model footer.

Claude Code writes a session transcript under a directory named after the pane's own working
directory, and that transcript is the only place the served model appears. Treating the
footer's absence as agreement made an entire harness family read `unknown` forever, so this
binding declares the transcript as its serving source and nothing else.

Three rules the fleet paid for. `<synthetic>` turns are injected or compaction messages
rather than served turns, so they are stepped over and an all-synthetic file reports unknown.
A transcript older than an hour proves nothing: a stale file in a shared worktree once
reported a dead session's model as live truth. And a line that will not parse is stepped over
rather than ending the read, because a single truncated write must not blind the whole file.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from ctower_runner.claude_code.spec import TRANSCRIPT_STALE_AFTER

__all__ = [
    "SYNTHETIC_MODEL",
    "ServedModelReading",
    "newest_transcript",
    "served_model",
    "transcript_slug",
]

SYNTHETIC_MODEL = "<synthetic>"

_NON_SLUG = re.compile(r"[^A-Za-z0-9]")

# Reading the whole file to find the last assistant turn would make a long session's cost
# grow without bound; the served model is always within the last exchanges.
_TAIL_LINES = 200


@dataclass(frozen=True, slots=True)
class ServedModelReading:
    """The served model, or `unknown` with the reason named. Never a guess."""

    model: str | None
    basis: str

    def is_unknown(self) -> bool:
        return self.model is None


def transcript_slug(cwd: str) -> str:
    """Return the transcript directory name Claude Code derives from a pane's cwd."""

    return _NON_SLUG.sub("-", cwd)


def newest_transcript(entries: Sequence[tuple[str, datetime]]) -> str | None:
    """Pick the most recently modified transcript, or `None` when the directory is empty."""

    if not entries:
        return None
    return max(entries, key=lambda entry: entry[1])[0]


def served_model(lines: Sequence[str], *, age: timedelta) -> ServedModelReading:
    """Read the most recent real assistant turn's model out of one transcript."""

    if not lines:
        return ServedModelReading(None, "no transcript exists under this pane's cwd")
    if age > TRANSCRIPT_STALE_AFTER:
        return ServedModelReading(None, f"the transcript is {age} old and proves nothing")
    synthetic_seen = False
    for line in reversed(list(lines[-_TAIL_LINES:])):
        model = _assistant_model(line)
        if model == SYNTHETIC_MODEL:
            synthetic_seen = True
        elif model is not None:
            return ServedModelReading(model, "the most recent real assistant turn")
    if synthetic_seen:
        return ServedModelReading(None, "every recent turn is synthetic, so none was served")
    return ServedModelReading(None, "the transcript holds no assistant turn")


def _assistant_model(line: str) -> str | None:
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict) or row.get("type") != "assistant":
        return None
    message = row.get("message")
    if not isinstance(message, dict):
        return None
    model = message.get("model")
    return model if isinstance(model, str) and model else None
