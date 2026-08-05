"""Explicit generated-client attention-finding command builders."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from ctower_client.models import AppendFindingRequest, FindingDispositionRequest
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    """Build one explicit generated attention-finding request selected by authored CLI spelling."""

    cli_name = cast(str, arguments.cli_name)
    if cli_name == "attention finding append":
        return _append(arguments)
    if cli_name == "attention finding disposition":
        return _disposition(arguments)
    raise ValueError("usage: unsupported attention mutation")


def mutation_command_names() -> frozenset[str]:
    """Expose the closed attention-finding mutation inventory for contract parity."""

    return frozenset({"attention finding append", "attention finding disposition"})


def _append(arguments: argparse.Namespace) -> MutationPayload:
    request = AppendFindingRequest(
        subject_ticket_id=cast(UUID, arguments.subject_ticket_id),
        kind_key=cast(str, arguments.kind_key),
        reason_code=cast(str, arguments.reason_code),
        effective_owner=arguments.effective_owner,
        recommendation=cast(str, arguments.recommendation),
        alternatives=tuple(cast(list[str], arguments.alternatives)),
        consequence=cast(str, arguments.consequence),
        deadline=arguments.deadline,
        dedupe_key=cast(str, arguments.dedupe_key),
        source_facts=tuple(cast(list[str], arguments.source_facts)),
    )
    return MutationPayload(request=request, path_parameters={})


def _disposition(arguments: argparse.Namespace) -> MutationPayload:
    request = FindingDispositionRequest(
        outcome=arguments.outcome,
        reason=cast(str, arguments.reason),
    )
    return MutationPayload(
        request=request,
        path_parameters={"finding_id": str(cast(UUID, arguments.finding_id))},
    )
