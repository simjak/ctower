"""Repo-wide pytest hook: secret-shaped values never render in failure output.

gh#290 — a failing test's rendered locals/funcargs included a live `ANTHROPIC_AUTH_TOKEN` because
pytest's default failure display shows a frame's call arguments (`repr_args`, on by default) and,
under `-l`/`--showlocals`, its full locals (`repr_locals`). `--tb=short` alone only turns off the
*default* funcargs display; a developer debugging a flaky test with `-l`/`--showlocals`/`--tb=long`
(exactly what produced the original leak) defeats it. Redacting by key name at the point pytest
builds these reprs is invariant to `--tb`/`-l`/`--showlocals` choice and keeps every non-sensitive
frame argument, local, and traceback line intact.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

try:
    from _pytest._code.code import FormattedExcinfo as _ExcinfoFormatter
except ImportError:  # pytest 9 renamed FormattedExcinfo to ExceptionInfoFormatter
    from _pytest._code.code import ExceptionInfoFormatter as _ExcinfoFormatter
from _pytest._code.code import ReprFuncArgs, ReprLocals, TracebackEntry
from _pytest._io.saferepr import saferepr

_SENSITIVE_KEY = re.compile(r"TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL|AUTH", re.IGNORECASE)
_REDACTED = "***REDACTED***"
_MAX_DEPTH = 6


def _is_sensitive_key(name: object) -> bool:
    return _SENSITIVE_KEY.search(str(name)) is not None


def _redact_value(value: object, depth: int = 0) -> object:
    if depth >= _MAX_DEPTH:
        return value
    if isinstance(value, Mapping):
        return {
            key: _REDACTED if _is_sensitive_key(key) else _redact_value(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return type(value)(_redact_value(item, depth + 1) for item in value)
    return value


def _redact_named(name: str, value: object) -> object:
    return _REDACTED if _is_sensitive_key(name) else _redact_value(value)


_original_repr_locals = _ExcinfoFormatter.repr_locals


def _redacting_repr_locals(
    self: _ExcinfoFormatter, locals: Mapping[str, object]
) -> ReprLocals | None:
    if not self.showlocals:
        return None
    safe_locals = {name: _redact_named(name, value) for name, value in locals.items()}
    return _original_repr_locals(self, safe_locals)


def _redacting_repr_args(self: _ExcinfoFormatter, entry: TracebackEntry) -> ReprFuncArgs | None:
    if not self.funcargs:
        return None
    args = []
    for argname, argvalue in entry.frame.getargs(var=True):
        safe_value = _redact_named(argname, argvalue)
        str_repr = (
            saferepr(safe_value) if self.truncate_args else saferepr(safe_value, maxsize=None)
        )
        args.append((argname, str_repr))
    return ReprFuncArgs(args)


_ExcinfoFormatter.repr_locals = _redacting_repr_locals  # type: ignore[method-assign]
_ExcinfoFormatter.repr_args = _redacting_repr_args  # type: ignore[method-assign]
