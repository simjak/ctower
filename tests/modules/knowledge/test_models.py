"""Typed knowledge command, result, document, and event behavior."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest

from ctower_kernel.knowledge import Knowledge
from ctower_kernel.knowledge.models import (
    KnowledgeAddCommand,
    KnowledgeAddResult,
    KnowledgeDocument,
    KnowledgeDocumentListResult,
    add_result_from_committed,
)
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.knowledge_events import KnowledgeDocumentRegisteredPayload
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

COMMAND_ID = UUID("00000000-0000-4000-8000-000000000001")
DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000002")
EVENT_ID = UUID("00000000-0000-4000-8000-000000000003")
PRINCIPAL_ID = UUID("00000000-0000-4000-8000-000000000004")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000005")
NOW = datetime(2026, 8, 7, 13, 37, tzinfo=UTC)


def test_command_result_and_documents_have_stable_wire_payloads() -> None:
    command = _command()
    result = KnowledgeAddResult(
        COMMAND_ID,
        DOCUMENT_ID,
        EVENT_ID,
        NOW,
        "org",
        "Operations handbook",
    )
    document = KnowledgeDocument(
        DOCUMENT_ID,
        "org",
        "Operations handbook",
        "Keep the runbook current.",
        NOW,
        PRINCIPAL_ID,
    )

    assert command.request_payload() == {
        "body": "Keep the runbook current.",
        "scope": "org",
        "title": "Operations handbook",
    }
    assert result.response_payload() == {
        "command_id": str(COMMAND_ID),
        "document_id": str(DOCUMENT_ID),
        "durability_state": "durability_pending",
        "event_ids": [str(EVENT_ID)],
        "project_key": None,
        "registered_at": NOW.isoformat(),
        "scope": "org",
        "source_ref": None,
        "title": "Operations handbook",
    }
    assert add_result_from_committed(result.response_payload()) == result
    assert document.response_payload() == {
        "body": "Keep the runbook current.",
        "document_id": str(DOCUMENT_ID),
        "project_key": None,
        "registered_at": NOW.isoformat(),
        "registered_by": str(PRINCIPAL_ID),
        "scope": "org",
        "source_ref": None,
        "title": "Operations handbook",
    }
    assert KnowledgeDocumentListResult("org", (document,)).response_payload() == {
        "documents": [document.response_payload()],
        "project_key": None,
        "scope": "org",
    }


def test_command_rejects_malformed_fields() -> None:
    with pytest.raises(TypeError, match="identity must be a UUID"):
        _command(client_command_id=cast(UUID, "not-a-uuid"))
    with pytest.raises(ValueError, match="scope must be org or project"):
        _command(scope="team")
    with pytest.raises(ValueError, match=r"requires exactly body\+title or source_ref"):
        _command(source_ref="operations")
    with pytest.raises(ValueError, match="body is outside"):
        _command(body=None)
    with pytest.raises(ValueError, match="source_ref is outside"):
        _command(body=None, source_ref="../escape", title=None)
    assert _command(body=None, source_ref="operations", title=None).request_payload() == {
        "scope": "org",
        "source_ref": "operations",
    }
    with pytest.raises(ValueError, match="project scope requires"):
        _command(scope="project")
    assert _command(scope="project", project_key="ctower").request_payload()["project_key"] == (
        "ctower"
    )
    with pytest.raises(ValueError, match="title is outside"):
        _command(title="")
    with pytest.raises(ValueError, match="title is outside"):
        _command(title=cast(str, 7))
    with pytest.raises(ValueError, match="title is outside"):
        _command(title="t" * 1025)
    with pytest.raises(ValueError, match="body is outside"):
        _command(body="")
    with pytest.raises(ValueError, match="body is outside"):
        _command(body=cast(str, 7))
    with pytest.raises(ValueError, match="body is outside"):
        _command(body="b" * 1_048_577)


def test_results_and_documents_require_authored_time_and_scope() -> None:
    naive = datetime(2026, 8, 7, 13, 37)  # noqa: DTZ001
    with pytest.raises(ValueError, match="timestamps must be timezone-aware"):
        KnowledgeAddResult(COMMAND_ID, DOCUMENT_ID, EVENT_ID, naive, "org", "Title")
    with pytest.raises(ValueError, match="timestamps must be timezone-aware"):
        KnowledgeDocument(DOCUMENT_ID, "org", "Title", "Body", naive, PRINCIPAL_ID)
    with pytest.raises(ValueError, match="scope must be org or project"):
        KnowledgeDocument(DOCUMENT_ID, "team", "Title", "Body", NOW, PRINCIPAL_ID)


def test_registered_payload_is_strict_and_serializes_exactly() -> None:
    payload = KnowledgeDocumentRegisteredPayload(
        body="Keep the runbook current.",
        document_id=DOCUMENT_ID,
        registered_by=PRINCIPAL_ID,
        registered_at=NOW,
        scope="project",
        title="Operations handbook",
        project_key="ctower",
    )

    assert payload.to_mapping() == {
        "body": "Keep the runbook current.",
        "document_id": str(DOCUMENT_ID),
        "project_key": "ctower",
        "registered_by": str(PRINCIPAL_ID),
        "registered_at": NOW.isoformat(),
        "scope": "project",
        "source_ref": None,
        "title": "Operations handbook",
    }
    with pytest.raises(TypeError, match="document_id must be a UUID"):
        replace(payload, document_id=cast(UUID, "not-a-uuid"))
    with pytest.raises(TypeError, match="registered_by must be a UUID"):
        replace(payload, registered_by=cast(UUID, "not-a-uuid"))
    with pytest.raises(ValueError, match="scope must be org or project"):
        replace(payload, scope="team")
    with pytest.raises(ValueError, match="title is outside"):
        replace(payload, title="")
    with pytest.raises(ValueError, match="title is outside"):
        replace(payload, title=cast(str, 7))
    with pytest.raises(ValueError, match="title is outside"):
        replace(payload, title="t" * 1025)
    with pytest.raises(ValueError, match="body is outside"):
        replace(payload, body="")
    with pytest.raises(ValueError, match="body is outside"):
        replace(payload, body=cast(str, 7))
    with pytest.raises(ValueError, match="body is outside"):
        replace(payload, body="b" * 1_048_577)


def test_registered_payload_rejects_string_and_naive_registered_at() -> None:
    with pytest.raises(TypeError, match="registered_at must be a datetime"):
        KnowledgeDocumentRegisteredPayload(
            body="Keep the runbook current.",
            document_id=DOCUMENT_ID,
            registered_by=PRINCIPAL_ID,
            registered_at=cast(datetime, NOW.isoformat()),  # a string, not a datetime
            scope="org",
            title="Operations handbook",
        )
    naive = datetime(2026, 8, 7, 13, 37)  # noqa: DTZ001
    with pytest.raises(ValueError, match="registered_at must be timezone-aware"):
        KnowledgeDocumentRegisteredPayload(
            body="Keep the runbook current.",
            document_id=DOCUMENT_ID,
            registered_by=PRINCIPAL_ID,
            registered_at=naive,
            scope="org",
            title="Operations handbook",
        )


def test_public_interface_forwards_typed_commands_and_reads() -> None:
    actor = Actor(PRINCIPAL_ID, TENANT_ID, PrincipalKind.COMMANDER)
    store = _Store()
    knowledge = Knowledge(store)

    assert (
        knowledge.register(
            actor,
            _command(),
            request_digest=bytes.fromhex("a1" * 32),
            now=NOW,
            telemetry=_telemetry(),
        )
        == store.result
    )
    assert knowledge.list_by_scope(actor, "org") == KnowledgeDocumentListResult(
        "org", (store.document,)
    )
    assert knowledge.get(actor, DOCUMENT_ID, scope="org") == store.document


def _command(**overrides: object) -> KnowledgeAddCommand:
    fields: dict[str, object] = {
        "body": "Keep the runbook current.",
        "client_command_id": COMMAND_ID,
        "scope": "org",
        "title": "Operations handbook",
    }
    return KnowledgeAddCommand(**{**fields, **overrides})  # type: ignore[arg-type]


def _telemetry() -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=str(COMMAND_ID),
        causation_id=str(COMMAND_ID),
        tenant_id=str(TENANT_ID),
        actor_id=str(PRINCIPAL_ID),
        command_id=str(COMMAND_ID),
    )


class _Store:
    def __init__(self) -> None:
        self.document = KnowledgeDocument(
            DOCUMENT_ID,
            "org",
            "Operations handbook",
            "Keep the runbook current.",
            NOW,
            PRINCIPAL_ID,
        )
        self.result = KnowledgeAddResult(
            COMMAND_ID,
            DOCUMENT_ID,
            EVENT_ID,
            NOW,
            "org",
            "Operations handbook",
        )

    def register(
        self,
        actor: Actor,
        command: KnowledgeAddCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> KnowledgeAddResult:
        assert (actor, command, request_digest, now, telemetry) == (
            Actor(PRINCIPAL_ID, TENANT_ID, PrincipalKind.COMMANDER),
            _command(),
            bytes.fromhex("a1" * 32),
            NOW,
            _telemetry(),
        )
        return self.result

    def list_by_scope(
        self, actor: Actor, scope: str, project_key: str | None = None
    ) -> KnowledgeDocumentListResult:
        assert (actor.tenant_id, scope, project_key) == (TENANT_ID, "org", None)
        return KnowledgeDocumentListResult(scope, (self.document,))

    def get(
        self,
        actor: Actor,
        document_id: UUID,
        *,
        scope: str,
        project_key: str | None = None,
    ) -> KnowledgeDocument:
        assert (actor.tenant_id, document_id, scope, project_key) == (
            TENANT_ID,
            DOCUMENT_ID,
            "org",
            None,
        )
        return self.document
