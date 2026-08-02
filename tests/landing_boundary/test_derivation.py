"""The check carries no stage-key branch, so a renamed stage needs no check edit."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from tools.landing_boundary import (
    ChangeIdentity,
    LandingBoundaryReport,
    RecordSnapshot,
    evaluate_landing_boundary,
    load_verdict_tier_policy,
)

from . import support

__all__: tuple[str, ...] = ()

_MODULE_ROOT = Path(__file__).parents[2] / "tools" / "landing_boundary"
_FORBIDDEN_KEYS = (*support.SOFTWARE_FACTORY_STAGES, "capture", "frame", "verify", "close")


def _report(answer: dict[str, Any]) -> LandingBoundaryReport:
    return evaluate_landing_boundary(
        RecordSnapshot.model_validate_json(json.dumps(answer)),
        ChangeIdentity(**support.CHANGE),
        load_verdict_tier_policy(),
    )


def _executable_strings(source: str) -> list[str]:
    tree = ast.parse(source)
    documented = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in documented
    ]


@pytest.mark.parametrize("path", sorted(_MODULE_ROOT.glob("*.py")), ids=lambda path: path.name)
def test_no_module_of_the_check_names_a_stage_key(path: Path) -> None:
    literals = _executable_strings(path.read_text(encoding="utf-8"))

    assert [literal for literal in literals if any(key in literal for key in _FORBIDDEN_KEYS)] == []


def test_renaming_every_stage_renames_every_refusal_with_no_check_edit() -> None:
    renamed = tuple(f"phase-{index}" for index in range(5))
    answer = support.replace_slot(
        support.record_answer(stage_keys=renamed, landing_boundary_stage="phase-4"),
        "phase-2",
        "artifact",
        state="unfilled",
    )

    report = _report(answer)

    assert [fact.stage_key for fact in report.facts] == ["phase-0", "phase-1", "phase-2", "phase-3"]
    assert report.refusals == ("missing-phase-2-evidence",)


def test_a_non_engineering_pinned_workflow_reports_its_own_set() -> None:
    stages = ("capture", "frame", "verify", "close")
    answer = support.replace_slot(
        support.record_answer(stage_keys=stages, landing_boundary_stage="close"),
        "verify",
        "artifact",
        state="unfilled",
    )

    report = _report(answer)

    assert [fact.stage_key for fact in report.facts] == ["capture", "frame", "verify"]
    assert report.refusals == ("missing-verify-evidence",)


def test_the_reported_set_follows_the_pinned_graph_not_the_recorded_stage_list() -> None:
    answer = support.record_answer(stage_keys=("intake", "think", "merge"))
    answer["stages"].append(
        {"stage_key": "unrelated", "resolution": "resolved", "required_slots": []}
    )

    report = _report(answer)

    assert [fact.stage_key for fact in report.facts] == ["intake", "think"]
