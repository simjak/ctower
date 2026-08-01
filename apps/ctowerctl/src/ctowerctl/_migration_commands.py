"""Explicit online-only generated-client calls for the ctower-project cutover."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectEpochRefusalRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRunCreateRequest,
    ProjectDeliveryView,
)

__all__: tuple[str, ...] = ()

_REQUEST_MODELS: dict[str, type[BaseModel]] = {
    "migration ctower-project inventory": CtowerProjectImportRunCreateRequest,
    "migration ctower-project export": CtowerProjectExportEqualityBindRequest,
    "migration ctower-project plan": CtowerProjectAliasPlanBindRequest,
    "migration ctower-project import": CtowerProjectImportBatchRequest,
    "migration ctower-project reconcile": CtowerProjectImportFinalizeRequest,
    "migration ctower-project correction append": CtowerProjectImportCorrectionRequest,
    "migration ctower-project fence observe": CtowerProjectFenceObservationRequest,
    "migration ctower-project prepare": CtowerProjectEpochRefusalRequest,
    "migration ctower-project commit-development-epoch": CtowerProjectEpochRefusalRequest,
}
_REFUSAL_COMMANDS = frozenset(
    {
        "migration ctower-project prepare",
        "migration ctower-project commit-development-epoch",
    }
)


def execute_online(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    """Validate one command-specific DTO and send it without replay spooling."""

    cli_name = cast(str, arguments.cli_name)
    model = _REQUEST_MODELS.get(cli_name)
    if model is None:
        raise ValueError("usage: unsupported ctower-project mutation")
    payload = model.model_validate_json(
        cast(Path, arguments.request_file).read_text(encoding="utf-8")
    )
    command_id = cast(UUID, arguments.command_id)
    if cli_name in {
        "migration ctower-project inventory",
        "migration ctower-project export",
        "migration ctower-project plan",
    }:
        return _execute_binding(cli_name, client, payload, command_id)
    return _execute_import_cutover(cli_name, client, payload, command_id)


def _execute_binding(
    cli_name: str,
    client: CtowerClient,
    payload: BaseModel,
    command_id: UUID,
) -> BaseModel:
    if cli_name == "migration ctower-project inventory":
        return client.create_ctower_project_import_run(
            cast(CtowerProjectImportRunCreateRequest, payload),
            command_id=command_id,
        )
    if cli_name == "migration ctower-project export":
        return client.bind_ctower_project_export_equality(
            cast(CtowerProjectExportEqualityBindRequest, payload),
            command_id=command_id,
        )
    return client.bind_ctower_project_alias_plan(
        cast(CtowerProjectAliasPlanBindRequest, payload),
        command_id=command_id,
    )


def _execute_import_cutover(
    cli_name: str,
    client: CtowerClient,
    payload: BaseModel,
    command_id: UUID,
) -> BaseModel:
    if cli_name == "migration ctower-project import":
        return client.apply_ctower_project_import_batch(
            cast(CtowerProjectImportBatchRequest, payload),
            command_id=command_id,
        )
    if cli_name == "migration ctower-project reconcile":
        return client.finalize_ctower_project_import_run(
            cast(CtowerProjectImportFinalizeRequest, payload),
            command_id=command_id,
        )
    if cli_name == "migration ctower-project correction append":
        return client.append_ctower_project_import_correction(
            cast(CtowerProjectImportCorrectionRequest, payload),
            command_id=command_id,
        )
    if cli_name == "migration ctower-project fence observe":
        return client.report_ctower_project_fence_observation(
            cast(CtowerProjectFenceObservationRequest, payload),
            command_id=command_id,
        )
    refusal = cast(CtowerProjectEpochRefusalRequest, payload)
    if cli_name == "migration ctower-project prepare":
        return client.prepare_ctower_project_cutover(refusal, command_id=command_id)
    if cli_name == "migration ctower-project commit-development-epoch":
        return client.commit_ctower_project_development_epoch(refusal, command_id=command_id)
    raise AssertionError("closed migration dispatch fell through")


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    """Invoke one exact migration or Project Delivery read."""

    cli_name = cast(str, arguments.cli_name)
    if cli_name == "migration ctower-project verify":
        return client.get_ctower_project_cutover_health()
    if cli_name == "migration ctower-project run get":
        return client.get_ctower_project_import_run(arguments.run_id)
    if cli_name == "project delivery query":
        return client.get_project_delivery(cast(str, arguments.project_key))
    raise ValueError("usage: unsupported ctower-project query")


def delivery_text(view: ProjectDeliveryView) -> str:
    """Render deterministic compact rows without percentages or hidden state."""

    headers = ("CHECKPOINT", "STATE", "CRITERIA", "SLOTS", "UNRESOLVED")
    summaries = tuple(
        (
            row.checkpoint_key,
            row.headline_state,
            f"{row.criteria.proven}/{row.criteria.declared}",
            f"{row.qualifying_stage_slots_filled}/{row.qualifying_stage_slots_required}",
            ",".join(row.qualifying_stage_unfilled_or_unknown_slot_keys) or "-",
        )
        for row in view.rows
    )
    widths = tuple(
        max((len(header), *(len(str(values[index])) for values in summaries)))
        for index, header in enumerate(headers)
    )
    lines = [
        f"company={view.company_key} project={view.project_key} "
        f"watermark={view.projection_record_position}/{view.source_record_position} "
        f"reconciled_at={view.reconciled_at.isoformat()} "
        f"freshness_due_at={view.freshness_due_at.isoformat()} "
        f"rebuild_generation={view.rebuild_generation} "
        f"semantic_digest={view.projection_semantic_digest}",
        _column_line(headers, widths),
    ]
    for row, summary in zip(view.rows, summaries, strict=True):
        lines.append(_column_line(summary, widths))
        lines.append(
            f"  label={row.checkpoint_label} owner={row.accountable_owner} outcome={row.outcome}"
        )
        lines.append(
            f"  freshness={row.freshness} confidence={row.confidence} health={row.health} "
            "sources="
            + ",".join(row.source_ids)
            + " reasons="
            + ",".join(row.derivation_reasons)
            + f" watermark={row.projection_watermark}/{row.source_watermark} "
            + f"row_digest={row.semantic_digest}"
        )
    return "\n".join(lines) + "\n"


def _column_line(values: tuple[str, ...], widths: tuple[int, ...]) -> str:
    padded = (value.ljust(width) for value, width in zip(values[:-1], widths[:-1], strict=True))
    return "  ".join((*padded, values[-1]))


def mutation_command_names() -> frozenset[str]:
    """Return the exact online-only, unspoolable mutation inventory."""

    return frozenset(_REQUEST_MODELS) - _REFUSAL_COMMANDS


def refusal_command_names() -> frozenset[str]:
    """Return the exact online-only, unspoolable non-mutating refusal inventory."""

    return _REFUSAL_COMMANDS


def query_command_names() -> frozenset[str]:
    """Return the exact generated-client-backed read inventory."""

    return frozenset(
        {
            "migration ctower-project verify",
            "migration ctower-project run get",
            "project delivery query",
        }
    )
