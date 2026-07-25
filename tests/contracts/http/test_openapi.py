"""Minimum public HTTP and RFC 9457 contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]

_EXPECTED_OPERATION_METADATA: dict[str, tuple[object, bool, str]] = {
    "addTicketComment": ("ticket comment add", True, "allowed"),
    "addTicketRelation": ("ticket relation add", True, "allowed"),
    "applyCompanyBundle": ("company bundle apply", True, "allowed"),
    "applyTicketIntent": (
        ["ticket admit", "ticket defer", "ticket block", "ticket unblock", "ticket reopen"],
        True,
        "allowed",
    ),
    "bootstrapFirstTenant": ("bootstrap first-tenant", True, "forbidden"),
    "changeTicketAssignment": ("ticket assign", True, "allowed"),
    "changeTicketPriority": ("ticket prioritize", True, "allowed"),
    "createTicket": (["ticket capture", "ticket create"], True, "allowed"),
    "exportCompanyBundle": ("company bundle export", False, "forbidden"),
    "freezeProofCriteria": ("ticket criteria freeze", True, "allowed"),
    "getBoard": ("board query", False, "forbidden"),
    "getControlHealth": ("control health", False, "forbidden"),
    "getTicket": (["ticket query", "ticket show"], False, "forbidden"),
    "getTicketTimeline": ("ticket timeline", False, "forbidden"),
    "listTicketAssignments": ("ticket assignments", False, "forbidden"),
    "listTicketAuditEvents": ("ticket audit", False, "forbidden"),
    "planCompanyBundle": ("company bundle plan", False, "forbidden"),
    "recordOutboxPoisonDisposition": ("ops outbox poison dispose", True, "allowed"),
    "recordProofEvidence": ("ticket evidence add", True, "allowed"),
    "recordProofVerdict": ("ticket gate verdict", True, "allowed"),
    "resolveCloseWorkflow": ("ticket resolve", True, "allowed"),
    "startTicketWorkflow": ("ticket workflow start", True, "allowed"),
    "transferTicketCustody": ("ticket custody transfer", True, "allowed"),
    "transitionWorkflow": ("ticket transition", True, "allowed"),
    "validateCompanyBundle": ("company bundle validate", False, "forbidden"),
}
_EXPECTED_PROBLEM_CODES = {
    "bootstrap-consumed",
    "bootstrap-expired",
    "bootstrap-nonempty",
    "bootstrap-origin",
    "bundle-base-conflict",
    "bundle-compatibility-refused",
    "bundle-digest-mismatch",
    "bundle-grant-refused",
    "bundle-independence-refused",
    "bundle-no-effect-refused",
    "bundle-not-active",
    "bundle-plan-mismatch",
    "bundle-recovery-unavailable",
    "bundle-reference-invalid",
    "bundle-schema-invalid",
    "bundle-security-refused",
    "durability_pending",
    "idempotency-conflict",
    "poison-not-found",
    "proof-candidate-author-mismatch",
    "proof-candidate-digest-invalid",
    "proof-candidate-digest-not-current",
    "proof-candidate-unchanged",
    "proof-criteria-already-frozen",
    "proof-criteria-invalid",
    "proof-criteria-policy-mismatch",
    "proof-criterion-unknown",
    "proof-current-evidence-missing",
    "proof-evidence-digest-mismatch",
    "proof-evidence-id-conflict",
    "proof-incomplete",
    "proof-policy-mismatch",
    "proof-policy-pin-mismatch",
    "proof-protected-authority-required",
    "proof-self-review-refused",
    "proof-verdict-id-conflict",
    "tenant-scope-denied",
    "ticket-comment-ineligible",
    "ticket-comment-invalid",
    "unauthorized",
    "validation-error",
    "version-conflict",
    "work-assignment-kind-refused",
    "work-assignment-target-ineligible",
    "work-assignment-unchanged",
    "work-blocker-already-resolved",
    "work-blocker-id-conflict",
    "work-blocker-owner-ineligible",
    "work-blocker-unknown",
    "work-intent-unmet",
    "work-priority-unchanged",
    "work-relation-cycle",
    "work-relation-exists",
    "work-reopen-unmet",
    "work-ticket-terminal",
    "workflow-already-started",
    "workflow-not-terminal",
    "workflow-pin-mismatch",
    "workflow-predicate-unsatisfied",
    "workflow-run-not-started",
    "workflow-state-conflict",
    "workflow-terminal",
    "workflow-transition-not-declared",
    "workflow-version-unknown",
}


def test_openapi_exposes_exact_i1_operations_and_generated_routing_metadata() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    paths = cast(dict[str, dict[str, dict[str, object]]], document["paths"])
    operations = {
        cast(str, operation["operationId"]): (
            operation.get("x-ctower-cli"),
            operation.get("x-ctower-mutation"),
            operation.get("x-ctower-spool"),
        )
        for path in paths.values()
        for method, operation in path.items()
        if method in {"get", "post"}
    }

    assert document["openapi"] == "3.1.0"
    assert operations == _EXPECTED_OPERATION_METADATA
    assert all(set(path) <= {"get", "post"} for path in paths.values())
    assert set(paths["/v1/board"]) == {"get"}
    assert all("status" not in path.casefold() for path in paths)
    assert {
        operation_id
        for operation_id, (_, is_mutation, spool_policy) in operations.items()
        if is_mutation and spool_policy == "forbidden"
    } == {"bootstrapFirstTenant"}


def test_problem_vocabulary_and_boundary_objects_are_strict() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    problem_properties = cast(dict[str, object], schemas["Problem"]["properties"])
    code_schema = cast(dict[str, object], problem_properties["code"])
    problem_codes = set(cast(list[str], code_schema["enum"]))

    assert problem_codes == _EXPECTED_PROBLEM_CODES
    for name, schema in schemas.items():
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False, name
