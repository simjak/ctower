"""Deterministic, read-only CLI for private-VPS packet verification."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, cast

from tools.private_vps.evidence import verify_evidence
from tools.private_vps.manifest import PacketError
from tools.private_vps.models import Claim, OperationResult, ResultIssue
from tools.private_vps.preflight import validate_deployment

__all__ = ["main"]

Operation = Literal["validate", "evidence-verify"]


def main(argv: Sequence[str] | None = None) -> int:
    """Run one non-mutating operation and emit one secret-free JSON result."""
    arguments = _parser().parse_args(argv)
    operation = cast("Operation", arguments.operation)
    try:
        if operation == "validate":
            validate_deployment(
                arguments.bindings,
                arguments.source_sha,
                arguments.source_tree,
            )
            result = _result(operation="validate")
        else:
            claim = cast("Claim", arguments.claim)
            summary = verify_evidence(arguments.manifest, claim)
            result = _result(
                operation="evidence-verify",
                claim=claim,
                artifact_count=summary.artifact_count,
                working_days=summary.qualifying_working_days,
            )
    except PacketError as error:
        result = _result(
            operation=operation,
            ok=False,
            code=error.code,
            claim=getattr(arguments, "claim", None),
            issue=ResultIssue(code=error.code, field=error.field),
        )
    print(
        json.dumps(
            result.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if result.ok else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.private_vps")
    operations = parser.add_subparsers(dest="operation", required=True)
    validate = operations.add_parser("validate")
    validate.add_argument("--bindings", type=Path, required=True)
    validate.add_argument("--source-sha", required=True)
    validate.add_argument("--source-tree", required=True)
    evidence = operations.add_parser("evidence-verify")
    evidence.add_argument("--manifest", type=Path, required=True)
    evidence.add_argument(
        "--claim",
        choices=("development_rehearsal", "i1_exit"),
        required=True,
    )
    return parser


def _result(
    *,
    operation: Operation,
    ok: bool = True,
    code: str = "valid",
    claim: Claim | None = None,
    artifact_count: int = 0,
    working_days: int = 0,
    issue: ResultIssue | None = None,
) -> OperationResult:
    return OperationResult(
        schema="ctower.private-vps-result/v1",
        operation=operation,
        ok=ok,
        code=code,
        claim=claim,
        artifact_count=artifact_count,
        qualifying_working_days=working_days,
        issues=() if issue is None else (issue,),
    )
