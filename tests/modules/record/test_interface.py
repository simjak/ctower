"""Record Module value behavior through its public Interface."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from ctower_kernel.record import CustodyCommand, RecordProblem
from ctower_kernel.record.postgres import PostgresRecord


def test_postgres_adapter_is_owned_by_record_module() -> None:
    assert PostgresRecord.__module__ == "ctower_kernel.record.postgres"


__all__: tuple[str, ...] = ()


def test_version_problem_serializes_stable_rfc_9457_extensions() -> None:
    command_id = uuid4()
    problem = RecordProblem(
        code="version-conflict",
        detail="The ticket changed.",
        status=409,
        title="Ticket version conflict",
        command_id=command_id,
        current_version=7,
    )

    assert problem.response_payload() == {
        "code": "version-conflict",
        "command_id": str(command_id),
        "current_version": 7,
        "detail": "The ticket changed.",
        "status": 409,
        "title": "Ticket version conflict",
        "type": "https://ctower.dev/problems/version-conflict",
    }


def test_custody_command_is_immutable_and_includes_target_aggregate_in_digest_payload() -> None:
    command = CustodyCommand(
        client_command_id=uuid4(),
        expected_version=3,
        from_custodian_id=uuid4(),
        protected_transfer=True,
        reason="Accountable handoff",
        ticket_id=uuid4(),
        to_custodian_id=uuid4(),
    )

    assert command.request_payload()["ticket_id"] == str(command.ticket_id)
    with pytest.raises(FrozenInstanceError):
        command.reason = "rewritten"  # type: ignore[misc]
