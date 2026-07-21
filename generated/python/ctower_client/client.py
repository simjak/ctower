"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:71152e641b41ee93136c346c04060769bcfd05c8bdfb8e009491efe2d666be3c
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
    BootstrapReceipt,
    BootstrapRequest,
    CustodyTransferRequest,
    EvidenceRequest,
    FreezeCriteriaRequest,
    Problem,
    ProofReceipt,
    ResolveCloseRequest,
    TelemetryContext,
    TicketCommandResult,
    TicketCreateRequest,
    TicketResource,
    TimelineResponse,
    VerdictRequest,
    WorkflowReceipt,
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
