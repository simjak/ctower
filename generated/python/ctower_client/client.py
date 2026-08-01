"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:19abd7a3003df793c986fda7420df89ccac2127cab34e9cf3344279da01db82e
"""

from __future__ import annotations

from collections.abc import Mapping
import secrets
from types import TracebackType
from typing import Annotated, NoReturn, Protocol, Self, cast
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
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectCutoverHealth,
    CtowerProjectEpochRefusalRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportBatchResult,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRun,
    CtowerProjectImportRunCreateRequest,
    CtowerProjectMigrationReceipt,
    CtowerProjectReconciliationResult,
    CustodyTransferRequest,
    EvidenceRequest,
    FreezeCriteriaRequest,
    IntakeCommandResult,
    IntakePromotionRequest,
    IntakeSubmitRequest,
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


class _StatusProblemModel(_ProblemModel, Protocol):
    status: int


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
        return _response(response, {200: TicketCommentResult, 202: TicketCommentResult}, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: WorkReceipt, 202: WorkReceipt}, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def append_ctower_project_import_correction(
        self,
        request: CtowerProjectImportCorrectionRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectMigrationReceipt:
        response = self._http.post(
            "/v1/migrations/ctower-project/corrections",
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
        return _response(response, {201: CtowerProjectMigrationReceipt, 202: CtowerProjectMigrationReceipt}, {401: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: CompanyBundleCommandResult, 202: CompanyBundleCommandResult}, {401: Problem, 403: Problem, 409: Problem, 422: Problem, 503: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def apply_ctower_project_import_batch(
        self,
        request: CtowerProjectImportBatchRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectImportBatchResult:
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
        return _response(response, {200: CtowerProjectImportBatchResult, 202: CtowerProjectImportBatchResult}, {401: Problem, 403: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: WorkReceipt, 202: WorkReceipt}, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def bind_ctower_project_alias_plan(
        self,
        request: CtowerProjectAliasPlanBindRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectImportRun:
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
        return _response(response, {200: CtowerProjectImportRun, 202: CtowerProjectImportRun}, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def bind_ctower_project_export_equality(
        self,
        request: CtowerProjectExportEqualityBindRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectImportRun:
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
        return _response(response, {200: CtowerProjectImportRun, 202: CtowerProjectImportRun}, {401: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {201: BootstrapReceipt, 202: BootstrapReceipt}, {401: Problem, 403: Problem, 409: Problem, 410: Problem, 422: Problem})

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
        return _response(response, {200: WorkReceipt, 202: WorkReceipt}, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: WorkReceipt, 202: WorkReceipt}, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def commit_ctower_project_development_epoch(
        self,
        request: CtowerProjectEpochRefusalRequest,
        *,
        command_id: UUID,
    ) -> NoReturn:
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
        _refusal(response, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def create_ctower_project_import_run(
        self,
        request: CtowerProjectImportRunCreateRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectImportRun:
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
        return _response(response, {201: CtowerProjectImportRun, 202: CtowerProjectImportRun}, {401: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {201: TicketCommandResult, 202: TicketCommandResult}, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: CompanyBundleExportResult}, {401: Problem, 403: Problem, 404: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def finalize_ctower_project_import_run(
        self,
        request: CtowerProjectImportFinalizeRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectReconciliationResult:
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
        return _response(response, {200: CtowerProjectReconciliationResult, 202: CtowerProjectReconciliationResult}, {401: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: ProofReceipt, 202: ProofReceipt}, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def get_board(
        self,
        *,
        lane: str | None = None,
        priority: str | None = None,
        stage_key: str | None = None,
        custodian_id: UUID | None = None,
        assignee_id: UUID | None = None,
        source_kind: Annotated[str, Field(min_length=1, max_length=64)] | None = None,
        source_ref: Annotated[str, Field(min_length=1, max_length=256)] | None = None,
    ) -> BoardView:
        response = self._http.get(
            "/v1/board",
            params={**({"lane": lane} if lane is not None else {}), **({"priority": priority} if priority is not None else {}), **({"stage_key": stage_key} if stage_key is not None else {}), **({"custodian_id": str(custodian_id)} if custodian_id is not None else {}), **({"assignee_id": str(assignee_id)} if assignee_id is not None else {}), **({"source_kind": source_kind} if source_kind is not None else {}), **({"source_ref": source_ref} if source_ref is not None else {})},
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, {200: BoardView}, {401: Problem, 422: Problem})

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
        return _response(response, {200: ControlHealth}, {401: Problem})

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
        return _response(response, {200: CtowerProjectCutoverHealth}, {401: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def get_ctower_project_import_run(
        self,
        run_id: UUID,
    ) -> CtowerProjectImportRun:
        response = self._http.get(
            f"/v1/migrations/ctower-project/import-runs/{quote(str(run_id), safe='')}",
            headers=self._telemetry_headers(
                self._context(uuid4()),
                {
                    **self._auth_headers(),
                },
            ),
        )
        return _response(response, {200: CtowerProjectImportRun}, {401: Problem, 404: Problem})

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
        return _response(response, {200: ProjectDeliveryView}, {401: Problem, 404: Problem, 422: Problem})

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
        return _response(response, {200: SyntheticRunResource}, {401: Problem, 404: Problem, 422: Problem})

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
        return _response(response, {200: TicketResource}, {401: Problem, 404: Problem, 422: Problem})

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
        return _response(response, {200: TimelineResponse}, {401: Problem, 404: Problem, 422: Problem})

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
        return _response(response, {200: AssignmentList}, {401: Problem, 404: Problem, 422: Problem})

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
        return _response(response, {200: AuditPage}, {401: Problem, 404: Problem, 422: Problem})

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
        return _response(response, {200: CompanyBundlePlan}, {401: Problem, 403: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def prepare_ctower_project_cutover(
        self,
        request: CtowerProjectEpochRefusalRequest,
        *,
        command_id: UUID,
    ) -> NoReturn:
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
        _refusal(response, {401: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def promote_intake_event(
        self,
        inbound_event_id: UUID,
        request: IntakePromotionRequest,
        *,
        command_id: UUID,
    ) -> IntakeCommandResult:
        response = self._http.post(
            f"/v1/intake/events/{quote(str(inbound_event_id), safe='')}/promotion",
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
        return _response(response, {200: IntakeCommandResult, 202: IntakeCommandResult}, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 413: Problem, 422: Problem})

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
        return _response(response, {200: PoisonDispositionReceipt, 202: PoisonDispositionReceipt}, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: ProofReceipt, 202: ProofReceipt}, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: ProofReceipt, 202: ProofReceipt}, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def report_ctower_project_fence_observation(
        self,
        request: CtowerProjectFenceObservationRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectMigrationReceipt:
        response = self._http.post(
            "/v1/migrations/ctower-project/fence-observations",
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
        return _response(response, {201: CtowerProjectMigrationReceipt, 202: CtowerProjectMigrationReceipt}, {401: Problem, 403: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: WorkflowReceipt, 202: WorkflowReceipt}, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {201: SyntheticRunReceipt, 202: SyntheticRunReceipt}, {401: Problem, 403: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: WorkflowReceipt, 202: WorkflowReceipt}, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def submit_intake(
        self,
        request: IntakeSubmitRequest,
        *,
        command_id: UUID,
    ) -> IntakeCommandResult:
        response = self._http.post(
            "/v1/intake",
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
        return _response(response, {201: IntakeCommandResult, 202: IntakeCommandResult}, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 413: Problem, 422: Problem})

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
        return _response(response, {200: TicketCommandResult, 202: TicketCommandResult}, {401: Problem, 403: Problem, 404: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: WorkflowReceipt, 202: WorkflowReceipt}, {401: Problem, 404: Problem, 409: Problem, 422: Problem})

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
        return _response(response, {200: CompanyBundleValidationResult}, {401: Problem, 403: Problem, 422: Problem})

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
    success_models: Mapping[int, type[ModelT]],
    problem_models: Mapping[int, type[BaseModel]],
) -> ModelT:
    model = success_models.get(response.status_code)
    if model is not None:
        return model.model_validate_json(response.content)
    if response.is_success:
        raise httpx.HTTPStatusError(
            "ctower returned an undeclared success status",
            request=response.request,
            response=response,
        )
    _raise_problem(response, problem_models)


def _raise_problem(
    response: httpx.Response,
    problem_models: Mapping[int, type[BaseModel]],
) -> NoReturn:
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
    problem = cast(_StatusProblemModel, problem_model.model_validate_json(response.content))
    if problem.status != response.status_code:
        raise ValueError("Problem status does not match HTTP response status")
    raise CtowerProblemError(problem)


def _refusal(
    response: httpx.Response,
    problem_models: Mapping[int, type[BaseModel]],
) -> NoReturn:
    if response.is_success:
        raise httpx.HTTPStatusError(
            "refusal-only operation returned success",
            request=response.request,
            response=response,
        )
    _raise_problem(response, problem_models)
