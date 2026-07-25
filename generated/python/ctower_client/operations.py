"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:e1263c9e3ab91876558e63c26af7f1a2bb7e6f0ba30d5984a3499e17cd78c3e8
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel

from ctower_client import models as _models

__all__ = [
    "CLI_OPERATIONS",
    "OPERATIONS",
    "OperationSpec",
    "SpoolPolicy",
    "operation_for_cli",
]


class SpoolPolicy(StrEnum):
    ALLOWED = "allowed"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True, slots=True)
class OperationSpec:
    operation_id: str
    client_method: str
    method: Literal["GET", "POST"]
    path: str
    request_model: type[BaseModel] | None
    response_model: type[BaseModel]
    cli_names: tuple[str, ...]
    mutation: bool
    spool_policy: SpoolPolicy


OPERATIONS = MappingProxyType(
    {
        "addTicketComment": OperationSpec(
            operation_id="addTicketComment",
            client_method="add_ticket_comment",
            method="POST",
            path="/v1/tickets/{ticket_id}/comments",
            request_model=_models.TicketCommentRequest,
            response_model=_models.TicketCommentResult,
            cli_names=('ticket comment add',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "addTicketRelation": OperationSpec(
            operation_id="addTicketRelation",
            client_method="add_ticket_relation",
            method="POST",
            path="/v1/tickets/{ticket_id}/relations",
            request_model=_models.RelationRequest,
            response_model=_models.WorkReceipt,
            cli_names=('ticket relation add',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "applyCompanyBundle": OperationSpec(
            operation_id="applyCompanyBundle",
            client_method="apply_company_bundle",
            method="POST",
            path="/v1/company/bundle/apply",
            request_model=_models.CompanyBundleApplyRequest,
            response_model=_models.CompanyBundleCommandResult,
            cli_names=('company bundle apply',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "applyTicketIntent": OperationSpec(
            operation_id="applyTicketIntent",
            client_method="apply_ticket_intent",
            method="POST",
            path="/v1/tickets/{ticket_id}/intents",
            request_model=_models.TicketIntentRequest,
            response_model=_models.WorkReceipt,
            cli_names=('ticket admit', 'ticket defer', 'ticket block', 'ticket unblock', 'ticket reopen'),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "bootstrapFirstTenant": OperationSpec(
            operation_id="bootstrapFirstTenant",
            client_method="bootstrap_first_tenant",
            method="POST",
            path="/v1/bootstrap/first-tenant",
            request_model=_models.BootstrapRequest,
            response_model=_models.BootstrapReceipt,
            cli_names=('bootstrap first-tenant',),
            mutation=True,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "changeTicketAssignment": OperationSpec(
            operation_id="changeTicketAssignment",
            client_method="change_ticket_assignment",
            method="POST",
            path="/v1/tickets/{ticket_id}/assignments",
            request_model=_models.AssignmentChangeRequest,
            response_model=_models.WorkReceipt,
            cli_names=('ticket assign',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "changeTicketPriority": OperationSpec(
            operation_id="changeTicketPriority",
            client_method="change_ticket_priority",
            method="POST",
            path="/v1/tickets/{ticket_id}/priority",
            request_model=_models.PriorityChangeRequest,
            response_model=_models.WorkReceipt,
            cli_names=('ticket prioritize',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "createTicket": OperationSpec(
            operation_id="createTicket",
            client_method="create_ticket",
            method="POST",
            path="/v1/tickets",
            request_model=_models.TicketCreateRequest,
            response_model=_models.TicketCommandResult,
            cli_names=('ticket capture', 'ticket create'),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "exportCompanyBundle": OperationSpec(
            operation_id="exportCompanyBundle",
            client_method="export_company_bundle",
            method="GET",
            path="/v1/company/bundle/export",
            request_model=None,
            response_model=_models.CompanyBundleExportResult,
            cli_names=('company bundle export',),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "freezeProofCriteria": OperationSpec(
            operation_id="freezeProofCriteria",
            client_method="freeze_proof_criteria",
            method="POST",
            path="/v1/tickets/{ticket_id}/proof/criteria",
            request_model=_models.FreezeCriteriaRequest,
            response_model=_models.ProofReceipt,
            cli_names=('ticket criteria freeze',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "getBoard": OperationSpec(
            operation_id="getBoard",
            client_method="get_board",
            method="GET",
            path="/v1/board",
            request_model=None,
            response_model=_models.BoardView,
            cli_names=('board query',),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "getControlHealth": OperationSpec(
            operation_id="getControlHealth",
            client_method="get_control_health",
            method="GET",
            path="/health",
            request_model=None,
            response_model=_models.ControlHealth,
            cli_names=('control health',),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "getSyntheticWorkflowRun": OperationSpec(
            operation_id="getSyntheticWorkflowRun",
            client_method="get_synthetic_workflow_run",
            method="GET",
            path="/v1/control/synthetic-runs/{run_id}",
            request_model=None,
            response_model=_models.SyntheticRunResource,
            cli_names=('synthetic query',),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "getTicket": OperationSpec(
            operation_id="getTicket",
            client_method="get_ticket",
            method="GET",
            path="/v1/tickets/{ticket_id}",
            request_model=None,
            response_model=_models.TicketResource,
            cli_names=('ticket query', 'ticket show'),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "getTicketTimeline": OperationSpec(
            operation_id="getTicketTimeline",
            client_method="get_ticket_timeline",
            method="GET",
            path="/v1/tickets/{ticket_id}/timeline",
            request_model=None,
            response_model=_models.TimelineResponse,
            cli_names=('ticket timeline',),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "listTicketAssignments": OperationSpec(
            operation_id="listTicketAssignments",
            client_method="list_ticket_assignments",
            method="GET",
            path="/v1/tickets/{ticket_id}/assignments",
            request_model=None,
            response_model=_models.AssignmentList,
            cli_names=('ticket assignments',),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "listTicketAuditEvents": OperationSpec(
            operation_id="listTicketAuditEvents",
            client_method="list_ticket_audit_events",
            method="GET",
            path="/v1/tickets/{ticket_id}/audit",
            request_model=None,
            response_model=_models.AuditPage,
            cli_names=('ticket audit',),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "planCompanyBundle": OperationSpec(
            operation_id="planCompanyBundle",
            client_method="plan_company_bundle",
            method="POST",
            path="/v1/company/bundle/plan",
            request_model=_models.CompanyBundleRequest,
            response_model=_models.CompanyBundlePlan,
            cli_names=('company bundle plan',),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
        "recordOutboxPoisonDisposition": OperationSpec(
            operation_id="recordOutboxPoisonDisposition",
            client_method="record_outbox_poison_disposition",
            method="POST",
            path="/v1/outbox/{outbox_id}/dispositions",
            request_model=_models.PoisonDispositionRequest,
            response_model=_models.PoisonDispositionReceipt,
            cli_names=('ops outbox poison dispose',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "recordProofEvidence": OperationSpec(
            operation_id="recordProofEvidence",
            client_method="record_proof_evidence",
            method="POST",
            path="/v1/tickets/{ticket_id}/proof/evidence",
            request_model=_models.EvidenceRequest,
            response_model=_models.ProofReceipt,
            cli_names=('ticket evidence add',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "recordProofVerdict": OperationSpec(
            operation_id="recordProofVerdict",
            client_method="record_proof_verdict",
            method="POST",
            path="/v1/tickets/{ticket_id}/proof/verdict",
            request_model=_models.VerdictRequest,
            response_model=_models.ProofReceipt,
            cli_names=('ticket gate verdict',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "resolveCloseWorkflow": OperationSpec(
            operation_id="resolveCloseWorkflow",
            client_method="resolve_close_workflow",
            method="POST",
            path="/v1/tickets/{ticket_id}/workflow/resolve-close",
            request_model=_models.ResolveCloseRequest,
            response_model=_models.WorkflowReceipt,
            cli_names=('ticket resolve',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "runSyntheticWorkflow": OperationSpec(
            operation_id="runSyntheticWorkflow",
            client_method="run_synthetic_workflow",
            method="POST",
            path="/v1/control/synthetic-runs",
            request_model=_models.SyntheticRunRequest,
            response_model=_models.SyntheticRunReceipt,
            cli_names=('synthetic run',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "startTicketWorkflow": OperationSpec(
            operation_id="startTicketWorkflow",
            client_method="start_ticket_workflow",
            method="POST",
            path="/v1/tickets/{ticket_id}/workflow/start",
            request_model=_models.WorkflowStartRequest,
            response_model=_models.WorkflowReceipt,
            cli_names=('ticket workflow start',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "transferTicketCustody": OperationSpec(
            operation_id="transferTicketCustody",
            client_method="transfer_ticket_custody",
            method="POST",
            path="/v1/tickets/{ticket_id}/custody",
            request_model=_models.CustodyTransferRequest,
            response_model=_models.TicketCommandResult,
            cli_names=('ticket custody transfer',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "transitionWorkflow": OperationSpec(
            operation_id="transitionWorkflow",
            client_method="transition_workflow",
            method="POST",
            path="/v1/tickets/{ticket_id}/workflow/transition",
            request_model=_models.WorkflowTransitionRequest,
            response_model=_models.WorkflowReceipt,
            cli_names=('ticket transition',),
            mutation=True,
            spool_policy=SpoolPolicy.ALLOWED,
        ),
        "validateCompanyBundle": OperationSpec(
            operation_id="validateCompanyBundle",
            client_method="validate_company_bundle",
            method="POST",
            path="/v1/company/bundle/validate",
            request_model=_models.CompanyBundleRequest,
            response_model=_models.CompanyBundleValidationResult,
            cli_names=('company bundle validate',),
            mutation=False,
            spool_policy=SpoolPolicy.FORBIDDEN,
        ),
    }
)

CLI_OPERATIONS = MappingProxyType(
    {
        "ticket comment add": OPERATIONS["addTicketComment"],
        "ticket relation add": OPERATIONS["addTicketRelation"],
        "company bundle apply": OPERATIONS["applyCompanyBundle"],
        "ticket admit": OPERATIONS["applyTicketIntent"],
        "ticket defer": OPERATIONS["applyTicketIntent"],
        "ticket block": OPERATIONS["applyTicketIntent"],
        "ticket unblock": OPERATIONS["applyTicketIntent"],
        "ticket reopen": OPERATIONS["applyTicketIntent"],
        "bootstrap first-tenant": OPERATIONS["bootstrapFirstTenant"],
        "ticket assign": OPERATIONS["changeTicketAssignment"],
        "ticket prioritize": OPERATIONS["changeTicketPriority"],
        "ticket capture": OPERATIONS["createTicket"],
        "ticket create": OPERATIONS["createTicket"],
        "company bundle export": OPERATIONS["exportCompanyBundle"],
        "ticket criteria freeze": OPERATIONS["freezeProofCriteria"],
        "board query": OPERATIONS["getBoard"],
        "control health": OPERATIONS["getControlHealth"],
        "synthetic query": OPERATIONS["getSyntheticWorkflowRun"],
        "ticket query": OPERATIONS["getTicket"],
        "ticket show": OPERATIONS["getTicket"],
        "ticket timeline": OPERATIONS["getTicketTimeline"],
        "ticket assignments": OPERATIONS["listTicketAssignments"],
        "ticket audit": OPERATIONS["listTicketAuditEvents"],
        "company bundle plan": OPERATIONS["planCompanyBundle"],
        "ops outbox poison dispose": OPERATIONS["recordOutboxPoisonDisposition"],
        "ticket evidence add": OPERATIONS["recordProofEvidence"],
        "ticket gate verdict": OPERATIONS["recordProofVerdict"],
        "ticket resolve": OPERATIONS["resolveCloseWorkflow"],
        "synthetic run": OPERATIONS["runSyntheticWorkflow"],
        "ticket workflow start": OPERATIONS["startTicketWorkflow"],
        "ticket custody transfer": OPERATIONS["transferTicketCustody"],
        "ticket transition": OPERATIONS["transitionWorkflow"],
        "company bundle validate": OPERATIONS["validateCompanyBundle"],
    }
)


def operation_for_cli(cli_name: str) -> OperationSpec | None:
    """Resolve only an authored CLI spelling; never dispatch arbitrary operation IDs."""

    return CLI_OPERATIONS.get(cli_name)
