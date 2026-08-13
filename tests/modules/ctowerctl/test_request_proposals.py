"""Closed CLI grammar for the five Request-maintenance proposal operations."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from ctower_client.models import (
    RequestMaintenanceProposalAppendRequest,
    RequestMaintenanceProposalConfirmRequest,
    RequestMaintenanceProposalRejectRequest,
)
from ctowerctl._parser import authored_command_names, parse_arguments
from ctowerctl._request_commands import build_mutation

__all__: tuple[str, ...] = ()

_COMMANDS = {
    "request proposal append",
    "request proposal confirm",
    "request proposal list",
    "request proposal reject",
    "request proposal review",
}


def test_request_proposal_cli_names_are_real_authored_commands() -> None:
    assert authored_command_names() >= _COMMANDS


def test_proposal_decisions_build_generated_boundaries() -> None:
    proposal_id = uuid4()
    confirm = parse_arguments(
        [
            "request",
            "proposal",
            "confirm",
            str(proposal_id),
            "--expected-version",
            "1",
        ]
    )
    reject = parse_arguments(
        [
            "request",
            "proposal",
            "reject",
            str(proposal_id),
            "--expected-version",
            "1",
        ]
    )

    assert isinstance(build_mutation(confirm).request, RequestMaintenanceProposalConfirmRequest)
    reject_request = build_mutation(reject).request
    assert isinstance(reject_request, RequestMaintenanceProposalRejectRequest)
    assert reject_request.reason is None


def test_proposal_append_loads_one_strict_json_document(tmp_path: Path) -> None:
    input_file = tmp_path / "proposal.json"
    input_file.write_text(json.dumps(_append_payload()), encoding="utf-8")
    arguments = parse_arguments(["request", "proposal", "append", "--input", str(input_file)])

    assert isinstance(build_mutation(arguments).request, RequestMaintenanceProposalAppendRequest)

    input_file.write_text(json.dumps({**_append_payload(), "proposer": str(uuid4())}))
    with pytest.raises(ValueError):
        build_mutation(arguments)


def _append_payload() -> dict[str, object]:
    return {
        "basis": "recorded-evidence",
        "evidence": [
            {
                "event_digest": "sha256:" + "a" * 64,
                "event_id": str(uuid4()),
                "event_kind": "request.changed",
                "kind": "record-event",
            }
        ],
        "kind": "keep",
        "project_key": "ctower",
        "source_record_position": 10,
        "target_expected_version": 1,
        "target_request_id": str(uuid4()),
        "target_text": "Keep this exact Request.",
    }
