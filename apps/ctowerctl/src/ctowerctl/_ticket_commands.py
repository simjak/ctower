"""Explicit generated-client ticket command builders and read handlers."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import (
    AdmitIntent,
    AssignmentChangeRequest,
    BlockIntent,
    CustodyTransferRequest,
    DeferIntent,
    EvidenceRequest,
    FreezeCriteriaRequest,
    MutableAssignmentKind,
    Priority,
    PriorityChangeRequest,
    RelationKind,
    RelationRequest,
    ReopenIntent,
    ResolveCloseRequest,
    SourceReference,
    TicketCommentRequest,
    TicketCreateRequest,
    TicketIntentRequest,
    UnblockIntent,
    VerdictDecision,
    VerdictRequest,
    WorkflowStartRequest,
    WorkflowTransitionRequest,
)
from ctowerctl._command_types import MutationPayload
from ctowerctl._input import load_yaml_json, read_text

__all__: tuple[str, ...] = ()

_EVIDENCE_MAX_BYTES = 100_000


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    """Build one explicit generated ticket request selected by authored CLI spelling."""

    cli_name = cast(str, arguments.cli_name)
    builder = _MUTATION_BUILDERS.get(cli_name)
    if builder is None:
        raise ValueError("usage: unsupported ticket mutation")
    return builder(arguments)


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    """Invoke one explicit ticket read through the generated client."""

    cli_name = cast(str, arguments.cli_name)
    handler = _QUERY_HANDLERS.get(cli_name)
    if handler is None:
        raise ValueError("usage: unsupported ticket query")
    return handler(client, arguments)


def mutation_command_names() -> frozenset[str]:
    """Expose the closed ticket mutation inventory for contract parity."""

    return frozenset(_MUTATION_BUILDERS)


def query_command_names() -> frozenset[str]:
    """Expose the closed ticket read inventory for contract parity."""

    return frozenset(_QUERY_HANDLERS)


def _capture(arguments: argparse.Namespace) -> MutationPayload:
    request = TicketCreateRequest(
        initial_custodian_id=cast(UUID, arguments.initial_custodian_id),
        priority=Priority(cast(str, arguments.priority)),
        source=SourceReference(
            kind=cast(str, arguments.source_kind),
            ref=cast(str, arguments.source_ref),
        ),
        title=cast(str, arguments.title),
    )
    return _payload(request)


def _comment(arguments: argparse.Namespace) -> MutationPayload:
    return _ticket_payload(arguments, TicketCommentRequest(body=cast(str, arguments.body)))


def _assignment(arguments: argparse.Namespace) -> MutationPayload:
    kind = {
        "current_assignee": MutableAssignmentKind.CURRENT_ASSIGNEE,
        "stage_owner": MutableAssignmentKind.STAGE_OWNER,
        "reviewer": MutableAssignmentKind.REVIEWER_ASSIGNMENT,
    }[cast(str, arguments.kind)]
    request = AssignmentChangeRequest(
        assignment_kind=kind,
        expected_version=cast(int, arguments.expected_version),
        reason=cast(str, arguments.reason),
        scope_ref=cast(str | None, arguments.scope_ref),
        to_principal_id=cast(UUID, arguments.to_principal_id),
    )
    return _ticket_payload(arguments, request)


def _custody(arguments: argparse.Namespace) -> MutationPayload:
    request = CustodyTransferRequest(
        expected_version=cast(int, arguments.expected_version),
        from_custodian_id=cast(UUID, arguments.from_custodian_id),
        protected_transfer=cast(bool, arguments.protected_transfer),
        reason=cast(str, arguments.reason),
        to_custodian_id=cast(UUID, arguments.to_custodian_id),
    )
    return _ticket_payload(arguments, request)


def _priority(arguments: argparse.Namespace) -> MutationPayload:
    request = PriorityChangeRequest(
        expected_version=cast(int, arguments.expected_version),
        priority=Priority(cast(str, arguments.priority)),
        reason=cast(str, arguments.reason),
        urgent_evidence_ref=cast(str | None, arguments.urgent_evidence_ref),
    )
    return _ticket_payload(arguments, request)


def _intent(arguments: argparse.Namespace) -> MutationPayload:
    cli_name = cast(str, arguments.cli_name)
    intent: AdmitIntent | DeferIntent | ReopenIntent
    if cli_name == "ticket admit":
        intent = AdmitIntent(
            kind="admit",
            expected_version=cast(int, arguments.expected_version),
            reason=cast(str, arguments.reason),
        )
    elif cli_name == "ticket defer":
        intent = DeferIntent(
            kind="defer",
            expected_version=cast(int, arguments.expected_version),
            reason=cast(str, arguments.reason),
            review_after=arguments.review_after,
        )
    elif cli_name == "ticket reopen":
        intent = ReopenIntent(
            kind="reopen",
            expected_version=cast(int, arguments.expected_version),
            priority_policy="carry_forward",
            reason=cast(str, arguments.reason),
        )
    else:
        raise ValueError("usage: unsupported ticket intent")
    return _ticket_payload(arguments, TicketIntentRequest(intent=intent))


def _block(arguments: argparse.Namespace) -> MutationPayload:
    intent = BlockIntent(
        kind="block",
        expected_version=cast(int, arguments.expected_version),
        reason=cast(str, arguments.reason),
        blocker_id=cast(UUID, arguments.blocker_id),
        blocker_kind=arguments.blocker_kind,
        reason_class=cast(str, arguments.reason_class),
        owner_principal_id=cast(UUID, arguments.owner_principal_id),
        source_ref=cast(str, arguments.source_ref),
        affected_stage=cast(str | None, arguments.affected_stage),
        resolution_condition=cast(str, arguments.resolution_condition),
        next_check_at=arguments.next_check_at,
        dependency_ref=cast(str | None, arguments.dependency_ref),
        board_impact=cast(bool, arguments.board_impact),
    )
    return _ticket_payload(arguments, TicketIntentRequest(intent=intent))


def _unblock(arguments: argparse.Namespace) -> MutationPayload:
    intent = UnblockIntent(
        kind="unblock",
        expected_version=cast(int, arguments.expected_version),
        reason=cast(str, arguments.reason),
        blocker_id=cast(UUID, arguments.blocker_id),
        resolution_evidence_ref=cast(str, arguments.resolution_evidence_ref),
    )
    return _ticket_payload(arguments, TicketIntentRequest(intent=intent))


def _relation(arguments: argparse.Namespace) -> MutationPayload:
    request = RelationRequest(
        expected_version=cast(int, arguments.expected_version),
        reason=cast(str, arguments.reason),
        relation_kind=RelationKind(cast(str, arguments.kind)),
        target_ticket_id=cast(UUID, arguments.target_ticket_id),
    )
    return _ticket_payload(arguments, request)


def _criteria(arguments: argparse.Namespace) -> MutationPayload:
    criteria = load_yaml_json(arguments.criteria_file, label="criteria input")
    payload = {
        "candidate_digest": cast(str, arguments.candidate_digest),
        "criteria": criteria,
        "expected_version": cast(int, arguments.expected_version),
    }
    request = FreezeCriteriaRequest.model_validate_json(
        json.dumps(payload, allow_nan=False, separators=(",", ":"))
    )
    return _ticket_payload(arguments, request)


def _evidence(arguments: argparse.Namespace) -> MutationPayload:
    request = EvidenceRequest(
        expected_version=cast(int, arguments.expected_version),
        evidence_id=cast(UUID, arguments.evidence_id),
        criterion_key=cast(str, arguments.criterion_key),
        candidate_digest=cast(str, arguments.candidate_digest),
        artifact_digest=cast(str, arguments.artifact_digest),
        content=read_text(
            arguments.content_file,
            maximum_bytes=_EVIDENCE_MAX_BYTES,
            label="evidence content",
        ),
    )
    return _ticket_payload(arguments, request)


def _verdict(arguments: argparse.Namespace) -> MutationPayload:
    request = VerdictRequest(
        expected_version=cast(int, arguments.expected_version),
        verdict_id=cast(UUID, arguments.verdict_id),
        criterion_key=cast(str, arguments.criterion_key),
        candidate_digest=cast(str, arguments.candidate_digest),
        decision=VerdictDecision(cast(str, arguments.decision)),
    )
    return _ticket_payload(arguments, request)


def _workflow_start(arguments: argparse.Namespace) -> MutationPayload:
    request = WorkflowStartRequest(
        workflow_ref=cast(str, arguments.workflow_ref),
        workflow_digest=cast(str, arguments.workflow_digest),
        execution_policy_ref=cast(str, arguments.execution_policy_ref),
        execution_policy_digest=cast(str, arguments.execution_policy_digest),
        gate_policy_ref=cast(str, arguments.gate_policy_ref),
        gate_policy_digest=cast(str, arguments.gate_policy_digest),
        evidence_policy_ref=cast(str, arguments.evidence_policy_ref),
        evidence_policy_digest=cast(str, arguments.evidence_policy_digest),
    )
    return _ticket_payload(arguments, request)


def _transition(arguments: argparse.Namespace) -> MutationPayload:
    request = WorkflowTransitionRequest(
        expected_version=cast(int, arguments.expected_version),
        workflow_ref=cast(str, arguments.workflow_ref),
        source_stage=cast(str, arguments.source_stage),
        destination_stage=cast(str, arguments.destination_stage),
    )
    return _ticket_payload(arguments, request)


def _resolve(arguments: argparse.Namespace) -> MutationPayload:
    request = ResolveCloseRequest(
        expected_version=cast(int, arguments.expected_version),
        workflow_ref=cast(str, arguments.workflow_ref),
    )
    return _ticket_payload(arguments, request)


def _ticket_payload(arguments: argparse.Namespace, request: BaseModel) -> MutationPayload:
    return _payload(request, ticket_id=str(cast(UUID, arguments.ticket_id)))


def _payload(request: BaseModel, **path_parameters: str) -> MutationPayload:
    return MutationPayload(request=request, path_parameters=path_parameters)


def _ticket_query(client: CtowerClient, arguments: argparse.Namespace) -> BaseModel:
    return client.get_ticket(cast(UUID, arguments.ticket_id))


def _timeline(client: CtowerClient, arguments: argparse.Namespace) -> BaseModel:
    return client.get_ticket_timeline(cast(UUID, arguments.ticket_id))


def _assignments(client: CtowerClient, arguments: argparse.Namespace) -> BaseModel:
    return client.list_ticket_assignments(cast(UUID, arguments.ticket_id))


def _audit(client: CtowerClient, arguments: argparse.Namespace) -> BaseModel:
    return client.list_ticket_audit_events(
        cast(UUID, arguments.ticket_id),
        cursor=cast(int | None, arguments.cursor),
        limit=cast(int | None, arguments.limit),
    )


_MUTATION_BUILDERS: dict[str, Callable[[argparse.Namespace], MutationPayload]] = {
    "ticket capture": _capture,
    "ticket create": _capture,
    "ticket comment add": _comment,
    "ticket assign": _assignment,
    "ticket custody transfer": _custody,
    "ticket prioritize": _priority,
    "ticket admit": _intent,
    "ticket defer": _intent,
    "ticket block": _block,
    "ticket unblock": _unblock,
    "ticket reopen": _intent,
    "ticket relation add": _relation,
    "ticket criteria freeze": _criteria,
    "ticket evidence add": _evidence,
    "ticket gate verdict": _verdict,
    "ticket workflow start": _workflow_start,
    "ticket transition": _transition,
    "ticket resolve": _resolve,
}

_QUERY_HANDLERS: dict[str, Callable[[CtowerClient, argparse.Namespace], BaseModel]] = {
    "ticket query": _ticket_query,
    "ticket show": _ticket_query,
    "ticket timeline": _timeline,
    "ticket assignments": _assignments,
    "ticket audit": _audit,
}
