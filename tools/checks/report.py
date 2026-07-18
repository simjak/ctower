"""Typed report values exposed by the Repository Policy Interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Merge significance of one policy finding."""

    WARNING = "warning"
    ERROR = "error"


class SuiteDisposition(StrEnum):
    """Observed state of one expected verification suite."""

    REQUIRED = "required"
    PASSED = "passed"
    NOT_YET_REQUIRED = "not_yet_required"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Finding:
    """One typed, attributable repository-policy result."""

    rule_id: str
    path: str
    message: str
    severity: Severity
    line: int | None = None
    observed: int | None = None
    limit: int | None = None
    exception_id: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyReport:
    """Complete deterministic report returned by the Module."""

    profile: str
    scanned_files: int
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity is Severity.ERROR for item in self.findings)

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.severity is Severity.WARNING)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "ok": self.ok,
            "scanned_files": self.scanned_files,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "findings": [
                {
                    "rule_id": item.rule_id,
                    "path": item.path,
                    "message": item.message,
                    "severity": item.severity.value,
                    "line": item.line,
                    "observed": item.observed,
                    "limit": item.limit,
                    "exception_id": item.exception_id,
                }
                for item in self.findings
            ],
        }


@dataclass(frozen=True, slots=True)
class SuiteResult:
    """One manifest suite after fail-closed structural verification."""

    suite_id: str
    owner: str
    phase: str
    path: str
    command: tuple[str, ...]
    timeout_seconds: int
    disposition: SuiteDisposition
    message: str


@dataclass(frozen=True, slots=True)
class ExpectedSuitesReport:
    """Typed result for the repository's current verification scope."""

    schema: str
    manifest_version: int
    active_phase: str
    suites: tuple[SuiteResult, ...]
    manifest_errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.manifest_errors and not any(
            item.disposition is SuiteDisposition.FAILED for item in self.suites
        )

    @property
    def failures(self) -> tuple[SuiteResult, ...]:
        return tuple(item for item in self.suites if item.disposition is SuiteDisposition.FAILED)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "manifest_version": self.manifest_version,
            "active_phase": self.active_phase,
            "ok": self.ok,
            "manifest_errors": list(self.manifest_errors),
            "suites": [
                {
                    "id": item.suite_id,
                    "owner": item.owner,
                    "phase": item.phase,
                    "path": item.path,
                    "command": list(item.command),
                    "timeout_seconds": item.timeout_seconds,
                    "disposition": item.disposition.value,
                    "message": item.message,
                }
                for item in self.suites
            ],
        }
