"""Explicit generated-client builders for protected intake mutations."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from ctower_client.models import (
    IntakeIntent,
    IntakePromotionIntent,
    IntakePromotionRequest,
    IntakeSubmitRequest,
    IntakeTaint,
    Priority,
    SourceReference,
)
from ctowerctl._command_types import MutationPayload
from ctowerctl._input import read_text

__all__: tuple[str, ...] = ()

_CONTENT_MAX_BYTES = 262_144


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    """Build only the two authored generated intake requests."""

    cli_name = cast(str, arguments.cli_name)
    if cli_name == "intake submit":
        return _submit(arguments)
    if cli_name == "intake promote":
        return _promote(arguments)
    raise ValueError("usage: unsupported intake mutation")


def mutation_command_names() -> frozenset[str]:
    return frozenset({"intake submit", "intake promote"})


def _submit(arguments: argparse.Namespace) -> MutationPayload:
    priority = cast(str | None, arguments.priority)
    request = IntakeSubmitRequest(
        content=read_text(
            arguments.content_file,
            maximum_bytes=_CONTENT_MAX_BYTES,
            label="intake content",
        ),
        expected_thread_version=cast(int | None, arguments.expected_thread_version),
        expected_ticket_version=cast(int | None, arguments.expected_ticket_version),
        initial_custodian_id=cast(UUID | None, arguments.initial_custodian_id),
        intent=IntakeIntent(cast(str, arguments.intent)),
        priority=Priority(priority) if priority is not None else None,
        project_key=cast(str, arguments.project_key),
        source=SourceReference(
            kind=cast(str, arguments.source_kind),
            ref=cast(str, arguments.source_ref),
        ),
        taint=IntakeTaint(cast(str, arguments.taint)),
        target_ticket_id=cast(UUID | None, arguments.target_ticket_id),
        thread_id=cast(UUID | None, arguments.thread_id),
        title=cast(str | None, arguments.title),
    )
    return MutationPayload(request=request, path_parameters={})


def _promote(arguments: argparse.Namespace) -> MutationPayload:
    priority = cast(str | None, arguments.priority)
    request = IntakePromotionRequest(
        expected_thread_version=cast(int, arguments.expected_thread_version),
        expected_ticket_version=cast(int | None, arguments.expected_ticket_version),
        initial_custodian_id=cast(UUID | None, arguments.initial_custodian_id),
        intent=IntakePromotionIntent(cast(str, arguments.intent)),
        priority=Priority(priority) if priority is not None else None,
        target_ticket_id=cast(UUID | None, arguments.target_ticket_id),
        title=cast(str | None, arguments.title),
    )
    return MutationPayload(
        request=request,
        path_parameters={
            "inbound_event_id": str(cast(UUID, arguments.inbound_event_id)),
        },
    )
