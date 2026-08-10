"""Closed explicit CLI, assignment, and bounded bundle-input evidence."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from ctower_client.models import (
    AppendFindingRequest,
    ApplyLabelRequest,
    AssignmentChangeRequest,
    ChangeReferenceRequest,
    CustodyTransferRequest,
    EvidenceRequest,
    FindingDispositionRequest,
    FreezeCriteriaRequest,
    InboxNotificationRequest,
    ResolveCloseRequest,
    SeatCredentialIssueRequest,
    SeatCredentialRevocationRequest,
    VerdictRequest,
    WorkflowStartRequest,
)
from ctower_client.operations import CLI_OPERATIONS, SpoolPolicy
from ctowerctl import _credential_commands, _ruling_commands, _workflow_commands, main
from ctowerctl._attention_commands import build_mutation as build_attention_mutation
from ctowerctl._attention_commands import (
    mutation_command_names as attention_mutations,
)
from ctowerctl._company_commands import (
    load_bundle,
)
from ctowerctl._company_commands import (
    mutation_command_names as company_mutations,
)
from ctowerctl._company_commands import (
    query_command_names as company_queries,
)
from ctowerctl._dream_dispatch_commands import (
    mutation_command_names as dream_dispatch_mutations,
)
from ctowerctl._dream_dispatch_commands import query_command_names as dream_dispatch_queries
from ctowerctl._dream_lane_commands import mutation_command_names as dream_lane_mutations
from ctowerctl._inbox_commands import build_mutation as build_inbox_mutation
from ctowerctl._inbox_commands import mutation_command_names as inbox_mutations
from ctowerctl._inbox_commands import query_command_names as inbox_queries
from ctowerctl._intake_commands import mutation_command_names as intake_mutations
from ctowerctl._knowledge_commands import mutation_command_names as knowledge_mutations
from ctowerctl._knowledge_commands import query_command_names as knowledge_queries
from ctowerctl._migration_commands import (
    mutation_command_names as migration_mutations,
)
from ctowerctl._migration_commands import (
    query_command_names as migration_queries,
)
from ctowerctl._migration_commands import (
    refusal_command_names as migration_refusals,
)
from ctowerctl._ops_commands import (
    mutation_command_names as ops_mutations,
)
from ctowerctl._ops_commands import (
    query_command_names as ops_queries,
)
from ctowerctl._parser import authored_command_names, parse_arguments
from ctowerctl._request_commands import mutation_command_names as request_mutations
from ctowerctl._request_commands import query_command_names as request_queries
from ctowerctl._session_commands import (
    mutation_command_names as session_mutations,
)
from ctowerctl._session_commands import (
    query_command_names as session_queries,
)
from ctowerctl._synthetic_commands import (
    mutation_command_names as synthetic_mutations,
)
from ctowerctl._synthetic_commands import (
    query_command_names as synthetic_queries,
)
from ctowerctl._ticket_commands import (
    build_mutation,
)
from ctowerctl._ticket_commands import (
    mutation_command_names as ticket_mutations,
)
from ctowerctl._ticket_commands import (
    query_command_names as ticket_queries,
)

__all__: tuple[str, ...] = ()


def test_parser_exposes_every_authored_name_without_operation_dispatch() -> None:
    assert authored_command_names() == frozenset(CLI_OPERATIONS)
    with pytest.raises(ValueError, match="usage"):
        parse_arguments(
            [
                "--base-url",
                "https://ctower.example",
                "operation",
                "applyCompanyBundle",
            ]
        )


def test_explicit_handlers_cover_every_generated_operation_class() -> None:
    mutations = (
        ticket_mutations()
        | company_mutations()
        | ops_mutations()
        | synthetic_mutations()
        | migration_mutations()
        | intake_mutations()
        | inbox_mutations()
        | knowledge_mutations()
        | _credential_commands.mutation_command_names()
        | session_mutations()
        | attention_mutations()
        | dream_dispatch_mutations()
        | dream_lane_mutations()
        | (request_mutations() | _ruling_commands.mutation_command_names())
    )
    queries = (
        ticket_queries()
        | company_queries()
        | ops_queries()
        | synthetic_queries()
        | migration_queries()
        | inbox_queries()
        | knowledge_queries()
        | session_queries()
        | dream_dispatch_queries()
        | ({"digest morning"} | request_queries() | _ruling_commands.query_command_names())
    )
    refusals = migration_refusals()
    expected_mutations = {name for name, operation in CLI_OPERATIONS.items() if operation.mutation}
    expected_queries = {
        name
        for name, operation in CLI_OPERATIONS.items()
        if not operation.mutation and not operation.refusal_only
    }
    expected_refusals = {
        name for name, operation in CLI_OPERATIONS.items() if operation.refusal_only
    }
    forbidden = {
        name
        for name, operation in CLI_OPERATIONS.items()
        if operation.mutation and operation.spool_policy is SpoolPolicy.FORBIDDEN
    }

    assert mutations == expected_mutations - {"bootstrap first-tenant"}
    assert queries == expected_queries
    assert refusals == expected_refusals
    assert forbidden == {
        "bootstrap first-tenant",
        "credential seat issue",
        "credential seat revoke",
        "dream-lane bind",
        "migration ctower-project inventory",
        "migration ctower-project export",
        "migration ctower-project plan",
        "migration ctower-project import",
        "migration ctower-project reconcile",
        "migration ctower-project correction append",
        "migration ctower-project fence observe",
    }


def test_inbox_notify_builds_the_strict_generated_request() -> None:
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "inbox",
            "notify",
            "--command-id",
            str(uuid4()),
            "--to",
            "qa-agent",
            "Strict notification body.",
        ]
    )

    payload = build_inbox_mutation(arguments)

    assert isinstance(payload.request, InboxNotificationRequest)
    assert payload.request.model_dump(mode="json") == {
        "text": "Strict notification body.",
        "to": "qa-agent",
    }
    assert payload.path_parameters == {}


def test_review_dispatch_commands_parse_the_exact_effect_and_routing_facts() -> None:
    ticket_id = uuid4()
    effect_id = uuid4()
    listed = parse_arguments(["ticket", "review-dispatch", "list", str(ticket_id)])
    consumed = parse_arguments(
        [
            "ticket",
            "review-dispatch",
            "consume",
            str(ticket_id),
            str(effect_id),
            "--expected-version",
            "3",
            "--reason",
            "Independent review routing",
            "--crew-name",
            "review-r347",
        ]
    )

    assert listed.cli_name == "ticket review-dispatch list"
    assert listed.ticket_id == ticket_id
    assert consumed.cli_name == "ticket review-dispatch consume"
    assert consumed.effect_id == effect_id
    assert consumed.crew_name == "review-r347"


def test_project_seat_credential_commands_are_strict_and_unspoolable() -> None:
    command_id = uuid4()
    issue = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "credential",
            "seat",
            "issue",
            "--command-id",
            str(command_id),
            "--credential-digest",
            "sha256:" + "a" * 64,
            "--credential-ref",
            "secret-ref:seat/manibo",
            "--display-name",
            "Manibo Commander",
            "--project-key",
            "manibo",
            "--scope",
            "capture",
            "--scope",
            "transition",
            "--seat-key",
            "manibo-commander",
        ]
    )
    credential_id = uuid4()
    revoke = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "credential",
            "seat",
            "revoke",
            str(credential_id),
            "--command-id",
            str(uuid4()),
            "--reason",
            "rotation",
        ]
    )

    issuance = _credential_commands.build_mutation(issue)
    revocation = _credential_commands.build_mutation(revoke)

    assert isinstance(issuance.request, SeatCredentialIssueRequest)
    assert issuance.request.scopes == ("capture", "transition")
    assert issuance.path_parameters == {}
    assert isinstance(revocation.request, SeatCredentialRevocationRequest)
    assert revocation.path_parameters == {"credential_id": str(credential_id)}


def test_assignment_and_custody_build_distinct_generated_requests() -> None:
    ticket_id = uuid4()
    command_id = uuid4()
    principal_id = uuid4()
    assignment = parse_arguments(_assignment_arguments(ticket_id, command_id, principal_id))
    custody = parse_arguments(_custody_arguments(ticket_id, command_id, principal_id))

    assignment_payload = build_mutation(assignment)
    custody_payload = build_mutation(custody)

    assert assignment.cli_name == "ticket assign"
    assert isinstance(assignment_payload.request, AssignmentChangeRequest)
    assert assignment_payload.request.assignment_kind == "reviewer_assignment"
    assert custody.cli_name == "ticket custody transfer"
    assert isinstance(custody_payload.request, CustodyTransferRequest)


def test_ticket_context_set_commands_build_distinct_generated_requests() -> None:
    ticket_id = uuid4()
    change_reference = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "ticket",
            "change-reference",
            "add",
            str(ticket_id),
            "--command-id",
            str(uuid4()),
            "--repository",
            "simjak/ctower",
            "--change-identity",
            "284",
            "--reference",
            "https://github.com/simjak/ctower/pull/284",
        ]
    )
    label = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "ticket",
            "label",
            "apply",
            str(ticket_id),
            "--command-id",
            str(uuid4()),
            "--label-key",
            "security",
        ]
    )

    change_reference_payload = build_mutation(change_reference)
    label_payload = build_mutation(label)

    assert isinstance(change_reference_payload.request, ChangeReferenceRequest)
    assert change_reference_payload.path_parameters == {"ticket_id": str(ticket_id)}
    assert isinstance(label_payload.request, ApplyLabelRequest)
    assert label_payload.request.label_key == "security"


def test_attention_commands_build_distinct_generated_requests() -> None:
    append = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "attention",
            "finding",
            "append",
            "--command-id",
            str(uuid4()),
            "--subject-ticket-id",
            str(uuid4()),
            "--kind-key",
            "needs_decision",
            "--reason-code",
            "gate_decision",
            "--effective-owner",
            "operator",
            "--recommendation",
            "Approve the release train",
            "--alternative",
            "Defer to next window",
            "--consequence",
            "Release stays blocked",
            "--dedupe-key",
            "release-gate-1",
            "--source-fact",
            "gate:release-1",
        ]
    )
    disposition = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "attention",
            "finding",
            "disposition",
            str(uuid4()),
            "--command-id",
            str(uuid4()),
            "--outcome",
            "resolved",
            "--reason",
            "Decision made",
        ]
    )

    append_payload = build_attention_mutation(append)
    disposition_payload = build_attention_mutation(disposition)

    assert isinstance(append_payload.request, AppendFindingRequest)
    assert append_payload.path_parameters == {}
    assert isinstance(disposition_payload.request, FindingDispositionRequest)
    assert disposition_payload.request.outcome == "resolved"


def test_ticket_create_defaults_only_derivable_identifiers() -> None:
    arguments = [
        "--base-url",
        "https://ctower.example",
        "ticket",
        "create",
        "--priority",
        "P2",
        "--project-key",
        "ctower",
        "--source-kind",
        "mission-control",
        "--source-ref",
        "R2257",
        "--title",
        "First-day ticket creation",
    ]

    first = parse_arguments(arguments)
    second = parse_arguments(arguments)
    capture = parse_arguments(
        [argument if argument != "create" else "capture" for argument in arguments]
    )
    explicit_command_id = uuid4()
    explicit_custodian_id = uuid4()
    explicit = parse_arguments(
        [
            *arguments,
            "--command-id",
            str(explicit_command_id),
            "--initial-custodian-id",
            str(explicit_custodian_id),
        ]
    )

    assert first.command_id != second.command_id
    assert first.initial_custodian_id is None
    assert capture.command_id not in {first.command_id, second.command_id}
    assert capture.initial_custodian_id is None
    assert explicit.command_id == explicit_command_id
    assert explicit.initial_custodian_id == explicit_custodian_id


def test_workflow_list_and_omitted_pins_use_the_installed_revision() -> None:
    output = io.StringIO()
    status = main(
        [
            "--base-url",
            "https://ctower.example",
            "ticket",
            "workflow",
            "list",
        ],
        stdin=io.StringIO(""),
        stdout=output,
        stderr=io.StringIO(),
    )
    discovery = json.loads(output.getvalue())
    revision = discovery["revisions"][0]
    ticket_id = uuid4()
    start = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "ticket",
            "workflow",
            "start",
            str(ticket_id),
            "--command-id",
            str(uuid4()),
        ]
    )
    resolve = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "ticket",
            "resolve",
            str(ticket_id),
            "--command-id",
            str(uuid4()),
            "--expected-version",
            "4",
        ]
    )

    start_request = build_mutation(start).request
    resolve_request = build_mutation(resolve).request
    assert status == 0
    assert len(discovery["revisions"]) == 1
    assert isinstance(start_request, WorkflowStartRequest)
    assert start_request.model_dump(mode="json") == revision
    assert isinstance(resolve_request, ResolveCloseRequest)
    assert resolve_request.workflow_ref is None


def test_workflow_start_requires_all_explicit_pins_together() -> None:
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "ticket",
            "workflow",
            "start",
            str(uuid4()),
            "--command-id",
            str(uuid4()),
            "--workflow-ref",
            "explicit@1",
        ]
    )

    with pytest.raises(ValueError, match="omitted or supplied together"):
        build_mutation(arguments)


def test_proof_commands_derive_installed_defaults_and_exact_content_digests() -> None:
    ticket_id = uuid4()
    criteria_request = _proof_request(
        "criteria",
        "freeze",
        str(ticket_id),
        "--expected-version",
        "0",
        "--candidate-content",
        "candidate bytes",
    )
    evidence_request = _proof_request(
        "evidence",
        "add",
        str(ticket_id),
        "--expected-version",
        "1",
        "--evidence-id",
        str(uuid4()),
        "--content",
        "evidence bytes",
    )
    verdict_request = _proof_request(
        "gate",
        "verdict",
        str(ticket_id),
        "--expected-version",
        "2",
        "--verdict-id",
        str(uuid4()),
        "--decision",
        "pass",
    )

    assert isinstance(criteria_request, FreezeCriteriaRequest)
    assert (
        criteria_request.candidate_digest,
        [item.key for item in criteria_request.criteria],
    ) == (_digest("candidate bytes"), ["artifact-current"])
    assert isinstance(evidence_request, EvidenceRequest)
    assert (
        evidence_request.candidate_digest,
        evidence_request.artifact_digest,
        evidence_request.criterion_key,
    ) == (None, _digest("evidence bytes"), "artifact-current")
    assert isinstance(verdict_request, VerdictRequest)
    assert verdict_request.candidate_digest is None
    assert verdict_request.criterion_key == "artifact-current"


def _proof_request(*arguments: str) -> object:
    return build_mutation(
        parse_arguments(
            [
                "--base-url",
                "https://ctower.example",
                "ticket",
                *arguments,
                "--command-id",
                str(uuid4()),
            ]
        )
    ).request


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def test_workflow_discovery_changes_with_installed_pack_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pack_root = tmp_path / "packs"
    shutil.copytree(Path(__file__).parents[3] / "packs", pack_root)
    monkeypatch.setattr(_workflow_commands, "_pack_root", lambda: pack_root)
    before = _workflow_commands.installed_pins()

    evidence_path = pack_root / "policies/evidence/trust-spine-four-stage-v1.yaml"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["note"] = "Changed installed bytes must change discovery."
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    after = _workflow_commands.installed_pins()

    assert len(before) == len(after) == 1
    assert before[0].workflow_ref == after[0].workflow_ref
    assert before[0].workflow_digest == after[0].workflow_digest
    assert before[0].evidence_policy_digest != after[0].evidence_policy_digest


def _assignment_arguments(ticket_id: object, command_id: object, principal_id: object) -> list[str]:
    return [
        "--base-url",
        "https://ctower.example",
        "ticket",
        "assign",
        str(ticket_id),
        "--command-id",
        str(command_id),
        "--expected-version",
        "3",
        "--kind",
        "reviewer",
        "--to-principal-id",
        str(principal_id),
        "--reason",
        "Independent review",
    ]


def _custody_arguments(ticket_id: object, command_id: object, principal_id: object) -> list[str]:
    return [
        "--base-url",
        "https://ctower.example",
        "ticket",
        "custody",
        "transfer",
        str(ticket_id),
        "--command-id",
        str(command_id),
        "--expected-version",
        "3",
        "--from-custodian-id",
        str(uuid4()),
        "--to-custodian-id",
        str(principal_id),
        "--reason",
        "Protected authority handoff",
        "--protected-transfer",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        "base: &base {schema: ctower.company-bundle/v1}\nbundle: *base\n",
        "schema: ctower.company-bundle/v1\nschema: ctower.company-bundle/v1\n",
        "schema: !include other.yaml\n",
    ],
)
def test_bundle_input_rejects_alias_duplicate_and_tag(
    tmp_path: Path,
    payload: str,
) -> None:
    source = tmp_path / "bundle.yaml"
    source.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="bundle input"):
        load_bundle(source)
