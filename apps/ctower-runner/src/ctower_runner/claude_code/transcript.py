"""Serving truth for a harness that names no model anywhere on its own screen.

Claude Code writes a session transcript under a directory named after the pane's own working
directory, and that transcript is the only place the model that actually answered appears.
Treating the pane's silence as agreement with what was requested made an entire harness
family report its served model as whatever the launcher asked for, so this binding declares
the transcript as its serving source and returns `None` by name when it cannot be believed.

Three rules the fleet paid for. `<synthetic>` rows are injected or compaction messages rather
than served turns, so they are stepped over and an all-synthetic file reports unknown. A
transcript older than an hour proves nothing: a stale file in a shared worktree once reported
a dead session's model as live truth. And a line that will not parse is stepped over rather
than ending the read, because one truncated write must not blind the whole file.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from ctower_runner.claude_code.spec import TRANSCRIPT_STALE_AFTER
from ctower_runner_sdk.attempt import AttemptPin

__all__ = [
    "SYNTHETIC_MODEL",
    "ServedModelReading",
    "SessionTranscript",
    "TranscriptSource",
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


class TranscriptSource(Protocol):
    """Whatever can list and read one transcript directory. No path handling leaks out."""

    def entries(self, slug: str) -> Sequence[tuple[str, datetime]]:
        """Return `(name, modified_at)` for every transcript under this slug."""

    def lines(self, name: str) -> Sequence[str]:
        """Return the transcript's lines, oldest first."""


class SessionTranscript:
    """The serving-truth port, over one directory listing and one line reader."""

    def __init__(
        self,
        source: TranscriptSource,
        worktree_for: Callable[[AttemptPin], str],
        clock: Callable[[], datetime],
    ) -> None:
        self._source = source
        self._worktree_for = worktree_for
        self._clock = clock

    def served_model(self, attempt: AttemptPin) -> str | None:
        """Return the model that answered this attempt's most recent real turn."""

        return self.reading(attempt).model

    def reading(self, attempt: AttemptPin) -> ServedModelReading:
        """The same answer with its basis, for a caller that reports why it is unknown."""

        slug = transcript_slug(self._worktree_for(attempt))
        entries = self._source.entries(slug)
        newest = newest_transcript(entries)
        if newest is None:
            return ServedModelReading(None, f"no transcript exists under {slug}")
        modified = next(at for name, at in entries if name == newest)
        return served_model(self._source.lines(newest), age=self._clock() - modified)


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
        return ServedModelReading(None, "the transcript under this pane's cwd is empty")
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
