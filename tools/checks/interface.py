"""Small public Interface for all repository-policy callers."""

from __future__ import annotations

from pathlib import Path

from tools.checks._impl.suites import verify_expected_suites as _verify_expected_suites
from tools.checks._impl.verifier import run_verification
from tools.checks.report import (
    ExpectedSuitesReport,
    Finding,
    PolicyReport,
    Severity,
    SuiteDisposition,
    SuiteResult,
)

__all__ = [
    "ExpectedSuitesReport",
    "Finding",
    "PolicyReport",
    "Severity",
    "SuiteDisposition",
    "SuiteResult",
    "verify",
    "verify_expected_suites",
]


def verify(repository_root: str | Path, profile: str = "full") -> PolicyReport:
    """Verify one repository through the shared policy implementation."""

    return run_verification(Path(repository_root).resolve(), profile)


def verify_expected_suites(
    repository_root: str | Path, *, execute: bool = False
) -> ExpectedSuitesReport:
    """Verify the versioned manifest that defines current and deferred test scope."""

    return _verify_expected_suites(Path(repository_root).resolve(), execute=execute)
