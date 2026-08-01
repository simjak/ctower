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
    AssignmentChangeRequest,
    CustodyTransferRequest,
    EvidenceRequest,
    FreezeCriteriaRequest,
    ResolveCloseRequest,
    VerdictRequest,
    WorkflowStartRequest,
)
from ctower_client.operations import CLI_OPERATIONS, SpoolPolicy
from ctowerctl import _workflow_commands, main
from ctowerctl._company_commands import (
    load_bundle,
)
from ctowerctl._company_commands import (
    mutation_command_names as company_mutations,
)
from ctowerctl._company_commands import (
    query_command_names as company_queries,
)
from ctowerctl._intake_commands import mutation_command_names as intake_mutations
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
    )
    queries = (
        ticket_queries()
        | company_queries()
        | ops_queries()
        | synthetic_queries()
        | migration_queries()
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
        "migration ctower-project inventory",
        "migration ctower-project export",
        "migration ctower-project plan",
        "migration ctower-project import",
        "migration ctower-project reconcile",
        "migration ctower-project correction append",
        "migration ctower-project fence observe",
    }


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
