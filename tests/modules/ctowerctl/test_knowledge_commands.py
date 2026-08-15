"""Unit tests for knowledge CLI command parsing and mutation building."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ctower_client.models import KnowledgeAddRequest
from ctowerctl._knowledge_commands import build_mutation
from ctowerctl._parser import parse_arguments

__all__: tuple[str, ...] = ()


def test_knowledge_add_accepts_recorded_at_timestamp() -> None:
    """--recorded-at is accepted and passed to the generated request."""
    command_id = uuid4()
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "knowledge",
            "add",
            "--command-id",
            str(command_id),
            "--scope",
            "org",
            "--source-ref",
            "ctower-knowledge",
            "--recorded-at",
            "2026-01-15T12:00:00+00:00",
        ]
    )
    payload = build_mutation(arguments)

    assert isinstance(payload.request, KnowledgeAddRequest)
    assert payload.request.recorded_at == datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    assert payload.path_parameters == {}


def test_knowledge_add_without_recorded_at_defaults_to_none() -> None:
    """Omitting --recorded-at keeps the request backward-compatible (None)."""
    command_id = uuid4()
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "knowledge",
            "add",
            "--command-id",
            str(command_id),
            "--scope",
            "org",
            "--source-ref",
            "ctower-knowledge",
        ]
    )
    payload = build_mutation(arguments)

    assert isinstance(payload.request, KnowledgeAddRequest)
    assert payload.request.recorded_at is None


def test_knowledge_add_recorded_at_flows_through_build_and_request() -> None:
    """Full flow: --recorded-at parses RFC 3339 and survives model_dump()."""
    command_id = uuid4()
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "knowledge",
            "add",
            "--command-id",
            str(command_id),
            "--scope",
            "org",
            "--source-ref",
            "ctower-knowledge",
            "--recorded-at",
            "2025-12-01T08:30:00Z",
        ]
    )
    payload = build_mutation(arguments)
    serialized = payload.request.model_dump(mode="json")

    assert serialized["recorded_at"] == "2025-12-01T08:30:00Z"
