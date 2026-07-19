"""Fail-closed confidentiality checks for the complete public report bytes."""

from __future__ import annotations

import re

from .models_core import CompatibilityError

__all__ = ["validate_public_report_bytes"]

_PRIVATE_PATH = re.compile(
    r"(?:/Users/[^/]+|/home/[^/]+|/var/folders/|/private/var/folders/|/tmp/|[A-Za-z]:\\\\Users\\\\[^\\]+)",
    re.IGNORECASE,
)
_CREDENTIAL_LIKE = re.compile(
    r"(?:"
    r"gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|[Bb]earer\s+[A-Za-z0-9._~+/-]{16,}"
    r"|https?://[^/@\s:]+:[^/@\s]+@"
    r"|(?:password|passwd|secret|token|api[_-]?key)"
    r"[\"']?\s*[:=]\s*[\"']?[^\s\",;]{8,}"
    r")",
    re.IGNORECASE,
)
_URL = re.compile(r"(?:https?|file)://", re.IGNORECASE)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?:\+[1-9][0-9 .()-]{7,20}[0-9]|\([0-9]{2,4}\)[ 0-9.-]{6,18}[0-9])")


def validate_public_report_bytes(encoded: bytes) -> None:
    """Inspect the exact final serialization, not a partial or pre-sanitized projection."""

    try:
        text = encoded.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CompatibilityError("public report is not valid UTF-8") from error
    if _PRIVATE_PATH.search(text):
        raise CompatibilityError("public report contains a private host or temporary path")
    if _CREDENTIAL_LIKE.search(text):
        raise CompatibilityError("public report contains credential-like material")
    if _URL.search(text):
        raise CompatibilityError("public report contains a URL")
    if _EMAIL.search(text) or _PHONE.search(text):
        raise CompatibilityError("public report contains explicit personal data")
