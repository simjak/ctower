"""Command-line adapter for the record-backed landing-boundary check.

The change identity comes from the checkout, never from a branch name, a title, or a
body, and the facts come from the record's own answer.  An absent, unreadable, or
malformed answer is reported as a refusal and exits nonzero: unknown is a failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from tools.landing_boundary import (
    DEFAULT_POLICY_PATH,
    ChangeIdentity,
    LandingBoundaryError,
    LandingBoundaryReport,
    VerdictTierPolicy,
    evaluate_landing_boundary,
    load_verdict_tier_policy,
    read_record_snapshot,
    refused_report,
    render_report,
)

__all__ = ["main"]

_USAGE_EXIT = 2


def main(argv: tuple[str, ...] | None = None) -> int:
    """Report every landing-boundary fact and exit nonzero unless all of them pass."""

    arguments = _parse_arguments(argv)
    try:
        change = ChangeIdentity(
            repository=arguments.repository,
            pull_request_reference=arguments.pull_request,
            head_revision=arguments.head_revision,
        )
        policy = load_verdict_tier_policy(arguments.policy)
    except (LandingBoundaryError, ValidationError) as error:
        sys.stderr.write(f"landing boundary: {_bounded(error)}\n")
        return _USAGE_EXIT
    report = _evaluate(arguments.record, change, policy)
    _emit(report, json_output=arguments.json)
    return 0 if report.verdict == "pass" else 1


def _evaluate(
    record: Path | None, change: ChangeIdentity, policy: VerdictTierPolicy
) -> LandingBoundaryReport:
    if record is None:
        return refused_report(change, "record-unavailable", "no record answer was supplied")
    try:
        snapshot = read_record_snapshot(record)
    except LandingBoundaryError as error:
        return refused_report(change, "record-payload-invalid", _bounded(error))
    return evaluate_landing_boundary(snapshot, change, policy)


def _emit(report: LandingBoundaryReport, *, json_output: bool) -> None:
    body = (
        report.model_dump_json(indent=2, by_alias=True) + "\n"
        if json_output
        else render_report(report)
    )
    sys.stdout.write(body)


def _parse_arguments(argv: tuple[str, ...] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tools.landing_boundary",
        description="Report the record-backed landing-boundary facts for one change",
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-request", required=True)
    parser.add_argument("--head-revision", required=True)
    parser.add_argument("--record", type=_optional_path, default=None)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def _optional_path(value: str) -> Path | None:
    return Path(value) if value else None


def _bounded(value: object) -> str:
    return " ".join(str(value).split())[:1000]
