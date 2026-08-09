"""Reusable frozen outcome assertions for every first-party issue connector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ctower_kernel.integrations import (
    AmbiguousWrite,
    CloseExternalIssueResult,
    CloseFailure,
    ConnectorReceipt,
    ExternalIssuePage,
    FetchFailure,
    FetchIssuePageResult,
    WriteDisposition,
)

__all__ = [
    "CloseObservation",
    "ConnectorOutcomeFixture",
    "ReconciliationOutcome",
    "RetryObservation",
    "TransportReason",
    "run_outcome_conformance",
]

TransportReason = Literal["transport_connect", "transport_read", "transport_protocol"]
ReconciliationOutcome = Literal["found", "absent", "inconclusive"]
_MAX_ATTEMPTS = 4
_EXPECTED_SLEEPS = _MAX_ATTEMPTS - 1
_MAX_BACKOFF_SECONDS = 2.0
_MAX_ELAPSED_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class CloseObservation:
    result: CloseExternalIssueResult
    marker_reads: int
    marker_writes: int


@dataclass(frozen=True, slots=True)
class RetryObservation:
    result: FetchIssuePageResult
    invocations: int
    sleeps: tuple[float, ...]
    elapsed_seconds: float
    request_timeouts: tuple[float, ...] = ()


class ConnectorOutcomeFixture(Protocol):
    """Provider-owned transport scenarios consumed by unchanged shared assertions."""

    def fetch_status(self, status: int) -> FetchIssuePageResult: ...

    def close_status(self, status: int) -> CloseObservation: ...

    def fetch_transport(self, reason: TransportReason) -> FetchIssuePageResult: ...

    def close_transport(self, reason: TransportReason) -> CloseObservation: ...

    def ambiguous_write(self, outcome: ReconciliationOutcome) -> CloseObservation: ...

    def retry_sequence(self) -> RetryObservation: ...

    def retry_exhaustion(self) -> RetryObservation: ...

    def deadline_exhaustion(self) -> RetryObservation: ...


def run_outcome_conformance(fixture: ConnectorOutcomeFixture) -> None:
    """Assert the frozen classification, reconciliation, retry, and deadline matrix."""

    _assert_provider_statuses(fixture)
    _assert_transport_failures(fixture)
    _assert_ambiguous_writes(fixture)
    _assert_retry_bounds(fixture)


def _assert_provider_statuses(fixture: ConnectorOutcomeFixture) -> None:
    rows = (
        (401, "terminal", "authentication", "not_written", 1),
        (403, "terminal", "authorization", "not_written", 1),
        (400, "terminal", "ordinary_4xx", "not_written", 1),
        (429, "retryable", "throttled", "reconciled_absent", 2),
        (503, "retryable", "provider_5xx", "reconciled_absent", 2),
    )
    for status, retry_class, reason, disposition, reads in rows:
        fetch = fixture.fetch_status(status)
        close = fixture.close_status(status)
        assert isinstance(fetch, FetchFailure)
        assert (fetch.retry_class, fetch.reason) == (retry_class, reason)
        assert isinstance(close.result, CloseFailure)
        assert (close.result.retry_class, close.result.reason) == (retry_class, reason)
        assert close.result.write_disposition == disposition
        assert (close.marker_reads, close.marker_writes) == (reads, 1)


def _assert_transport_failures(fixture: ConnectorOutcomeFixture) -> None:
    rows: tuple[tuple[TransportReason, WriteDisposition, int], ...] = (
        ("transport_connect", "not_written", 1),
        ("transport_read", "reconciled_absent", 2),
        ("transport_protocol", "reconciled_absent", 2),
    )
    for reason, disposition, reads in rows:
        fetch = fixture.fetch_transport(reason)
        close = fixture.close_transport(reason)
        assert fetch == FetchFailure(retry_class="retryable", reason=reason)
        assert close.result == CloseFailure(
            retry_class="retryable",
            reason=reason,
            write_disposition=disposition,
        )
        assert (close.marker_reads, close.marker_writes) == (reads, 1)


def _assert_ambiguous_writes(fixture: ConnectorOutcomeFixture) -> None:
    found = fixture.ambiguous_write("found")
    absent = fixture.ambiguous_write("absent")
    inconclusive = fixture.ambiguous_write("inconclusive")
    assert isinstance(found.result, ConnectorReceipt)
    assert found.result.marker_present and found.result.issue_closed
    assert absent.result == CloseFailure(
        retry_class="retryable",
        reason="transport_read",
        write_disposition="reconciled_absent",
    )
    assert inconclusive.result == AmbiguousWrite()
    assert (found.marker_reads, found.marker_writes) == (2, 1)
    assert (absent.marker_reads, absent.marker_writes) == (2, 1)
    assert (inconclusive.marker_reads, inconclusive.marker_writes) == (2, 1)


def _assert_retry_bounds(fixture: ConnectorOutcomeFixture) -> None:
    success = fixture.retry_sequence()
    exhausted = fixture.retry_exhaustion()
    deadline = fixture.deadline_exhaustion()
    assert isinstance(success.result, ExternalIssuePage)
    assert success.invocations == _MAX_ATTEMPTS
    assert len(success.sleeps) == _EXPECTED_SLEEPS
    assert success.sleeps == tuple(sorted(success.sleeps))
    assert max(success.sleeps) <= _MAX_BACKOFF_SECONDS
    assert success.elapsed_seconds <= _MAX_ELAPSED_SECONDS
    assert exhausted.result == FetchFailure(retry_class="retryable", reason="provider_5xx")
    assert exhausted.invocations == _MAX_ATTEMPTS
    assert len(exhausted.sleeps) == _EXPECTED_SLEEPS
    assert max(exhausted.sleeps) <= _MAX_BACKOFF_SECONDS
    assert exhausted.elapsed_seconds <= _MAX_ELAPSED_SECONDS
    assert deadline.result == FetchFailure(retry_class="retryable", reason="timeout")
    assert deadline.invocations <= _MAX_ATTEMPTS
    assert deadline.elapsed_seconds <= _MAX_ELAPSED_SECONDS
    assert deadline.request_timeouts
    assert all(timeout <= _MAX_ELAPSED_SECONDS for timeout in deadline.request_timeouts)
