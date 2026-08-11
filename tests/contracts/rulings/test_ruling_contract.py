"""Authored boundaries for the append-only Agreements ledger."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()

_EXPECTED_PRINCIPALS = {
    "operator",
    "commander",
    "migration_importer",
    "fence_observer",
    "viewer",
}


def test_ruling_http_surface_is_strict_generated_and_has_no_claimed_identity() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    paths = cast(dict[str, dict[str, dict[str, object]]], document["paths"])
    append = paths["/v1/rulings"]["post"]
    listed = paths["/v1/rulings"]["get"]
    cited = paths["/v1/rulings/{ruling_id}"]["get"]
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    payload = schemas["RulingAppendRequest"]

    assert append["operationId"] == "appendRuling"
    assert append["x-ctower-cli"] == "ruling append"
    assert append["x-ctower-spool"] == "allowed"
    assert listed["operationId"] == "listRulings"
    assert cited["operationId"] == "getRuling"
    assert payload["additionalProperties"] is False
    assert payload["required"] == ["verbatim"]
    assert set(cast(dict[str, object], payload["properties"])) == {
        "request_id",
        "supersedes_ruling_id",
        "verbatim",
    }


def test_ruling_migration_uses_the_existing_principal_domain_and_trigger_idiom() -> None:
    migration = (ROOT / "packages/ctower-kernel/migrations/0060_rulings_ledger.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE rulings" in migration
    assert "CREATE TRIGGER rulings_immutable" in migration
    assert "BEFORE UPDATE OR DELETE ON rulings" in migration
    assert "EXECUTE FUNCTION refuse_immutable_control_fact_mutation()" in migration
    assert "REFERENCES project_seats(principal_id, tenant_id)" in migration
    assert "CREATE TABLE principals" not in migration
    assert "ALTER TABLE principals" not in migration
    assert _principal_values() == _EXPECTED_PRINCIPALS


def test_ruling_cso_trigger_records_no_new_boundary_and_no_new_principal() -> None:
    """The exact candidate reuses the one bearer/seat boundary and triggers no new CSO seam."""

    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemes = cast(dict[str, object], document["components"])["securitySchemes"]
    paths = cast(dict[str, dict[str, dict[str, object]]], document["paths"])
    decision = (ROOT / "DECISIONS.md").read_text(encoding="utf-8")

    assert cast(dict[str, object], schemes)["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "opaque",
    }
    assert paths["/v1/rulings"]["post"]["security"] == [{"bearerAuth": []}]
    assert "no-new-boundary" in decision[decision.index("## D49") :]
    assert _principal_values() == _EXPECTED_PRINCIPALS


def _principal_values() -> set[str]:
    source = ROOT / "packages/ctower-kernel/src/ctower_kernel/record/interface.py"
    module = ast.parse(source.read_text(encoding="utf-8"))
    principal = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "PrincipalKind"
    )
    return {
        statement.value.value
        for statement in principal.body
        if isinstance(statement, ast.Assign)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    }
