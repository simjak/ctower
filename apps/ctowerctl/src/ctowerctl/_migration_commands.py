"""Explicit generated-client calls for I1.7A reads and refusing phase stubs."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import (
    CtowerProjectMigrationStubRequest,
    ProjectDeliveryView,
)

__all__: tuple[str, ...] = ()


def execute_online_stub(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    """Invoke one authored online-only operation without touching the replay spool."""

    cli_name = cast(str, arguments.cli_name)
    request = CtowerProjectMigrationStubRequest(
        cutover_id=cast(UUID, arguments.cutover_id),
        input_digest=cast(str, arguments.input_digest),
    )
    command_id = cast(UUID, arguments.command_id)
    if cli_name in {
        "migration ctower-project inventory",
        "migration ctower-project export",
        "migration ctower-project plan",
        "migration ctower-project import",
    }:
        return _execute_source_stub(cli_name, client, request, command_id)
    return _execute_cutover_stub(cli_name, client, request, command_id)


def _execute_source_stub(
    cli_name: str,
    client: CtowerClient,
    request: CtowerProjectMigrationStubRequest,
    command_id: UUID,
) -> BaseModel:
    if cli_name == "migration ctower-project inventory":
        return client.inventory_ctower_project_migration(request, command_id=command_id)
    if cli_name == "migration ctower-project export":
        return client.export_ctower_project_migration(request, command_id=command_id)
    if cli_name == "migration ctower-project plan":
        return client.plan_ctower_project_migration(request, command_id=command_id)
    if cli_name == "migration ctower-project import":
        return client.import_ctower_project_migration(request, command_id=command_id)
    raise ValueError("usage: unsupported ctower-project source stub")


def _execute_cutover_stub(
    cli_name: str,
    client: CtowerClient,
    request: CtowerProjectMigrationStubRequest,
    command_id: UUID,
) -> BaseModel:
    if cli_name == "migration ctower-project reconcile":
        return client.reconcile_ctower_project_migration(request, command_id=command_id)
    if cli_name == "migration ctower-project prepare":
        return client.prepare_ctower_project_cutover(request, command_id=command_id)
    if cli_name == "migration ctower-project commit-development-epoch":
        return client.commit_ctower_project_development_epoch(request, command_id=command_id)
    raise ValueError("usage: unsupported ctower-project cutover stub")


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    """Invoke one real I1.7A read."""

    cli_name = cast(str, arguments.cli_name)
    if cli_name == "migration ctower-project verify":
        return client.get_ctower_project_cutover_health()
    if cli_name == "project delivery query":
        return client.get_project_delivery(cast(str, arguments.project_key))
    raise ValueError("usage: unsupported I1.7A query")


def delivery_text(view: ProjectDeliveryView) -> str:
    """Render deterministic compact rows without percentages or hidden state."""

    lines = [("CHECKPOINT  STATE       PROOF  FRESHNESS      CONFIDENCE           OWNER  OUTCOME")]
    for row in view.rows:
        coverage = f"{row.criteria.proven}/{row.criteria.declared}"
        lines.append(
            f"{row.checkpoint_key:<10}  {row.headline_state:<10}  {coverage:<5}  "
            f"{row.freshness:<13}  {row.confidence:<19}  "
            f"{row.accountable_owner}  {row.outcome}"
        )
        lines.append(
            "  reasons="
            + ",".join(row.derivation_reasons)
            + " sources="
            + ",".join(row.source_ids)
            + f" watermark={row.projection_watermark}/{row.source_watermark}"
        )
    return "\n".join(lines) + "\n"


def mutation_command_names() -> frozenset[str]:
    """Return only the explicit online-only, unspoolable phase stubs."""

    return frozenset(
        {
            "migration ctower-project inventory",
            "migration ctower-project export",
            "migration ctower-project plan",
            "migration ctower-project import",
            "migration ctower-project reconcile",
            "migration ctower-project prepare",
            "migration ctower-project commit-development-epoch",
        }
    )


def query_command_names() -> frozenset[str]:
    """Return the two generated-client-backed I1.7A reads."""

    return frozenset(
        {
            "migration ctower-project verify",
            "project delivery query",
        }
    )
