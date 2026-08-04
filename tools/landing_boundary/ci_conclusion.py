"""The GitHub check-run conclusion this repository's CI renders for one report.

`tools.landing_boundary.cli` is unchanged: its exit-code contract (0 only when every
fact passes, 1 on any refusal) still governs every manual and local invocation, and the
reader still refuses `record-unavailable` exactly as before -- unknown is still a
failure, never calm.  What is not yet true on this repository is that a *reachable*
record answer exists in CI: `CTOWER_LANDING_BOUNDARY_RECORD` has nothing to point at, so
every pull request refuses the same way regardless of what it changed, and a check that
is always red trains everyone to stop reading it -- burying the reds that are real.

This module renders that one case honestly instead of red.  A refusal whose only named
cause is `record-unavailable` means the record was never consulted at all, so this CI
renders `neutral`, with the refusal still named in the check's own summary.  A refusal
the record itself answered -- any refusal beyond the record being unreachable -- still
renders `failure`: observe mode changes how absence is rendered, never what a real
answer means.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

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

__all__ = [
    "CheckConclusion",
    "CheckRunPayload",
    "check_run_payload",
    "conclusion_for",
    "main",
    "summary_for",
]

_USAGE_EXIT = 2

CheckConclusion = Literal["success", "neutral", "failure"]

_OBSERVE_MODE_ONLY_REFUSAL: tuple[str, ...] = ("record-unavailable",)
_TITLES: dict[CheckConclusion, str] = {
    "success": "landing boundary: every fact passes",
    "neutral": "landing boundary: record surface unreachable here (observe mode)",
    "failure": "landing boundary: refused",
}
_OBSERVE_MODE_NOTE = (
    "\nobserve mode: CTOWER_LANDING_BOUNDARY_RECORD has no answer to read in this "
    "environment, so this change was never evaluated against the record. This is not a "
    "pass -- it is a named, visible absence, and a real refusal from a reachable record "
    "still renders FAILURE.\n"
)


class CheckRunOutput(BaseModel):
    """The title/summary text the Checks API renders for one published conclusion."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    title: str
    summary: str


class CheckRunPayload(BaseModel):
    """The Checks API creation payload CI publishes for one report."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str
    head_sha: str
    status: Literal["completed"]
    conclusion: CheckConclusion
    output: CheckRunOutput


def conclusion_for(report: LandingBoundaryReport) -> CheckConclusion:
    """Render one report's GitHub check conclusion.

    A refusal named only ``record-unavailable`` means the record had nothing to answer
    with, so it renders ``neutral``. Every other refusal is an answer the record itself
    gave, and still renders ``failure``.
    """

    if report.verdict == "pass":
        return "success"
    if report.refusals == _OBSERVE_MODE_ONLY_REFUSAL:
        return "neutral"
    return "failure"


def summary_for(report: LandingBoundaryReport, conclusion: CheckConclusion) -> str:
    """Render the check-run summary body: the full report, refusal names included."""

    body = render_report(report)
    return body if conclusion != "neutral" else body + _OBSERVE_MODE_NOTE


def check_run_payload(
    report: LandingBoundaryReport, *, name: str, head_sha: str
) -> CheckRunPayload:
    """Build the Checks API creation payload CI publishes for one report."""

    conclusion = conclusion_for(report)
    return CheckRunPayload(
        name=name,
        head_sha=head_sha,
        status="completed",
        conclusion=conclusion,
        output=CheckRunOutput(title=_TITLES[conclusion], summary=summary_for(report, conclusion)),
    )


def main(argv: tuple[str, ...] | None = None) -> int:
    """Evaluate the record answer and write the check-run payload CI publishes."""

    arguments = _parse_arguments(argv)
    try:
        change = ChangeIdentity(
            repository=arguments.repository,
            pull_request_reference=arguments.pull_request,
            head_revision=arguments.head_revision,
        )
        policy = load_verdict_tier_policy(arguments.policy)
    except (LandingBoundaryError, ValidationError) as error:
        sys.stderr.write(f"landing boundary ci-conclusion: {_bounded(error)}\n")
        return _USAGE_EXIT
    report = _evaluate(arguments.record, change, policy)
    payload = check_run_payload(report, name=arguments.name, head_sha=arguments.head_revision)
    arguments.output.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(payload.output.summary)
    return 0


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


def _parse_arguments(argv: tuple[str, ...] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tools.landing_boundary.ci_conclusion",
        description="Render the GitHub check-run conclusion CI publishes for one change",
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-request", required=True)
    parser.add_argument("--head-revision", required=True)
    parser.add_argument("--record", type=_optional_path, default=None)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(list(argv) if argv is not None else None)


def _optional_path(value: str) -> Path | None:
    return Path(value) if value else None


def _bounded(value: object) -> str:
    return " ".join(str(value).split())[:1000]


if __name__ == "__main__":
    raise SystemExit(main())
