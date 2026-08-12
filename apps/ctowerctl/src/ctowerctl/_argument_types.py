"""Validating argparse value converters for the authored CLI grammar.

These are the type converters ``_parser`` hands to ``add_argument``: each one refuses a
value outside the authored contract at the process boundary rather than letting a
malformed number, timestamp, digest, or URL reach a request builder.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
from datetime import datetime
from urllib.parse import SplitResult, urlsplit

__all__: tuple[str, ...] = ()

_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_BEAT_ROUTINE_REF = re.compile(r"^ctower\.beat\.[a-z][a-z0-9._-]*@[1-9][0-9]*$")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def _assertions(value: str) -> tuple[str, ...]:
    parsed = tuple(value.split(","))
    if parsed != ("resolved", "closed"):
        raise argparse.ArgumentTypeError("synthetic assertion must be resolved,closed")
    return parsed


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed


def _sha256_digest(value: str) -> str:
    if _SHA256_DIGEST.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(
            "digest must be 'sha256:' followed by exactly 64 lowercase hex digits"
        )
    return value


def _beat_routine_ref(value: str) -> str:
    if _BEAT_ROUTINE_REF.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("routine reference must identify a versioned fleet beat")
    return value


def _safe_base_url(value: str) -> str:
    parsed = _split_base_url(value)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"}:
        raise argparse.ArgumentTypeError("base URL must be absolute HTTP(S)")
    if host is None:
        raise argparse.ArgumentTypeError("base URL must be absolute HTTP(S)")
    if _has_forbidden_url_parts(parsed):
        raise argparse.ArgumentTypeError("base URL must not contain credentials or suffix data")
    if parsed.scheme == "http" and not _loopback(host):
        raise argparse.ArgumentTypeError("cleartext HTTP is permitted only for loopback")
    return value


def _split_base_url(value: str) -> SplitResult:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        raise argparse.ArgumentTypeError("base URL syntax is invalid") from error
    return parsed


def _has_forbidden_url_parts(parsed: SplitResult) -> bool:
    return any((parsed.username, parsed.password, parsed.query, parsed.fragment))


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
