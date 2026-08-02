"""Closed online-only CLI evidence for project-seat credential mutations."""

from __future__ import annotations

import argparse
import io
import json
from typing import Self
from uuid import UUID, uuid4

import pytest

from ctower_client.models import (
    CredentialScope,
    DurabilityState,
    SeatCredentialIssueRequest,
    SeatCredentialReceipt,
    SeatCredentialRevocationRequest,
)
from ctower_client.operations import OperationSpec, SpoolPolicy, operation_for_cli
from ctowerctl import interface
from ctowerctl._output import ExitCode
from ctowerctl.spool import Spool

__all__: tuple[str, ...] = ()


def test_cli_executes_issue_and_revoke_online_without_touching_spool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _CredentialClient()
    monkeypatch.setattr(interface, "CtowerClient", lambda *_args, **_kwargs: client)

    def spool_refused(*_args: object, **_kwargs: object) -> Spool:
        raise AssertionError("online-only credential command touched the replay spool")

    monkeypatch.setattr(Spool, "for_origin", spool_refused)
    issue_id, revoke_id = uuid4(), uuid4()
    issue_output, revoke_output = io.StringIO(), io.StringIO()

    issue_code = interface.main(
        _issue_arguments(issue_id),
        stdin=io.StringIO("ephemeral-authority\n"),
        stdout=issue_output,
        stderr=io.StringIO(),
    )
    revoke_code = interface.main(
        _revoke_arguments(client.credential_id, revoke_id),
        stdin=io.StringIO("ephemeral-authority\n"),
        stdout=revoke_output,
        stderr=io.StringIO(),
    )

    assert issue_code == int(ExitCode.TEMPORARY)
    assert revoke_code == int(ExitCode.TEMPORARY)
    assert json.loads(issue_output.getvalue())["state"] == "active"
    assert json.loads(revoke_output.getvalue())["state"] == "revoked"
    assert [call[0] for call in client.calls] == ["issue", "revoke"]
    assert [call[2] for call in client.calls] == [issue_id, revoke_id]


def test_credential_dispatch_requires_forbidden_spool_metadata() -> None:
    operation = operation_for_cli("credential seat issue")
    assert operation is not None
    unsafe = OperationSpec(
        operation_id=operation.operation_id,
        client_method=operation.client_method,
        method=operation.method,
        path=operation.path,
        request_model=operation.request_model,
        response_model=operation.response_model,
        cli_names=operation.cli_names,
        mutation=operation.mutation,
        spool_policy=SpoolPolicy.ALLOWED,
        principal=operation.principal,
        refusal_only=operation.refusal_only,
    )
    with pytest.raises(ValueError, match="forbidden spool metadata"):
        interface._execute_online_credential(
            "https://ctower.example",
            "ephemeral-authority",
            argparse.Namespace(),
            unsafe,
        )


def _issue_arguments(command_id: UUID) -> list[str]:
    return [
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
        "--seat-key",
        "manibo-commander",
    ]


def _revoke_arguments(credential_id: UUID, command_id: UUID) -> list[str]:
    return [
        "--base-url",
        "https://ctower.example",
        "credential",
        "seat",
        "revoke",
        str(credential_id),
        "--command-id",
        str(command_id),
        "--reason",
        "rotation",
    ]


class _CredentialClient:
    def __init__(self) -> None:
        self.credential_id = uuid4()
        self.principal_id = uuid4()
        self.calls: list[tuple[str, object, UUID]] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def issue_seat_credential(
        self,
        request: SeatCredentialIssueRequest,
        *,
        command_id: UUID,
    ) -> SeatCredentialReceipt:
        self.calls.append(("issue", request, command_id))
        return self._receipt(command_id, "active")

    def revoke_seat_credential(
        self,
        credential_id: UUID,
        request: SeatCredentialRevocationRequest,
        *,
        command_id: UUID,
    ) -> SeatCredentialReceipt:
        assert credential_id == self.credential_id
        self.calls.append(("revoke", request, command_id))
        return self._receipt(command_id, "revoked")

    def _receipt(self, command_id: UUID, state: str) -> SeatCredentialReceipt:
        return SeatCredentialReceipt.model_validate(
            {
                "command_id": command_id,
                "credential_id": self.credential_id,
                "durability_state": DurabilityState.DURABILITY_PENDING,
                "event_ids": (uuid4(),),
                "principal_id": self.principal_id,
                "project_key": "manibo",
                "scopes": (CredentialScope.CAPTURE,),
                "seat_key": "manibo-commander",
                "state": state,
            }
        )
