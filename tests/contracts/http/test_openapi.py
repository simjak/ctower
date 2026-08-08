"""Minimum public HTTP and RFC 9457 contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]
MAX_IMPORT_ITEMS = 64

_EXPECTED_OPERATION_METADATA: dict[str, tuple[object, bool, str, object, bool]] = {
    "addKnowledgeDocument": ("knowledge add", True, "allowed", None, False),
    "addTicketComment": ("ticket comment add", True, "allowed", None, False),
    "addTicketRelation": ("ticket relation add", True, "allowed", None, False),
    "appendAttentionFinding": ("attention finding append", True, "allowed", None, False),
    "appendCtowerProjectImportCorrection": (
        "migration ctower-project correction append",
        True,
        "forbidden",
        "operator",
        False,
    ),
    "applyCompanyBundle": ("company bundle apply", True, "allowed", None, False),
    "applyCtowerProjectImportBatch": (
        "migration ctower-project import",
        True,
        "forbidden",
        "migration_importer",
        False,
    ),
    "applyTicketIntent": (
        ["ticket admit", "ticket defer", "ticket block", "ticket unblock", "ticket reopen"],
        True,
        "allowed",
        None,
        False,
    ),
    "applyTicketLabel": ("ticket label apply", True, "allowed", None, False),
    "bindCtowerProjectAliasPlan": (
        "migration ctower-project plan",
        True,
        "forbidden",
        "operator",
        False,
    ),
    "bindCtowerProjectExportEquality": (
        "migration ctower-project export",
        True,
        "forbidden",
        "operator",
        False,
    ),
    "bootstrapFirstTenant": ("bootstrap first-tenant", True, "forbidden", None, False),
    "changeTicketAssignment": ("ticket assign", True, "allowed", None, False),
    "changeTicketPriority": ("ticket prioritize", True, "allowed", None, False),
    "consumeReviewDispatchEffect": (
        "ticket review-dispatch consume",
        True,
        "allowed",
        None,
        False,
    ),
    "commitCtowerProjectDevelopmentEpoch": (
        "migration ctower-project commit-development-epoch",
        False,
        "forbidden",
        "operator",
        True,
    ),
    "createCtowerProjectImportRun": (
        "migration ctower-project inventory",
        True,
        "forbidden",
        "operator",
        False,
    ),
    "createTicket": (["ticket capture", "ticket create"], True, "allowed", None, False),
    "exportCompanyBundle": ("company bundle export", False, "forbidden", None, False),
    "finalizeCtowerProjectImportRun": (
        "migration ctower-project reconcile",
        True,
        "forbidden",
        "operator",
        False,
    ),
    "freezeProofCriteria": ("ticket criteria freeze", True, "allowed", None, False),
    "getBoard": ("board query", False, "forbidden", None, False),
    "getControlHealth": ("control health", False, "forbidden", None, False),
    "getKnowledgeDocument": ("knowledge get", False, "forbidden", None, False),
    "getCtowerProjectCutoverHealth": (
        "migration ctower-project verify",
        False,
        "forbidden",
        "authenticated",
        False,
    ),
    "getCtowerProjectImportRun": (
        "migration ctower-project run get",
        False,
        "forbidden",
        "operator",
        False,
    ),
    "getProjectDelivery": (
        "project delivery query",
        False,
        "forbidden",
        "authenticated",
        False,
    ),
    "getSyntheticWorkflowRun": ("synthetic query", False, "forbidden", None, False),
    "getTicket": (["ticket query", "ticket show"], False, "forbidden", None, False),
    "getTicketTimeline": ("ticket timeline", False, "forbidden", None, False),
    "issueSeatCredential": ("credential seat issue", True, "forbidden", None, False),
    "acknowledgeInboxMessage": ("inbox ack", True, "allowed", None, False),
    "listInboxThreads": ("inbox list", False, "forbidden", None, False),
    "listKnowledgeDocuments": ("knowledge list", False, "forbidden", None, False),
    "listTicketAssignments": ("ticket assignments", False, "forbidden", None, False),
    "listTicketAuditEvents": ("ticket audit", False, "forbidden", None, False),
    "listProjectEvents": (
        "project events",
        False,
        "forbidden",
        "authenticated",
        False,
    ),
    "listProjectSessions": (
        "session project",
        False,
        "forbidden",
        "authenticated",
        False,
    ),
    "listReviewDispatchEffects": (
        "ticket review-dispatch list",
        False,
        "forbidden",
        None,
        False,
    ),
    "listTicketSessions": ("session ticket", False, "forbidden", None, False),
    "planCompanyBundle": ("company bundle plan", False, "forbidden", None, False),
    "prepareCtowerProjectCutover": (
        "migration ctower-project prepare",
        False,
        "forbidden",
        "operator",
        True,
    ),
    "promoteIntakeEvent": ("intake promote", True, "allowed", None, False),
    "promoteInboxThread": ("inbox promote", True, "allowed", None, False),
    "readInboxThread": ("inbox read", False, "forbidden", None, False),
    "readInboxMessageState": ("inbox read-state", False, "forbidden", None, False),
    "recordAttentionFindingDisposition": (
        "attention finding disposition",
        True,
        "allowed",
        None,
        False,
    ),
    "recordOutboxPoisonDisposition": (
        "ops outbox poison dispose",
        True,
        "allowed",
        None,
        False,
    ),
    "recordTicketChangeReference": (
        "ticket change-reference add",
        True,
        "allowed",
        None,
        False,
    ),
    "recordProofEvidence": ("ticket evidence add", True, "allowed", None, False),
    "recordTicketSessionFact": (
        ["session transition", "session close"],
        True,
        "allowed",
        None,
        False,
    ),
    "recordProofVerdict": ("ticket gate verdict", True, "allowed", None, False),
    "reportCtowerProjectFenceObservation": (
        "migration ctower-project fence observe",
        True,
        "forbidden",
        "fence_observer",
        False,
    ),
    "resolveCloseWorkflow": ("ticket resolve", True, "allowed", None, False),
    "revokeSeatCredential": ("credential seat revoke", True, "forbidden", None, False),
    "runSyntheticWorkflow": ("synthetic run", True, "allowed", None, False),
    "sendInboxMessage": ("inbox send", True, "allowed", None, False),
    "startTicketSession": ("session start", True, "allowed", None, False),
    "startTicketWorkflow": ("ticket workflow start", True, "allowed", None, False),
    "submitIntake": ("intake submit", True, "allowed", None, False),
    "transferTicketCustody": ("ticket custody transfer", True, "allowed", None, False),
    "transitionWorkflow": ("ticket transition", True, "allowed", None, False),
    "validateCompanyBundle": ("company bundle validate", False, "forbidden", None, False),
}
_EXPECTED_PROBLEM_CODES = {
    "attention-finding-already-disposed",
    "attention-finding-not-found",
    "attention-kind-unrecognized",
    "auth-exchange-invalid",
    "auth-identity-unresolved",
    "auth-provider-unavailable",
    "auth-provider-unverifiable",
    "auth-role-denied",
    "auth-session-invalid",
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
    "durability_pending",
    "i1-7c-required",
    "idempotency-conflict",
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
    "prohibited-data-class",
    "project-delivery-unavailable",
    "project-grant-required",
    "project-scope-denied",
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


def _function_definitions(root: Path, name: str) -> set[str]:
    definitions: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
            for node in ast.walk(tree)
        ):
            definitions.add(path.relative_to(root).as_posix())
    return definitions


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
        "applyCtowerProjectImportBatch",
        "bindCtowerProjectAliasPlan",
        "bindCtowerProjectExportEquality",
        "bootstrapFirstTenant",
        "createCtowerProjectImportRun",
        "finalizeCtowerProjectImportRun",
        "issueSeatCredential",
        "reportCtowerProjectFenceObservation",
        "revokeSeatCredential",
    }


def test_project_and_credential_refusals_have_one_definition_each() -> None:
    kernel = ROOT / "packages/ctower-kernel/src/ctower_kernel"

    assert _function_definitions(kernel, "project_mutation_refusal") == {"record/transaction.py"}
    assert _function_definitions(kernel, "credential_scope_refusal") == {"record/interface.py"}


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


def test_scalar_profiles_are_exact_root_contracts() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    expected = {
        "x-ctower-free-form-json-profile": {
            "containers": "recursive-arrays-and-objects",
            "duplicate-object-members": "last-member-wins",
            "fraction-exponent-negative-zero": "preserve-sign",
            "fraction-exponent-semantics": "finite-ieee-754-binary64",
            "integer-lexemes": "x-ctower-json-integer-profile",
            "nonfinite": "rejected",
            "overflow": "rejected",
            "trust": "opaque-until-component-schema-validation",
            "underflow": "preserve-binary64-signed-zero",
        },
        "x-ctower-json-integer-profile": {
            "maximum": 9_007_199_254_740_991,
            "minimum": -9_007_199_254_740_991,
            "negative-zero": "normalize-to-zero",
            "semantics": "exact-integer-interoperability",
            "token-syntax": "minus-zero-or-nonzero-decimal-digits-only",
        },
        "x-ctower-absolute-uri-profile": {
            "characters": "ascii-rfc3986",
            "fragment": "allowed",
            "grammar": "rfc3986-uri-with-required-scheme",
            "http-authority": "required-with-nonempty-host",
            "normalization": "none-return-original",
            "percent-encoding": "complete-two-hex-digit-triplets",
            "raw-backslash": "rejected",
            "raw-whitespace-controls": "rejected",
        },
    }

    assert {key: document[key] for key in expected} == expected
    nested = json.dumps({key: value for key, value in document.items() if key not in expected})
    assert all(key not in nested for key in expected)


def test_intake_contract_is_explicit_and_has_no_classifier_or_dispatch_surface() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    paths = cast(dict[str, object], document["paths"])
    schemas = cast(dict[str, object], document["components"]["schemas"])
    intake = {
        "paths": {key: value for key, value in paths.items() if key.startswith("/v1/intake")},
        "schemas": {key: value for key, value in schemas.items() if key.startswith("Intake")},
    }
    rendered = json.dumps(intake, sort_keys=True).casefold()

    assert '"default": "discussion"' in rendered
    for forbidden in ("classifier", "fuzzy", "commander override", "agent dispatch"):
        assert forbidden not in rendered


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
