"""Minimum public HTTP and RFC 9457 contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]


def test_openapi_exposes_exact_walking_slice_operations_and_cli_mappings() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    paths = cast(dict[str, dict[str, dict[str, object]]], document["paths"])
    operations = {
        operation["operationId"]: operation["x-ctower-cli"]
        for path in paths.values()
        for method, operation in path.items()
        if method in {"get", "post"}
    }

    assert document["openapi"] == "3.1.0"
    assert operations == {
        "bootstrapFirstTenant": "bootstrap first-tenant",
        "createTicket": "ticket create",
        "getTicket": "ticket show",
        "getTicketTimeline": "ticket timeline",
        "transferTicketCustody": "ticket assign",
    }


def test_problem_vocabulary_and_boundary_objects_are_strict() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    problem_properties = cast(dict[str, object], schemas["Problem"]["properties"])
    code_schema = cast(dict[str, object], problem_properties["code"])
    problem_codes = set(cast(list[str], code_schema["enum"]))

    assert problem_codes == {
        "bootstrap-consumed",
        "bootstrap-expired",
        "bootstrap-origin",
        "idempotency-conflict",
        "tenant-scope-denied",
        "unauthorized",
        "version-conflict",
    }
    for name, schema in schemas.items():
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False, name
