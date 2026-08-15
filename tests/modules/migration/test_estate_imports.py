"""RED-first shared estate-import authority and parity vectors."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ctower_kernel.inbox.models import InboxAcknowledgementState
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_api.estate_import_contracts import (
    CompanyRecordAppend,
    _inbox_acknowledge_command,
    _inbox_send_command,
    _knowledge_import_command,
    _ruling_import_command,
)
from ctower_api.estate_import_support import (
    _inbox_batch_header,
    _same_record,
)
from ctower_kernel.record.events import EventOrigin
from ctower_kernel.record.inbox_events import InboxParticipant
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.estate_imports import (
    EstateImportWorkflow,
    EstateRefusal,
    build_estate_manifest,
    load_seat_mapping,
    parity_report,
    verify_estate_manifest_text,
)

__all__: tuple[str, ...] = ()

_SHA = "sha256:" + "1" * 64


class _Signer:
    def seal(self, value: Mapping[str, Any], digest_field: str) -> dict[str, Any]:
        result = dict(value)
        result[digest_field] = _SHA
        result["signature"] = {
            "algorithm": "Ed25519",
            "signed_digest": _SHA,
            "key_ref": "signing-key-ref:test",
            "key_version": 1,
            "public_key_digest": _SHA,
            "signature": "A" * 86 + "==",
        }
        return result


def test_manifest_builder_refuses_an_empty_source() -> None:
    with pytest.raises(EstateRefusal) as raised:
        build_estate_manifest(
            tier="company_records",
            source_identity={
                "namespace": "mission-control:estate",
                "source_path": "state/escapes.jsonl",
                "source_sha256": _SHA,
            },
            rows=[],
            seat_mapping_digest=None,
            signer=_Signer(),
        )

    assert raised.value.code == "source-empty"


def test_seat_mapping_digest_is_verified_before_rows_are_accepted(tmp_path: Path) -> None:
    mapping = {
        "schema": "ctower.estate-seat-mapping/v1",
        "mapping_digest": _SHA,
        "mappings": [
            {"source_seat": "engineer", "disposition": "mapped", "target_seat_key": "engineer"}
        ],
    }
    unsigned = dict(mapping)
    unsigned.pop("mapping_digest", None)
    mapping["mapping_digest"] = (
        "sha256:" + hashlib.sha256(rfc8785.dumps(cast(Any, unsigned))).hexdigest()
    )
    path = tmp_path / "seat-map.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    loaded = load_seat_mapping(path)
    assert loaded["engineer"].target_seat_key == "engineer"

    mapping["mapping_digest"] = "sha256:" + "2" * 64
    path.write_text(json.dumps(mapping), encoding="utf-8")
    with pytest.raises(EstateRefusal) as raised:
        load_seat_mapping(path)
    assert raised.value.code == "seat-mapping-digest-mismatch"


def test_manifest_verification_rejects_a_batch_count_mismatch() -> None:
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:test", 1, private_key)
    manifest = signer.seal(
        {
            "schema": "ctower.estate-import-manifest/v1",
            "tier": "company_records",
            "source_identity": {
                "namespace": "mission-control:estate",
                "source_path": "state/escapes.jsonl",
                "source_sha256": _SHA,
            },
            "counts": {"source_rows": 1},
            "batches": [{"batch_index": 0, "batch_digest": _SHA, "source_count": 2}],
        },
        "manifest_digest",
    )

    with pytest.raises(EstateRefusal) as raised:
        verify_estate_manifest_text(
            rfc8785.dumps(manifest).decode("utf-8"),
            tier="company_records",
            source_row_count=1,
            public_key=private_key.public_key(),
        )
    assert raised.value.code == "manifest-count-mismatch"


def test_inbox_estate_migration_preserves_source_sender_and_recipient() -> None:
    migration_path = Path(__file__).parents[3] / (
        "packages/ctower-kernel/migrations/0069_estate_import_idempotency.sql"
    )
    migration = migration_path.read_text(encoding="utf-8")

    assert "ADD COLUMN source_sender text" in migration
    assert "ADD COLUMN source_recipient text" in migration
    assert "length(source_sender) BETWEEN 1 AND 128" in migration
    assert "length(source_recipient) BETWEEN 1 AND 128" in migration
    assert "CREATE TABLE estate_import_source_only_messages" in migration
    assert (
        "source_only_disposition text NOT NULL CHECK (source_only_disposition = 'source_only')"
        in migration
    )


def test_inbox_import_commands_preserve_source_identity_and_read_timestamp() -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    sender = InboxParticipant(uuid4(), "mapped-sender")
    recipient = InboxParticipant(uuid4(), "operator")
    sent_at = datetime(2026, 8, 14, 20, 30, tzinfo=UTC)
    message_id = uuid4()
    row = {
        "message_id": str(message_id),
        "source_ref": "inbox.jsonl#17",
        "source_sender": "mapped-sender",
        "source_recipient": "operator",
        "sent_at": sent_at.isoformat(),
        "subject": "subject",
        "body": "body",
        "read_state": "read",
        "content_sha256": "sha256:" + "1" * 64,
    }

    send = _inbox_send_command(actor, row, sender=sender, recipient=recipient)
    acknowledge = _inbox_acknowledge_command(send)

    assert send.message_id == message_id
    assert send.sent_at == sent_at
    assert send.source_ref == "inbox.jsonl#17"
    assert send.source_sender == "mapped-sender"
    assert send.source_recipient == "operator"
    assert send.origin is EventOrigin.ESTATE_IMPORT
    assert acknowledge.state is InboxAcknowledgementState.READ
    assert acknowledge.recorded_at == sent_at
    assert acknowledge.origin is EventOrigin.ESTATE_IMPORT


def test_estate_imports_have_a_distinct_operator_authority_origin() -> None:
    """Estate imports cannot reuse the restricted Request-import origin."""
    assert EventOrigin.ESTATE_IMPORT.value == "estate_import"
    assert EventOrigin.ESTATE_IMPORT is not EventOrigin.MIGRATION_IMPORTER


def test_ruling_import_command_preserves_source_timestamp_and_origin() -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    recorded_at = datetime(2026, 8, 14, 20, 30, tzinfo=UTC)
    verbatim = "# Agreed\n\nKeep the decision."
    row = {
        "source_ref": "agreed-decision.md",
        "verbatim": verbatim,
        "recorded_at": recorded_at.isoformat(),
        "content_sha256": "sha256:" + hashlib.sha256(verbatim.encode()).hexdigest(),
    }

    command = _ruling_import_command(actor, row, project_key="ctower")

    assert command.source_ref == "agreed-decision.md"
    assert command.recorded_at == recorded_at
    assert command.project_key == "ctower"
    assert command.origin is EventOrigin.ESTATE_IMPORT


def test_knowledge_import_command_preserves_document_identity_and_source_metadata() -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    document_id = uuid4()
    recorded_at = datetime(2026, 8, 14, 20, 30, tzinfo=UTC)
    body = "Reference body."
    row = {
        "document_id": str(document_id),
        "source_ref": "policy/reference.md",
        "title": "Reference",
        "body": body,
        "recorded_at": recorded_at.isoformat(),
        "content_sha256": "sha256:" + __import__("hashlib").sha256(body.encode()).hexdigest(),
    }

    command = _knowledge_import_command(actor, row)

    assert command.document_id == document_id
    assert command.source_ref == "policy/reference.md"
    assert command.recorded_at == recorded_at
    assert command.origin is EventOrigin.ESTATE_IMPORT


def test_estate_batch_header_refuses_negative_batch_index() -> None:
    problem = _inbox_batch_header(
        {"batches": [{"batch_index": -1, "source_count": 1}]},
        -1,
        1,
        uuid4(),
    )

    assert isinstance(problem, RecordProblem)
    assert problem.code == "estate-import-batch-invalid"


def test_company_record_replay_ignores_new_import_timestamp() -> None:
    command = CompanyRecordAppend(
        uuid4(),
        "escape",
        "escape:one",
        "2026-07-27",
        "commander",
        (("defect", "example"),),
        "state/escapes.jsonl#1",
        datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )

    assert (
        _same_record(
            {
                "occurred_on": "2026-07-27",
                "seat": "commander",
                "payload_sha256": bytes.fromhex("0" * 64),
                "source_ref": "state/escapes.jsonl#1",
                "imported_at": datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
            },
            command,
            "0" * 64,
        )
        is True
    )


def test_parity_report_rejects_more_imports_than_source_rows() -> None:
    manifest = {
        "manifest_digest": _SHA,
        "batches": [{"batch_index": 0, "batch_digest": _SHA, "source_count": 1}],
    }

    with pytest.raises(EstateRefusal) as raised:
        parity_report(
            tier="company_records",
            manifest=manifest,
            source_count=1,
            imported_count=2,
            batch_imports=[(0, 2)],
            sampled=[("state/escapes.jsonl#1", _SHA)],
            source_only_owners=[],
            signer=_Signer(),
        )
    assert raised.value.code == "parity-count-mismatch"


def test_workflow_refuses_non_operator_before_import_or_closure() -> None:
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:test", 1, private_key)
    rows = _workflow_rows()
    manifest = _workflow_manifest(signer, rows)
    observed: list[str] = []

    def batch_importer(_index: int, _rows: Sequence[Mapping[str, Any]]) -> int:
        observed.append("import")
        return 1

    with pytest.raises(EstateRefusal) as raised:
        EstateImportWorkflow(private_key.public_key()).execute(
            actor_kind="commander",
            tier="company_records",
            manifest_text=rfc8785.dumps(manifest).decode(),
            rows=rows,
            batch_importer=batch_importer,
            emit_report=lambda _report: observed.append("report"),
            close_source=lambda: observed.append("close"),
            signer=signer,
        )

    assert raised.value.code == "operator-required"
    assert observed == []


def test_workflow_emits_parity_before_source_closure() -> None:
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:test", 1, private_key)
    rows = _workflow_rows()
    manifest = _workflow_manifest(signer, rows)
    observed: list[str] = []

    report = EstateImportWorkflow(private_key.public_key()).execute(
        actor_kind="operator",
        tier="company_records",
        manifest_text=rfc8785.dumps(manifest).decode(),
        rows=rows,
        batch_importer=lambda _index, _rows: 1,
        emit_report=lambda _report: observed.append("report"),
        close_source=lambda: observed.append("close"),
        signer=signer,
    )

    assert report["emitted_before_closure"] is True
    assert report["source_count"] == report["imported_count"] == 1
    assert observed == ["report", "close"]


def _workflow_rows() -> list[dict[str, Any]]:
    return [
        {
            "_disposition": "source_only",
            "source_seat": "unknown-owner",
            "source_ref": "state/escapes.jsonl#1",
            "content_sha256": _SHA,
        }
    ]


def _workflow_manifest(signer: ArtifactSigner, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return signer.seal(
        build_estate_manifest(
            tier="company_records",
            source_identity={
                "namespace": "mission-control:estate",
                "source_path": "state/escapes.jsonl",
                "source_sha256": _SHA,
            },
            rows=rows,
            seat_mapping_digest=None,
            signer=None,
        ),
        "manifest_digest",
    )
