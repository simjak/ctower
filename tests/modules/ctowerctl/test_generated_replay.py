"""Generated registry is the sole replay routing and model boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from ctower_client import CtowerClient, CtowerProblemError
from ctower_client.models import (
    DurabilityState,
    Priority,
    SourceReference,
    TicketCommandResult,
    TicketCreateRequest,
    TicketResource,
)
from ctowerctl._generated_replay import GeneratedReplayExecutor
from ctowerctl.spool import ServerRefusal, SpoolCommand

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE_ENTITY = 422
PII_MARKER = "jane.doe+ct180@example.invalid"
BEARER_MARKER = "Bearer synthetic-refusal-probe-not-a-credential"


@dataclass(slots=True)
class _ProblemStub:
    code: str
    command_id: UUID | None
    detail: str
    status: int
    title: str


class _TicketClient:
    def __init__(self, result: TicketCommandResult | _ProblemStub) -> None:
        self.result = result
        self.calls: list[tuple[TicketCreateRequest, UUID]] = []

    def create_ticket(
        self,
        request: TicketCreateRequest,
        *,
        command_id: UUID,
    ) -> TicketCommandResult:
        self.calls.append((request, command_id))
        if isinstance(self.result, _ProblemStub):
            raise CtowerProblemError(self.result)
        return self.result


def test_generated_registry_reconstructs_exact_request_and_stable_command_id() -> None:
    command_id = uuid4()
    request = _request()
    client = _TicketClient(_result(command_id, state=DurabilityState.ACCEPTED))
    executor = GeneratedReplayExecutor(cast(CtowerClient, client))

    response = executor.execute(
        SpoolCommand(
            operation_id="createTicket",
            request_body=request.model_dump(mode="json"),
            command_id=command_id,
        )
    )

    assert client.calls == [(request, command_id)]
    assert response.command_id == command_id
    assert response.durability_state == "accepted"
    assert response.status_code == HTTP_OK
    assert response.response is not None


def test_generated_problem_is_permanent_and_keeps_the_refusal_the_server_named() -> None:
    command_id = uuid4()
    problem = _ProblemStub(
        code="tenant-scope-denied",
        command_id=command_id,
        detail="Authored safe detail.",
        status=403,
        title="Tenant scope denied",
    )
    executor = GeneratedReplayExecutor(cast(CtowerClient, _TicketClient(problem)))

    response = executor.execute(
        SpoolCommand(
            operation_id="createTicket",
            request_body=_request().model_dump(mode="json"),
            command_id=command_id,
        )
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert response.problem_code == "tenant_scope_denied"
    assert response.response == {"code": "tenant-scope-denied", "status": 403}
    assert response.refusal == ServerRefusal(status=403, name="tenant_scope_denied")
    assert cast(object, executor.observations[command_id].problem) is problem


def test_schema_valid_refusal_body_never_becomes_a_persistable_refusal() -> None:
    """A reachable origin may say anything; only the allowlisted name may be kept."""

    command_id = uuid4()
    problem = _ProblemStub(
        code="unauthorized",
        command_id=command_id,
        detail=f"Custody refused for {PII_MARKER} presenting {BEARER_MARKER}.",
        status=403,
        title=f"Initial custody refused for {PII_MARKER}",
    )
    executor = GeneratedReplayExecutor(cast(CtowerClient, _TicketClient(problem)))

    response = executor.execute(
        SpoolCommand(
            operation_id="createTicket",
            request_body=_request().model_dump(mode="json"),
            command_id=command_id,
        )
    )

    persistable = response.model_dump_json()
    assert response.refusal == ServerRefusal(status=403, name="unauthorized")
    assert PII_MARKER not in persistable
    assert BEARER_MARKER not in persistable
    assert sorted(ServerRefusal.model_fields) == ["name", "status"]


def test_refusal_code_outside_the_authored_allowlist_keeps_only_a_slug() -> None:
    """A server ahead of this CLI's contract is named as unrecognized, not quoted."""

    command_id = uuid4()
    problem = _ProblemStub(
        code="future-refusal-code",
        command_id=command_id,
        detail=f"Authored safe detail naming {PII_MARKER}.",
        status=403,
        title="Future refusal",
    )
    executor = GeneratedReplayExecutor(cast(CtowerClient, _TicketClient(problem)))

    response = executor.execute(
        SpoolCommand(
            operation_id="createTicket",
            request_body=_request().model_dump(mode="json"),
            command_id=command_id,
        )
    )

    assert response.refusal == ServerRefusal(
        status=403,
        name="unrecognized_refusal:future_refusal_code",
    )
    assert PII_MARKER not in response.model_dump_json()


def test_forbidden_or_unknown_registry_operation_never_enters_spool() -> None:
    for operation_id in ("getTicket", "bootstrapFirstTenant", "inventedOperation"):
        with pytest.raises(ValidationError):
            SpoolCommand(
                operation_id=operation_id,
                path_parameters={},
                request_body={},
                command_id=uuid4(),
            )


def test_invalid_stored_request_is_a_permanent_schema_observation() -> None:
    command_id = uuid4()
    executor = GeneratedReplayExecutor(
        cast(CtowerClient, _TicketClient(_result(command_id, state=DurabilityState.ACCEPTED)))
    )

    response = executor.execute(
        SpoolCommand(
            operation_id="createTicket",
            request_body={"title": "incomplete"},
            command_id=command_id,
        )
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert response.problem_code == "operation_schema_invalid"


def _request() -> TicketCreateRequest:
    return TicketCreateRequest(
        initial_custodian_id=uuid4(),
        priority=Priority.P1,
        source=SourceReference(kind="test", ref="test:generated-replay"),
        title="Generated replay",
    )


def _result(command_id: UUID, *, state: DurabilityState) -> TicketCommandResult:
    return TicketCommandResult(
        command_id=command_id,
        durability_state=state,
        event_ids=(uuid4(),),
        ticket=TicketResource(
            created_at=datetime(2026, 7, 24, tzinfo=UTC),
            custodian_id=uuid4(),
            durability_state=state,
            priority=Priority.P1,
            source=SourceReference(kind="test", ref="test:generated-replay"),
            ticket_id=uuid4(),
            title="Generated replay",
            version=1,
        ),
    )
