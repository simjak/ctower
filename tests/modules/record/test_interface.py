"""Record Module value behavior through its public Interface."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from ctower_kernel.record import CustodyCommand, RecordProblem
from ctower_kernel.record.events import canonical_event_bytes, event_digest
from ctower_kernel.record.postgres import PostgresRecord, provision_bootstrap

ROOT = Path(__file__).parents[3]


def test_postgres_adapter_is_owned_by_record_module() -> None:
    assert PostgresRecord.__module__ == "ctower_kernel.record.postgres"


def test_record_event_authority_matches_authored_canonical_vectors() -> None:
    document = json.loads(
        (ROOT / "contracts/domain/events/canonical-vectors.json").read_text(encoding="utf-8")
    )
    vectors = cast(list[dict[str, object]], document["vectors"])

    for vector in vectors:
        event = cast(dict[str, object], vector["event"])
        assert canonical_event_bytes(event).decode() == vector["canonical_json"]
        assert f"sha256:{event_digest(event).hex()}" == vector["event_hash"]


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


def test_bootstrap_provision_rejects_capability_above_authored_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_connect(_dsn: str) -> None:
        raise AssertionError("invalid capability reached persistence")

    monkeypatch.setattr("ctower_kernel.record._setup_sql.psycopg.connect", unexpected_connect)

    with pytest.raises(ValueError, match="at most 256 characters"):
        provision_bootstrap(
            "postgresql://unused",
            capability_input=StringIO("x" * 257 + "\n"),
            allowed_origin="127.0.0.1",
            expires_at=datetime.now(UTC),
        )
