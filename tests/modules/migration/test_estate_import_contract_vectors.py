"""Contract and refusal vectors for estate-import preparation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest

from ctower_api.estate_import_company import (
    _company_refusal,
    _existing_company_result,
    _from_replay,
)
from ctower_api.estate_import_contracts import (
    CompanyRecordAppend,
    _company_import_command,
    _import_timestamp,
    _InboxImportPlan,
    _knowledge_import_command,
    _required_text,
)
from ctower_api.estate_import_support import (
    _digest_json,
    _generic_manifest_projection,
    _persist_source_only_message,
)
from ctower_api.estate_imports import PostgresEstateImports
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.artifacts import ArtifactError

__all__: tuple[str, ...] = ()


class _Connection:
    def __init__(self, response: Mapping[str, object] | None) -> None:
        self.response = response

    def execute(self, *_args: object, **_kwargs: object) -> _Result:
        return _Result(self.response)


class _Result:
    def __init__(self, response: Mapping[str, object] | None) -> None:
        self.response = response

    def fetchone(self) -> Mapping[str, object] | None:
        return self.response


class _Transaction:
    def __init__(self) -> None:
        self.refused: RecordProblem | None = None

    def refuse(self, *args: object, **_kwargs: object) -> None:
        self.refused = cast(RecordProblem, args[4])


def _actor() -> Actor:
    return Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)


def _company_row(source_ref: str = "escapes.jsonl#1") -> dict[str, object]:
    return {
        "record_type": "escape",
        "natural_key": "escape:one",
        "occurred_on": "2026-08-15",
        "seat": "unknown-owner",
        "source_ref": source_ref,
        "imported_at": "2026-08-15T12:00:00+00:00",
        "payload": {"summary": "one"},
        "content_sha256": "sha256:" + "1" * 64,
    }


def _ruling_row(source_ref: str = "rulings.md#1") -> dict[str, object]:
    verbatim = "Use the durable path."
    digest = hashlib.sha256(verbatim.encode()).hexdigest()
    return {
        "source_ref": source_ref,
        "verbatim": verbatim,
        "recorded_at": "2026-08-15T12:00:00+00:00",
        "content_sha256": f"sha256:{digest}",
    }


def _knowledge_row(source_ref: str = "decisions/1") -> dict[str, object]:
    body = "The decision is durable."
    digest = hashlib.sha256(body.encode()).hexdigest()
    return {
        "document_id": str(uuid4()),
        "source_ref": source_ref,
        "title": "Decision",
        "body": body,
        "recorded_at": "2026-08-15T12:00:00+00:00",
        "content_sha256": f"sha256:{digest}",
    }


def _artifact(tier: str, rows: list[Mapping[str, object]]) -> dict[str, object]:
    projection = [_generic_manifest_projection(tier, row) for row in rows]
    artifact: dict[str, object] = {
        "batches": [
            {
                "batch_index": 0,
                "source_count": len(rows),
                "batch_digest": _digest_json(projection),
            }
        ]
    }
    if tier == "agreed_decisions":
        artifact["project_key"] = "ctower"
    return artifact


def _assert_problem(result: object, code: str) -> None:
    assert isinstance(result, RecordProblem)
    assert result.code == code


@pytest.mark.parametrize(
    "overrides",
    [
        {"record_type": "request"},
        {"natural_key": ""},
        {"natural_key": "x" * 257},
        {"seat": "Unknown Owner"},
        {"payload": ()},
        {"imported_at": datetime.fromisoformat("2026-08-15T12:00:00")},
    ],
)
def test_company_record_append_rejects_contract_violations(
    overrides: dict[str, object],
) -> None:
    fields: dict[str, object] = {
        "client_command_id": uuid4(),
        "record_type": "escape",
        "natural_key": "escape:one",
        "occurred_on": "2026-08-15",
        "seat": "unknown-owner",
        "payload": (("summary", "one"),),
        "source_ref": "escapes.jsonl#1",
        "imported_at": datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    }
    fields.update(overrides)

    with pytest.raises(ValueError, match="company record"):
        CompanyRecordAppend(**fields)  # type: ignore[arg-type]


def test_command_translation_rejects_company_payload_and_knowledge_types() -> None:
    actor = _actor()
    with pytest.raises(ValueError, match="payload"):
        _company_import_command(actor, {**_company_row(), "payload": {}})
    with pytest.raises(ValueError, match="payload values"):
        _company_import_command(actor, {**_company_row(), "payload": {"summary": 1}})

    knowledge = _knowledge_row()
    with pytest.raises(TypeError, match="knowledge scope"):
        _knowledge_import_command(actor, {**knowledge, "scope": 1})
    with pytest.raises(TypeError, match="knowledge scope"):
        _knowledge_import_command(actor, {**knowledge, "project_key": 1})


def test_required_text_and_import_timestamp_fail_closed() -> None:
    with pytest.raises(ValueError, match="field"):
        _required_text({}, "source_ref")
    with pytest.raises(ValueError, match="field"):
        _required_text({"source_ref": ""}, "source_ref")
    with pytest.raises(TypeError, match="timestamp"):
        _import_timestamp(12)
    with pytest.raises(ValueError, match="timezone-aware"):
        _import_timestamp("2026-08-15T12:00:00")


def test_prepare_tier_rejects_unknown_tier_and_ruling_batch_edges() -> None:
    importer = PostgresEstateImports("unused", {}, parity_signer=None)
    actor = _actor()
    command_id = uuid4()

    unknown = importer._prepare_tier(
        cast(Any, _Connection(None)),
        actor,
        tier="unknown",
        artifact={},
        batch_index=0,
        rows=[],
        command_id=command_id,
    )
    _assert_problem(unknown, "estate-import-invalid")

    row = _ruling_row()
    valid_artifact = _artifact("agreed_decisions", [row])
    missing_project = dict(valid_artifact)
    missing_project.pop("project_key")
    _assert_problem(
        importer._prepare_ruling_batch(actor, missing_project, 0, [row], command_id),
        "estate-import-project-required",
    )
    _assert_problem(
        importer._prepare_ruling_batch(
            actor,
            {"project_key": "ctower", "batches": []},
            0,
            [row],
            command_id,
        ),
        "estate-import-batch-invalid",
    )
    _assert_problem(
        importer._prepare_ruling_batch(
            actor,
            {"project_key": "ctower", "batches": [{"batch_index": 0, "source_count": 1}]},
            0,
            [{}],
            command_id,
        ),
        "estate-import-row-invalid",
    )
    duplicate = importer._prepare_ruling_batch(
        actor, _artifact("agreed_decisions", [row, dict(row)]), 0, [row, dict(row)], command_id
    )
    _assert_problem(duplicate, "estate-import-duplicate-source")
    batch = cast(list[Mapping[str, object]], valid_artifact["batches"])[0]
    tampered = {**valid_artifact, "batches": [{**batch, "batch_digest": "bad"}]}
    _assert_problem(
        importer._prepare_ruling_batch(actor, tampered, 0, [row], command_id),
        "estate-import-batch-digest-mismatch",
    )


def test_prepare_knowledge_batch_refuses_invalid_rows() -> None:
    importer = PostgresEstateImports("unused", {}, parity_signer=None)
    actor = _actor()
    command_id = uuid4()
    knowledge = _knowledge_row()

    _assert_problem(
        importer._prepare_knowledge_batch({}, 0, [knowledge], command_id, actor),
        "estate-import-batch-invalid",
    )
    _assert_problem(
        importer._prepare_knowledge_batch(
            _artifact("knowledge_documents", [knowledge]),
            0,
            [{}],
            command_id,
            actor,
        ),
        "estate-import-row-invalid",
    )
    knowledge_duplicate = importer._prepare_knowledge_batch(
        _artifact("knowledge_documents", [knowledge, dict(knowledge)]),
        0,
        [knowledge, dict(knowledge)],
        command_id,
        actor,
    )
    _assert_problem(knowledge_duplicate, "estate-import-duplicate-source")
    prohibited_body = "password = notarealsecret"
    prohibited = {
        **knowledge,
        "body": prohibited_body,
        "content_sha256": "sha256:" + hashlib.sha256(prohibited_body.encode()).hexdigest(),
    }
    _assert_problem(
        importer._prepare_knowledge_batch(
            _artifact("knowledge_documents", [prohibited]),
            0,
            [prohibited],
            command_id,
            actor,
        ),
        "prohibited-data-class",
    )
    knowledge_tampered = _artifact("knowledge_documents", [knowledge])
    knowledge_batch = cast(list[Mapping[str, object]], knowledge_tampered["batches"])[0]
    knowledge_tampered["batches"] = [{**knowledge_batch, "batch_digest": "tampered"}]
    _assert_problem(
        importer._prepare_knowledge_batch(knowledge_tampered, 0, [knowledge], command_id, actor),
        "estate-import-batch-digest-mismatch",
    )


def test_prepare_company_batch_refuses_invalid_rows() -> None:
    importer = PostgresEstateImports("unused", {}, parity_signer=None)
    actor = _actor()
    command_id = uuid4()
    company = _company_row()

    _assert_problem(
        importer._prepare_company_batch({}, 0, [company], command_id, actor),
        "estate-import-batch-invalid",
    )
    _assert_problem(
        importer._prepare_company_batch(
            _artifact("company_records", [company]),
            0,
            [{}],
            command_id,
            actor,
        ),
        "estate-import-row-invalid",
    )
    company_duplicate = importer._prepare_company_batch(
        _artifact("company_records", [company, dict(company)]),
        0,
        [company, dict(company)],
        command_id,
        actor,
    )
    _assert_problem(company_duplicate, "estate-import-duplicate-source")
    company_tampered = _artifact("company_records", [company])
    company_batch = cast(list[Mapping[str, object]], company_tampered["batches"])[0]
    company_tampered["batches"] = [{**company_batch, "batch_digest": "tampered"}]
    _assert_problem(
        importer._prepare_company_batch(company_tampered, 0, [company], command_id, actor),
        "estate-import-batch-digest-mismatch",
    )


def test_verified_manifest_rejects_missing_untrusted_and_malformed_signatures() -> None:
    importer = PostgresEstateImports("unused", {}, parity_signer=None)
    invalid_manifests = [
        {},
        {"signature": []},
        {"signature": {"key_ref": "ref", "key_version": "1"}},
        {"signature": {"key_ref": "ref", "key_version": 1}},
    ]
    for manifest in invalid_manifests:
        with pytest.raises(ArtifactError):
            importer._verified_manifest(cast(Mapping[str, object], manifest), "company_records")


def test_missing_parity_signer_is_a_durable_service_refusal() -> None:
    importer = PostgresEstateImports("unused", {}, parity_signer=None)
    transaction = _Transaction()
    actor = _actor()
    result = importer._require_parity_signer(
        cast(Any, transaction), actor, uuid4(), b"digest", datetime(2026, 8, 15, tzinfo=UTC)
    )

    _assert_problem(result, "estate-import-parity-signer-unavailable")
    assert transaction.refused is result


def _company_command() -> CompanyRecordAppend:
    row = _company_row()
    return _company_import_command(_actor(), row)


def test_company_refusal_and_existing_record_result_cover_conflict_replay() -> None:
    actor = _actor()
    command = _company_command()
    refused = _company_refusal(cast(Any, _Connection({"kind": "commander"})), actor, command)
    _assert_problem(refused, "estate-import-operator-required")

    payload_sha256 = hashlib.sha256(
        json.dumps({"summary": "one"}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    imported_at = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    existing = {
        "record_id": uuid4(),
        "occurred_on": command.occurred_on,
        "seat": command.seat,
        "payload_sha256": bytes.fromhex(payload_sha256),
        "source_ref": command.source_ref,
        "imported_at": imported_at,
    }
    same = _existing_company_result(existing, command, payload_sha256)
    assert not isinstance(same, RecordProblem)
    assert same.already_present is True
    conflict = _existing_company_result(
        {**existing, "seat": "another-seat"}, command, payload_sha256
    )
    _assert_problem(conflict, "company-record-conflict")

    replay = _from_replay({"response_body": same.response_payload()})
    assert replay.already_present is True
    with pytest.raises(TypeError, match="response body"):
        _from_replay({"response_body": []})


def test_source_only_inbox_replay_is_idempotent_and_conflict_is_refused() -> None:
    actor = _actor()
    message_id = uuid4()
    subject = "Subject"
    body = "Body"
    content_digest = hashlib.sha256(
        json.dumps({"subject": subject, "body": body}, sort_keys=True).encode()
    ).hexdigest()
    row: dict[str, object] = {
        "message_id": str(message_id),
        "source_ref": "inbox/1",
        "source_sender": "unknown-sender",
        "source_recipient": "unknown-recipient",
        "sent_at": "2026-08-15T12:00:00+00:00",
        "subject": subject,
        "body": body,
        "read_state": "read",
        "content_sha256": f"sha256:{content_digest}",
    }
    plan = _InboxImportPlan(
        row=row,
        source_sender="unknown-sender",
        source_recipient="unknown-recipient",
        sender=None,
        recipient=None,
        command=None,
        source_only=True,
    )
    existing = {
        "message_id": message_id,
        "source_sender": "unknown-sender",
        "source_recipient": "unknown-recipient",
        "sent_at": datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        "subject": subject,
        "body": body,
        "read_state": "read",
        "content_sha256": bytes.fromhex(content_digest),
    }
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)

    replay = _persist_source_only_message(
        cast(Any, _Connection(existing)), actor, plan, uuid4(), now
    )
    conflict = _persist_source_only_message(
        cast(Any, _Connection({**existing, "body": "different"})),
        actor,
        plan,
        uuid4(),
        now,
    )

    assert replay is None
    assert isinstance(conflict, RecordProblem)
    assert conflict.code == "estate-import-source-conflict"
