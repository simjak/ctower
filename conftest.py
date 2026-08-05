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

# Value-shaped secrets: a credential rendered under a key name that never matches
# `_SENSITIVE_KEY` (`dsn`, `innocent_header`, `payload`, ...). Key-based scrubbing cannot see
# these, so the value's own shape is the only signal. Each pattern redacts the credential
# portion where the shape has a separable non-secret part worth keeping for diagnosis (a DSN's
# host/db, a Bearer scheme word); whole-value where it does not (a base64/JWT blob IS the
# secret).
_URL_CREDENTIAL = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<user>[^:/@\s]+):(?P<password>[^@/\s]+)@"
)
_BEARER_TOKEN = re.compile(r"\bBearer\s+(?P<token>\S+)")
_AUTH_HEADER = re.compile(r"\b(?P<name>Authorization|Cookie|Set-Cookie)\s*:\s*(?P<value>.+)")
_JWT_SHAPE = re.compile(r"\bey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_BASE64_CHARSET = re.compile(r"[A-Za-z0-9+/_-]{24,}={0,2}")


def _is_sensitive_key(name: object) -> bool:
    return _SENSITIVE_KEY.search(str(name)) is not None


def _looks_like_base64_secret(text: str) -> bool:
    if not _BASE64_CHARSET.fullmatch(text):
        return False
    return any(char.isupper() for char in text) and any(
        char.islower() or char.isdigit() for char in text
    )


def _redact_value_shapes(text: str) -> str:
    if _looks_like_base64_secret(text):
        return _REDACTED
    text = _JWT_SHAPE.sub(_REDACTED, text)
    text = _URL_CREDENTIAL.sub(lambda m: f"{m['scheme']}{m['user']}:{_REDACTED}@", text)
    text = _BEARER_TOKEN.sub(f"Bearer {_REDACTED}", text)
    text = _AUTH_HEADER.sub(lambda m: f"{m['name']}: {_REDACTED}", text)
    return text


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
    if isinstance(value, str):
        return _redact_value_shapes(value)
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
