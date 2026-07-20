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
        cast(str, operation["operationId"]): operation.get("x-ctower-cli")
        for path in paths.values()
        for method, operation in path.items()
        if method in {"get", "post"}
    }

    assert document["openapi"] == "3.1.0"
    assert set(operations) == {
        "bootstrapFirstTenant",
        "createTicket",
        "freezeProofCriteria",
        "getTicket",
        "getTicketTimeline",
        "recordProofEvidence",
        "recordProofVerdict",
        "resolveCloseWorkflow",
        "transferTicketCustody",
        "transitionWorkflow",
    }
    assert {key: value for key, value in operations.items() if value is not None} == {
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
        "bootstrap-nonempty",
        "bootstrap-origin",
        "idempotency-conflict",
        "proof-candidate-author-mismatch",
        "proof-candidate-digest-invalid",
        "proof-candidate-digest-not-current",
        "proof-candidate-unchanged",
        "proof-criteria-already-frozen",
        "proof-criteria-invalid",
        "proof-criterion-unknown",
        "proof-current-evidence-missing",
        "proof-evidence-digest-mismatch",
        "proof-evidence-id-conflict",
        "proof-incomplete",
        "proof-protected-authority-required",
        "proof-self-review-refused",
        "proof-verdict-id-conflict",
        "tenant-scope-denied",
        "unauthorized",
        "validation-error",
        "version-conflict",
        "workflow-not-terminal",
        "workflow-predicate-unsatisfied",
        "workflow-state-conflict",
        "workflow-terminal",
        "workflow-transition-not-declared",
        "workflow-version-unknown",
    }
    for name, schema in schemas.items():
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False, name
