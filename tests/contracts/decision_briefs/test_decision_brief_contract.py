"""Authored boundaries for Request-derived operator decision briefs."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()
EXPECTED_CHOICE_COUNT = 3


def test_decision_brief_is_a_strict_read_shape_with_no_caller_fact_input() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    brief = schemas["DecisionBrief"]
    row = schemas["RequestRow"]

    assert brief["additionalProperties"] is False
    assert set(cast(list[str], brief["required"])) == {
        "choices",
        "eli",
        "origin_quote",
        "recommendation",
        "rendered",
        "ruling_id",
        "safe_default",
        "status",
    }
    choices = cast(dict[str, object], cast(dict[str, object], brief["properties"])["choices"])
    assert choices["minItems"] == choices["maxItems"] == EXPECTED_CHOICE_COUNT
    assert "decision_brief" in cast(list[str], row["required"])
    module = ast.parse(
        (ROOT / "packages/ctower-kernel/src/ctower_kernel/work/_decision_brief.py").read_text(
            encoding="utf-8"
        )
    )
    builder = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "decision_brief"
    )
    assert tuple(argument.arg for argument in builder.args.kwonlyargs) == (
        "content",
        "reference",
        "triage",
        "ruling_id",
    )


def test_ruling_request_link_is_strict_typed_and_bidirectional() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    append = schemas["RulingAppendRequest"]
    result = schemas["RulingAppendResult"]
    row = schemas["RulingRow"]

    assert append["additionalProperties"] is False
    assert set(cast(dict[str, object], append["properties"])) == {
        "request_id",
        "supersedes_ruling_id",
        "verbatim",
    }
    assert "request_id" in cast(list[str], result["required"])
    assert {"request_id", "request_reference"} <= set(cast(list[str], row["required"]))


def test_request_ruling_relation_is_database_bound_and_successor_inherited() -> None:
    migration = (
        ROOT / "packages/ctower-kernel/migrations/0061_request_decision_briefs.sql"
    ).read_text(encoding="utf-8")

    assert "FOREIGN KEY (request_id, tenant_id, project_key)" in migration
    assert "REFERENCES requests(request_id, tenant_id, project_key)" in migration
    assert "CREATE UNIQUE INDEX rulings_one_root_per_request" in migration
    assert "CREATE TRIGGER rulings_request_chain_guard" in migration
    assert "NEW.request_id IS DISTINCT FROM predecessor_request_id" in migration
    assert "UPDATE rulings" not in migration
