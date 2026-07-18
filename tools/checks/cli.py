"""Command-line adapter for the Repository Policy Interface."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from tools.checks.interface import (
    ExpectedSuitesReport,
    PolicyReport,
    verify,
    verify_expected_suites,
)

_MANIFEST_PATH = "tools/checks/expected-suites.toml"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify ctower repository policy")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--profile", choices=("staged", "fast", "full"), default="full")
    parser.add_argument(
        "--expected-suites",
        action="store_true",
        help="also verify the current/deferred suite scope manifest",
    )
    parser.add_argument(
        "--execute-suites",
        action="store_true",
        help="execute current required commands after manifest validation",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _render_text(report: PolicyReport) -> str:
    lines = [
        f"repository-policy profile={report.profile} ok={str(report.ok).lower()} "
        f"files={report.scanned_files} errors={len(report.errors)} warnings={len(report.warnings)}"
    ]
    for item in report.findings:
        location = f"{item.path}:{item.line}" if item.line is not None else item.path
        exception = f" exception={item.exception_id}" if item.exception_id else ""
        lines.append(
            f"{item.severity.value.upper()} {item.rule_id} {location} {item.message}{exception}"
        )
    return "\n".join(lines)


def _render_suites(report: ExpectedSuitesReport) -> str:
    lines = [
        f"expected-suites schema={report.schema} version={report.manifest_version} "
        f"active_phase={report.active_phase} ok={str(report.ok).lower()}"
    ]
    lines.extend(
        f"ERROR suite.manifest {_MANIFEST_PATH} {error}" for error in report.manifest_errors
    )
    lines.extend(
        f"{item.disposition.value.upper()} {item.suite_id} owner={item.owner} "
        f"phase={item.phase} path={item.path} {item.message}"
        for item in report.suites
    )
    return "\n".join(lines)


def _selected_suites(args: argparse.Namespace) -> ExpectedSuitesReport | None:
    if not args.expected_suites and not args.execute_suites:
        return None
    return verify_expected_suites(args.root, execute=args.execute_suites)


def _print_reports(
    report: PolicyReport, suites: ExpectedSuitesReport | None, *, as_json: bool
) -> None:
    if as_json:
        payload: dict[str, object] = {"repository_policy": report.to_dict()}
        if suites is not None:
            payload["expected_suites"] = suites.to_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(_render_text(report))
    if suites is not None:
        print(_render_suites(suites))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI adapter and return a process-compatible exit code."""

    args = _parser().parse_args(argv)
    report = verify(args.root, args.profile)
    suites = _selected_suites(args)
    _print_reports(report, suites, as_json=args.as_json)
    return 0 if report.ok and (suites is None or suites.ok) else 1
