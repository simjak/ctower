"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:@@CONTRACT_SHA256@@
"""

from __future__ import annotations

from types import TracebackType
from typing import Self
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import BaseModel

from ctower_client.models import (
    BootstrapReceipt,
    BootstrapRequest,
    CustodyTransferRequest,
    Problem,
    TicketCommandResult,
    TicketCreateRequest,
    TicketResource,
    TimelineResponse,
)

__all__ = ["CtowerClient", "CtowerProblemError"]


class CtowerProblemError(Exception):
    """Typed RFC 9457 response from ctower."""

    def __init__(self, problem: Problem) -> None:
        self.problem = problem
        super().__init__(f"{problem.code}: {problem.detail}")


class CtowerClient:
    """Thin synchronous client generated from the authored HTTP contract."""

    def __init__(
        self,
        base_url: str,
        *,
        credential: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._credential = credential
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

    def bootstrap_first_tenant(
        self,
        request: BootstrapRequest,
        *,
        command_id: UUID,
        capability: str,
    ) -> BootstrapReceipt:
        response = self._http.post(
            "/v1/bootstrap/first-tenant",
            content=request.model_dump_json(),
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": str(command_id),
                "X-Ctower-Bootstrap-Capability": capability,
            },
        )
        return _response(response, BootstrapReceipt)

    def create_ticket(
        self, request: TicketCreateRequest, *, command_id: UUID
    ) -> TicketCommandResult:
        response = self._http.post(
            "/v1/tickets",
            content=request.model_dump_json(),
            headers=self._command_headers(command_id),
        )
        return _response(response, TicketCommandResult)

    def get_ticket(self, ticket_id: UUID) -> TicketResource:
        response = self._http.get(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}", headers=self._auth_headers()
        )
        return _response(response, TicketResource)

    def get_ticket_timeline(self, ticket_id: UUID) -> TimelineResponse:
        response = self._http.get(
            f"/v1/tickets/{quote(str(ticket_id), safe='')}/timeline",
            headers=self._auth_headers(),
        )
        return _response(response, TimelineResponse)

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
            headers=self._command_headers(command_id),
        )
        return _response(response, TicketCommandResult)

    def _auth_headers(self) -> dict[str, str]:
        if self._credential is None:
            return {"Accept": "application/json"}
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._credential}",
        }

    def _command_headers(self, command_id: UUID) -> dict[str, str]:
        return {
            **self._auth_headers(),
            "Content-Type": "application/json",
            "Idempotency-Key": str(command_id),
        }


def _response[ModelT: BaseModel](response: httpx.Response, model: type[ModelT]) -> ModelT:
    if response.is_success:
        return model.model_validate_json(response.content)
    content_type = response.headers.get("content-type", "").partition(";")[0]
    if content_type != "application/problem+json":
        raise httpx.HTTPStatusError(
            "ctower returned a non-problem failure", request=response.request, response=response
        )
    raise CtowerProblemError(Problem.model_validate_json(response.content))
