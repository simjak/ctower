from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

from ._ast_support import function_definitions
from ._beat_inventory import BEAT_PROBLEM_CODES
from ._operation_inventory import _EXPECTED_OPERATION_METADATA
from ._request_proposal_inventory import (
    REQUEST_PROPOSAL_PROBLEM_CODES,
)
from ._ruling_inventory import RULING_PROBLEM_CODES

ROOT, MAX_IMPORT_ITEMS = Path(__file__).parents[3], 64

_EXPECTED_PROBLEM_CODES = {
    "attention-finding-already-disposed",
    "attention-finding-not-found",
    "attention-kind-unrecognized",
    "auth-csrf-invalid",
    "auth-exchange-invalid",
    "auth-identity-unresolved",
    "auth-provider-unavailable",
    "auth-provider-unverifiable",
    "auth-role-denied",
    "auth-session-invalid",
    *BEAT_PROBLEM_CODES,
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
    "change-reference-duplicate",
    "credential-already-revoked",
    "credential-authentication-unavailable",
    "credential-digest-conflict",
    "credential-issuance-refused",
    "credential-revocation-refused",
    "credential-revoked",
    "credential-scope-denied",
    "console-actor-suspended",
    "console-adapter-malformed",
    "console-adapter-unregistered",
    "console-allowlist-refused",
    "console-assignment-stale",
    "console-backend-fenced",
    "console-backend-unavailable",
    "console-browser-session-required",
    "console-continuous-view-limit",
    "console-csrf-invalid",
    "console-cursor-invalid",
    "console-globally-disabled",
    "console-grant-expired",
    "console-grant-unavailable",
    "console-incarnation-fenced",
    "console-kill-switch-refused",
    "console-loop-kind-refused",
    "console-origin-refused",
    "console-output-unavailable",
    "console-project-fence-mismatch",
    "console-project-refused",
    "console-renewal-binding-mismatch",
    "console-renewal-unavailable",
    "console-revocation-refused",
    "console-role-refused",
    "console-runner-epoch-fenced",
    "console-runner-fenced",
    "console-runtime-attempt-fenced",
    "console-sensitivity-refused",
    "console-session-already-allowed",
    "console-session-already-revoked",
    "console-session-join-stale",
    "console-session-not-allowed",
    "console-session-revoked",
    "console-session-unavailable",
    "console-stream-already-open",
    "console-stream-query-refused",
    "dream-dispatch-already-consumed",
    "dream-dispatch-family-excluded",
    "dream-dispatch-lane-unbound",
    "dream-dispatch-model-requirement-mismatch",
    "dream-dispatch-tier-refused",
    "dream-dispatch-unavailable",
    "dream-lane-already-bound",
    "dream-lane-binding-operator-required",
    "durability_pending",
    "estate-import-batch-digest-mismatch",
    "estate-import-batch-invalid",
    "estate-import-content-mismatch",
    "estate-import-count-mismatch",
    "estate-import-duplicate-source",
    "estate-import-invalid",
    "estate-import-operator-required",
    "estate-import-parity-signer-unavailable",
    "estate-import-project-required",
    "estate-import-row-invalid",
    "estate-import-source-conflict",
    "i1-7c-required",
    "idempotency-conflict",
    "invalid-request",
    "intake-already-promoted",
    "intake-promotion-ineligible",
    "intake-source-project-mismatch",
    "intake-source-conflict",
    "knowledge-invalid-project",
    "knowledge-invalid-scope",
    "knowledge-source-not-found",
    "knowledge-source-unavailable",
    "inbox-already-promoted",
    "inbox-acknowledgement-not-advancing",
    "inbox-message-recipient-mismatch",
    "inbox-recipient-ambiguous",
    "inbox-recipient-not-found",
    "inbox-recipient-self",
    "inbox-sender-unaddressable",
    "inbox-thread-head-invalid",
    "inbox-thread-participant-mismatch",
    "label-already-applied",
    "label-key-unrecognized",
    "migration-alias-conflict",
    "migration-capability-denied",
    "migration-correction-conflict",
    "migration-digest-mismatch",
    "migration-export-nondeterminism",
    "migration-fence-detected",
    "migration-import-finalization-refused",
    "migration-operation-drift",
    "migration-relation-invalid",
    "migration-run-conflict",
    "migration-signature-invalid",
    "migration-source-selection-drift",
    "migration-source-tainted",
    "poison-not-found",
    *REQUEST_PROPOSAL_PROBLEM_CODES,
    "prohibited-data-class",
    "project-delivery-unavailable",
    "project-grant-required",
    "project-scope-denied",
    "request-capture-forbidden",
    "request-import-forbidden",
    "request-owner-forbidden",
    "request-project-unavailable",
    "request-source-forbidden",
    "request-transition-forbidden",
    "request-triage-forbidden",
    *RULING_PROBLEM_CODES,
    "reauthentication-required",
    "request-body-too-large",
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
    "review-dispatch-already-consumed",
    "review-dispatch-family-conflict",
    "review-dispatch-incomplete",
    "review-dispatch-input-missing",
    "review-dispatch-model-unbound",
    "review-dispatch-self-review",
    "review-dispatch-unavailable",
    "seat-binding-conflict",
    "seat-credential-active",
    "seat-credential-unavailable",
    "seat-display-name-conflict",
    "session-ineligible",
    "session-not-found",
    "session-transition-invalid",
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
            operation.get("x-ctower-principal"),
            operation.get("x-ctower-refusal-only", False),
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
        for operation_id, (_, is_mutation, spool_policy, _, _) in operations.items()
        if is_mutation and spool_policy == "forbidden"
    } == {
        "appendCtowerProjectImportCorrection",
        "allowConsoleSession",
        "applyCtowerProjectImportBatch",
        "bindCtowerProjectAliasPlan",
        "bindCtowerProjectExportEquality",
        "bindDreamLane",
        "bootstrapFirstTenant",
        "createCtowerProjectImportRun",
        "finalizeCtowerProjectImportRun",
        "importEstateCompanyRecords",
        "importEstateInbox",
        "importEstateKnowledge",
        "importEstateRulings",
        "issueSeatCredential",
        "mintConsoleViewGrant",
        "renewConsoleViewGrant",
        "reportCtowerProjectFenceObservation",
        "retireBeatRoutine",
        "revokeSeatCredential",
        "revokeConsoleSession",
        "setConsoleKillSwitch",
        "streamConsoleEvents",
    }


def test_project_and_credential_refusals_have_one_definition_each() -> None:
    kernel = ROOT / "packages/ctower-kernel/src/ctower_kernel"

    assert function_definitions(kernel, "project_mutation_refusal") == {"record/transaction.py"}
    assert function_definitions(kernel, "credential_scope_refusal") == {"record/interface.py"}


def test_http_authentication_requires_scope_or_the_named_opt_out() -> None:
    api = ROOT / "apps/ctower-api/src/ctower_api"
    support = ast.parse((api / "_http_support.py").read_text(encoding="utf-8"))
    authenticate = next(
        node
        for node in support.body
        if isinstance(node, ast.FunctionDef) and node.name == "authenticate"
    )
    scope_index = next(
        index
        for index, argument in enumerate(authenticate.args.kwonlyargs)
        if argument.arg == "required_scope"
    )
    assert authenticate.args.kw_defaults[scope_index] is None
    assert any(
        isinstance(node, ast.ClassDef) and node.name == "UnscopedAuthentication"
        for node in support.body
    )

    calls: list[tuple[str, int]] = []
    for path in sorted(api.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"authenticate", "_authenticate"}
            ):
                continue
            calls.append((path.name, node.lineno))
            assert any(keyword.arg == "required_scope" for keyword in node.keywords), (
                path.name,
                node.lineno,
            )
    assert calls


def test_problem_vocabulary_is_exact() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    problem_properties = cast(dict[str, object], schemas["Problem"]["properties"])
    code_schema = cast(dict[str, object], problem_properties["code"])
    problem_codes = set(cast(list[str], code_schema["enum"]))

    assert problem_codes == _EXPECTED_PROBLEM_CODES


def test_ticket_timeline_contract_includes_workflow_change_payloads() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    timeline = schemas["TimelineEvent"]
    properties = cast(dict[str, object], timeline["properties"])
    kind = cast(dict[str, object], properties["kind"])
    payload = cast(dict[str, object], properties["payload"])

    assert kind["enum"] == [
        "ticket.created",
        "ticket.custody_transferred",
        "ticket.comment_added",
        "workflow.changed",
    ]
    assert [
        item["$ref"].rsplit("/", 1)[-1] for item in cast(list[dict[str, str]], payload["oneOf"])
    ] == [
        "TicketCreatedPayload",
        "CustodyTransferredPayload",
        "TicketCommentAddedPayload",
        "WorkflowChangedAuditPayload",
    ]


def test_i1_7b_reuses_paths_adds_only_planned_paths_and_refuses_i1_7c() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    paths = cast(dict[str, dict[str, dict[str, object]]], document["paths"])
    migration_paths = {
        path: set(value) for path, value in paths.items() if "ctower-project" in path
    }

    assert migration_paths == {
        "/v1/migrations/ctower-project/inventory": {"post"},
        "/v1/migrations/ctower-project/export": {"post"},
        "/v1/migrations/ctower-project/plan": {"post"},
        "/v1/migrations/ctower-project/import": {"post"},
        "/v1/migrations/ctower-project/reconcile": {"post"},
        "/v1/migrations/ctower-project/import-runs/{run_id}": {"get"},
        "/v1/migrations/ctower-project/corrections": {"post"},
        "/v1/migrations/ctower-project/fence-observations": {"post"},
        "/v1/migrations/ctower-project/prepare": {"post"},
        "/v1/migrations/ctower-project/commit-development-epoch": {"post"},
        "/v1/migrations/ctower-project/cutover-health": {"get"},
    }
    import_operation = paths["/v1/migrations/ctower-project/import"]["post"]
    assert import_operation["x-ctower-max-canonical-bytes"] == 256 * 1024
    for path in (
        "/v1/migrations/ctower-project/prepare",
        "/v1/migrations/ctower-project/commit-development-epoch",
    ):
        operation = paths[path]["post"]
        assert operation["x-ctower-refusal-only"] is True
        assert operation["x-ctower-mutation"] is False
        responses = cast(dict[str, object], operation["responses"])
        assert not any(status.startswith("2") for status in responses)
        assert "409" in responses


def test_import_union_and_generated_boundaries_exclude_privileged_fields() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    union = cast(list[dict[str, str]], schemas["CtowerProjectImportOperation"]["oneOf"])

    assert [item["$ref"].rsplit("/", 1)[-1] for item in union] == [
        "CtowerProjectTicketSeedOperation",
        "CtowerProjectExactAliasOperation",
        "CtowerProjectTicketRelationOperation",
        "CtowerProjectSourceLinkOperation",
    ]
    encoded = json.dumps(
        {
            name: schemas[name]
            for name in (
                "CtowerProjectTicketSeedOperation",
                "CtowerProjectExactAliasOperation",
                "CtowerProjectTicketRelationOperation",
                "CtowerProjectSourceLinkOperation",
            )
        }
    )
    for forbidden in ("proof", "verdict", "workflow", "lifecycle", "delivery", "effect_payload"):
        assert f'"{forbidden}"' not in encoded
    operations = cast(dict[str, object], schemas["CtowerProjectImportBatchRequest"]["properties"])
    operation_array = cast(dict[str, object], operations["operations"])
    assert operation_array["maxItems"] == MAX_IMPORT_ITEMS


def test_http_principals_match_the_executable_capability_matrix() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    vectors = json.loads(
        (ROOT / "contracts/domain/migration/migration-vectors.json").read_text(encoding="utf-8")
    )
    matrix = cast(dict[str, list[str]], vectors["capability_matrix"])
    actual: dict[str, set[str]] = {
        "operator": set(),
        "migration_importer": set(),
        "fence_observer": set(),
    }
    for path in cast(dict[str, dict[str, object]], document["paths"]).values():
        for method, raw in path.items():
            if method not in {"get", "post"}:
                continue
            operation = cast(dict[str, object], raw)
            principal = operation.get("x-ctower-principal")
            if isinstance(principal, str) and principal in actual:
                operation_id = cast(str, operation["operationId"])
                suffix = ":refusal_only" if operation.get("x-ctower-refusal-only") else ""
                actual[principal].add(operation_id + suffix)
    for principal, operations in actual.items():
        assert operations == set(matrix[principal])
