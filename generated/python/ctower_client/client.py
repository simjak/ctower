"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:d110be83601a088f160efa3fa859e9e3ed40119c7ab47e3e60d43a170e7163ce
"""

from __future__ import annotations

from collections.abc import Mapping
import secrets
from types import TracebackType
from typing import Annotated, Protocol, Self, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, validate_call

from ctower_client.models import (
    AssignmentChangeRequest,
    AssignmentList,
    AuditPage,
    BoardView,
    BootstrapReceipt,
    BootstrapRequest,
    CompanyBundleApplyRequest,
    CompanyBundleCommandResult,
    CompanyBundleExportResult,
    CompanyBundlePlan,
    CompanyBundleRequest,
    CompanyBundleValidationResult,
    ControlHealth,
    CtowerProjectCutoverHealth,
    CtowerProjectMigrationStubRequest,
    CtowerProjectMigrationStubResult,
    CustodyTransferRequest,
    EvidenceRequest,
    FreezeCriteriaRequest,
    PoisonDispositionReceipt,
    PoisonDispositionRequest,
    PriorityChangeRequest,
    Problem,
    ProjectDeliveryView,
    ProofReceipt,
    RelationRequest,
    ResolveCloseRequest,
    SyntheticRunReceipt,
    SyntheticRunRequest,
    SyntheticRunResource,
    TelemetryContext,
    TicketCommandResult,
    TicketCommentRequest,
    TicketCommentResult,
    TicketCreateRequest,
    TicketIntentRequest,
    TicketResource,
    TimelineResponse,
    VerdictRequest,
    WorkReceipt,
    WorkflowReceipt,
    WorkflowStartRequest,
    WorkflowTransitionRequest,
)

__all__ = ["CtowerClient", "CtowerProblemError"]


class _ProblemModel(Protocol):
    code: str
    detail: str


class CtowerProblemError(Exception):
    """Typed RFC 9457 response from ctower."""

    def __init__(self, problem: _ProblemModel) -> None:
        self.problem = problem
        super().__init__(f"{problem.code}: {problem.detail}")


class CtowerClient:
    """Thin synchronous client generated from the authored HTTP contract."""

    def __init__(
        self,
        base_url: str,
        *,
        credential: str | None = None,
        telemetry: TelemetryContext | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._credential = credential
        self._telemetry = telemetry
        self._http = httpx.Client(base_url=base_url, timeout=timeout_seconds)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def add_ticket_comment(
        self,
        ticket_id: UUID,
        request: TicketCommentRequest,
        *,
        command_id: UUID,
    ) -> TicketCommentResult:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/comments",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, TicketCommentResult, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def add_ticket_relation(
        self,
        ticket_id: UUID,
        request: RelationRequest,
        *,
        command_id: UUID,
    ) -> WorkReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/relations",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, WorkReceipt, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def apply_company_bundle(
        self,
        request: CompanyBundleApplyRequest,
        *,
        command_id: UUID,
    ) -> CompanyBundleCommandResult:
        response = self._http.post(
            "/v1/company/bundle/apply",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, CompanyBundleCommandResult, {401: Problem, 403: Problem, 409: Problem, 422: Problem, 503: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def apply_ticket_intent(
        self,
        ticket_id: UUID,
        request: TicketIntentRequest,
        *,
        command_id: UUID,
    ) -> WorkReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/intents",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, WorkReceipt, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def bootstrap_first_tenant(
        self,
        request: BootstrapRequest,
        *,
        command_id: UUID,
        capability: Annotated[str, Field(min_length=32, max_length=256)],
    ) -> BootstrapReceipt:
        response = self._http.post(
            "/v1/bootstrap/first-tenant",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                    "X-Ctower-Bootstrap-Capability": capability,
                },
            ),
        )
        return _response(response, BootstrapReceipt, {401: Problem, 403: Problem, 409: Problem, 410: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def change_ticket_assignment(
        self,
        ticket_id: UUID,
        request: AssignmentChangeRequest,
        *,
        command_id: UUID,
    ) -> WorkReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/assignments",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, WorkReceipt, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def change_ticket_priority(
        self,
        ticket_id: UUID,
        request: PriorityChangeRequest,
        *,
        command_id: UUID,
    ) -> WorkReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/priority",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, WorkReceipt, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def commit_ctower_project_development_epoch(
        self,
        request: CtowerProjectMigrationStubRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectMigrationStubResult:
        response = self._http.post(
            "/v1/migrations/ctower-project/commit-development-epoch",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, CtowerProjectMigrationStubResult, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def create_ticket(
        self,
        request: TicketCreateRequest,
        *,
        command_id: UUID,
    ) -> TicketCommandResult:
        response = self._http.post(
            "/v1/tickets",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, TicketCommandResult, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def export_company_bundle(
        self,
    ) -> CompanyBundleExportResult:
        response = self._http.get(
            "/v1/company/bundle/export",
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, CompanyBundleExportResult, {401: Problem, 403: Problem, 404: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def export_ctower_project_migration(
        self,
        request: CtowerProjectMigrationStubRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectMigrationStubResult:
        response = self._http.post(
            "/v1/migrations/ctower-project/export",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, CtowerProjectMigrationStubResult, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def freeze_proof_criteria(
        self,
        ticket_id: UUID,
        request: FreezeCriteriaRequest,
        *,
        command_id: UUID,
    ) -> ProofReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/proof/criteria",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, ProofReceipt, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def get_board(
        self,
        *,
        lane: str | None = None,
        priority: str | None = None,
        stage_key: str | None = None,
        custodian_id: UUID | None = None,
        assignee_id: UUID | None = None,
    ) -> BoardView:
        response = self._http.get(
            "/v1/board",
            params={**({"lane": lane} if lane is not None else {}), **({"priority": priority} if priority is not None else {}), **({"stage_key": stage_key} if stage_key is not None else {}), **({"custodian_id": str(custodian_id)} if custodian_id is not None else {}), **({"assignee_id": str(assignee_id)} if assignee_id is not None else {})},
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, BoardView, {401: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def get_control_health(
        self,
    ) -> ControlHealth:
        response = self._http.get(
            "/health",
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, ControlHealth, {401: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def get_ctower_project_cutover_health(
        self,
    ) -> CtowerProjectCutoverHealth:
        response = self._http.get(
            "/v1/migrations/ctower-project/cutover-health",
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, CtowerProjectCutoverHealth, {401: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def get_project_delivery(
        self,
        project_key: str,
    ) -> ProjectDeliveryView:
        response = self._http.get(
            f"/v1/projects/{quote(str(project_key), safe='')}/delivery",
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, ProjectDeliveryView, {401: Problem, 404: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def get_synthetic_workflow_run(
        self,
        run_id: UUID,
    ) -> SyntheticRunResource:
        response = self._http.get(
            f"/v1/control/synthetic-runs/{quote(str(run_id), safe='')}",
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, SyntheticRunResource, {401: Problem, 404: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def get_ticket(
        self,
        ticket_id: UUID,
    ) -> TicketResource:
        response = self._http.get(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}",
            headers=self._telemetry_headers(
                self._context(uuid4(), ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, TicketResource, {401: Problem, 404: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def get_ticket_timeline(
        self,
        ticket_id: UUID,
    ) -> TimelineResponse:
        response = self._http.get(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/timeline",
            headers=self._telemetry_headers(
                self._context(uuid4(), ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, TimelineResponse, {401: Problem, 404: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def import_ctower_project_migration(
        self,
        request: CtowerProjectMigrationStubRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectMigrationStubResult:
        response = self._http.post(
            "/v1/migrations/ctower-project/import",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, CtowerProjectMigrationStubResult, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def inventory_ctower_project_migration(
        self,
        request: CtowerProjectMigrationStubRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectMigrationStubResult:
        response = self._http.post(
            "/v1/migrations/ctower-project/inventory",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, CtowerProjectMigrationStubResult, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def list_ticket_assignments(
        self,
        ticket_id: UUID,
    ) -> AssignmentList:
        response = self._http.get(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/assignments",
            headers=self._telemetry_headers(
                self._context(uuid4(), ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, AssignmentList, {401: Problem, 404: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def list_ticket_audit_events(
        self,
        ticket_id: UUID,
        *,
        cursor: Annotated[int, Field(ge=0)] | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] | None = None,
    ) -> AuditPage:
        response = self._http.get(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/audit",
            params={**({"cursor": cursor} if cursor is not None else {}), **({"limit": limit} if limit is not None else {})},
            headers=self._telemetry_headers(
                self._context(uuid4(), ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, AuditPage, {401: Problem, 404: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def plan_company_bundle(
        self,
        request: CompanyBundleRequest,
    ) -> CompanyBundlePlan:
        response = self._http.post(
            "/v1/company/bundle/plan",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                },
            ),
        )
        return _response(response, CompanyBundlePlan, {401: Problem, 403: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def plan_ctower_project_migration(
        self,
        request: CtowerProjectMigrationStubRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectMigrationStubResult:
        response = self._http.post(
            "/v1/migrations/ctower-project/plan",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, CtowerProjectMigrationStubResult, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def prepare_ctower_project_cutover(
        self,
        request: CtowerProjectMigrationStubRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectMigrationStubResult:
        response = self._http.post(
            "/v1/migrations/ctower-project/prepare",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, CtowerProjectMigrationStubResult, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def reconcile_ctower_project_migration(
        self,
        request: CtowerProjectMigrationStubRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectMigrationStubResult:
        response = self._http.post(
            "/v1/migrations/ctower-project/reconcile",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, CtowerProjectMigrationStubResult, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def record_outbox_poison_disposition(
        self,
        outbox_id: UUID,
        request: PoisonDispositionRequest,
        *,
        command_id: UUID,
    ) -> PoisonDispositionReceipt:
        response = self._http.post(
            f"/v1/outbox/{quote(str(outbox_id), safe='')}/dispositions",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, PoisonDispositionReceipt, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def record_proof_evidence(
        self,
        ticket_id: UUID,
        request: EvidenceRequest,
        *,
        command_id: UUID,
    ) -> ProofReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/proof/evidence",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, ProofReceipt, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def record_proof_verdict(
        self,
        ticket_id: UUID,
        request: VerdictRequest,
        *,
        command_id: UUID,
    ) -> ProofReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/proof/verdict",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, ProofReceipt, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def resolve_close_workflow(
        self,
        ticket_id: UUID,
        request: ResolveCloseRequest,
        *,
        command_id: UUID,
    ) -> WorkflowReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/workflow/resolve-close",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, WorkflowReceipt, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def run_synthetic_workflow(
        self,
        request: SyntheticRunRequest,
        *,
        command_id: UUID,
    ) -> SyntheticRunReceipt:
        response = self._http.post(
            "/v1/control/synthetic-runs",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, SyntheticRunReceipt, {401: Problem, 403: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def start_ticket_workflow(
        self,
        ticket_id: UUID,
        request: WorkflowStartRequest,
        *,
        command_id: UUID,
    ) -> WorkflowReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/workflow/start",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, WorkflowReceipt, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def transfer_ticket_custody(
        self,
        ticket_id: UUID,
        request: CustodyTransferRequest,
        *,
        command_id: UUID,
    ) -> TicketCommandResult:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/custody",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, TicketCommandResult, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def transition_workflow(
        self,
        ticket_id: UUID,
        request: WorkflowTransitionRequest,
        *,
        command_id: UUID,
    ) -> WorkflowReceipt:
        response = self._http.post(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/workflow/transition",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(command_id, ticket_id=ticket_id),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                },
            ),
        )
        return _response(response, WorkflowReceipt, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def validate_company_bundle(
        self,
        request: CompanyBundleRequest,
    ) -> CompanyBundleValidationResult:
        response = self._http.post(
            "/v1/company/bundle/validate",
            content=request.model_dump_json(),
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                    "Content-Type": "application/json",
                },
            ),
        )
        return _response(response, CompanyBundleValidationResult, {401: Problem, 403: Problem, 422: Problem})

    def _auth_headers(self) -> dict[str, str]:
        if self._credential is None:
            return {"Accept": "application/json"}
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._credential}",
        }

    def _context(self, command_id: UUID, *, ticket_id: UUID | None = None) -> TelemetryContext:
        if self._telemetry is not None:
            payload = self._telemetry.model_dump(mode="json", by_alias=True, exclude_none=True)
            payload["command_id"] = str(command_id)
            payload["ticket_id"] = str(ticket_id) if ticket_id is not None else None
            return TelemetryContext.model_validate(payload)
        return TelemetryContext(
            schema_id="ctower.telemetry-context/v1",
            trace_id=secrets.token_hex(16),
            span_id=secrets.token_hex(8),
            trace_flags=1,
            correlation_id=str(command_id),
            causation_id=str(command_id),
            tenant_id="unresolved",
            actor_id="unresolved",
            command_id=str(command_id),
            ticket_id=str(ticket_id) if ticket_id is not None else None,
        )

    def _telemetry_headers(
        self, context: TelemetryContext, headers: dict[str, str]
    ) -> dict[str, str]:
        return {
            **headers,
            "X-Ctower-Telemetry-Context": context.model_dump_json(by_alias=True),
        }


def _response[ModelT: BaseModel](
    response: httpx.Response,
    model: type[ModelT],
    problem_models: Mapping[int, type[BaseModel]],
) -> ModelT:
    if response.is_success:
        return model.model_validate_json(response.content)
    content_type = response.headers.get("content-type", "").partition(";")[0]
    if content_type != "application/problem+json":
        raise httpx.HTTPStatusError(
            "ctower returned a non-problem failure", request=response.request, response=response
        )
    problem_model = problem_models.get(response.status_code)
    if problem_model is None:
        raise httpx.HTTPStatusError(
            "ctower returned an undeclared failure status",
            request=response.request,
            response=response,
        )
    problem = problem_model.model_validate_json(response.content)
    raise CtowerProblemError(cast(_ProblemModel, problem))
