"""Exact reviewer graph refusal evidence for PostgreSQL migration tests."""

from __future__ import annotations

import json
from typing import Literal, Protocol
from uuid import uuid4

from ctower_client.models import CtowerProjectAliasPlanBindRequest, CtowerProjectImportRun
from ctower_kernel.migration import Migration
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    canonical_digest,
)
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner

from ._postgres import Database, semantic_counts
from ._reviewed import ReviewedSource

__all__ = ["assert_export_graph_refusals", "assert_plan_graph_refusals"]


class _RunContext(Protocol):
    @property
    def source(self) -> ReviewedSource: ...

    @property
    def created(self) -> CtowerProjectImportRun: ...

    @property
    def migration(self) -> Migration: ...

    @property
    def operator(self) -> Actor: ...

    @property
    def alternate_signer(self) -> ArtifactSigner: ...


def assert_export_graph_refusals(context: _RunContext, database: Database) -> None:
    request = context.source.export_request(context.created.run_id)
    malformed = request.model_copy(
        update={"export_equality_artifact": canonical_bytes({"invalid": True}).decode()}
    )
    export_a = json.loads(request.export_a_artifact)
    export_a["artifact_digest"] = f"sha256:{'0' * 64}"
    bad_export_digest = request.model_copy(
        update={"export_a_artifact": canonical_bytes(export_a).decode()}
    )
    equality = _reseal(
        context,
        request.export_equality_artifact,
        "report_digest",
        {"cutover_id": str(uuid4())},
    )
    rebound = request.model_copy(
        update={
            "equality_report_digest": equality["report_digest"],
            "export_equality_artifact": canonical_bytes(equality).decode(),
        }
    )
    bad_inventory = request.model_copy(update={"inventory_a_digest": f"sha256:{'0' * 64}"})
    alternate = request.model_copy(
        update={
            "export_equality_artifact": _resign(
                context.alternate_signer,
                request.export_equality_artifact,
                "report_digest",
            )
        }
    )
    for candidate in (malformed, bad_export_digest, rebound, bad_inventory, alternate):
        before = semantic_counts(database)
        refused = context.migration.bind_export_equality(
            context.operator,
            candidate,
            command_id=uuid4(),
            telemetry=_telemetry(context.operator),
        )
        assert isinstance(refused, RecordProblem)
        assert semantic_counts(database) == before


def assert_plan_graph_refusals(
    context: _RunContext,
    database: Database,
    plan_request: CtowerProjectAliasPlanBindRequest,
) -> None:
    plan_nonexhaustive = json.loads(plan_request.import_plan_artifact)
    plan_nonexhaustive["operation_count"] += 1
    plan_batch = json.loads(plan_request.import_plan_artifact)
    plan_batch["batches"][0]["batch_index"] = 9
    plan_command = json.loads(plan_request.import_plan_artifact)
    plan_command["batches"][0]["operations"][0]["identity"]["command_id"] = str(uuid4())
    batch = plan_command["batches"][0]
    batch["batch_digest"] = canonical_digest(
        {key: value for key, value in batch.items() if key != "batch_digest"}
    )
    candidates = (
        plan_request.model_copy(update={"alias_map_digest": f"sha256:{'0' * 64}"}),
        _plan_candidate(context, plan_request, plan_nonexhaustive),
        _plan_candidate(context, plan_request, plan_batch),
        _plan_candidate(context, plan_request, plan_command),
        _artifact_candidate(
            context,
            plan_request,
            "alias_map_artifact",
            "map_digest",
            {"attention_required": 1},
        ),
        _artifact_candidate(
            context,
            plan_request,
            "fence_registry_artifact",
            "registry_digest",
            {"cutover_id": str(uuid4())},
        ),
        plan_request.model_copy(
            update={
                "alias_map_artifact": _resign(
                    context.alternate_signer,
                    plan_request.alias_map_artifact,
                    "map_digest",
                )
            }
        ),
        plan_request.model_copy(
            update={
                "import_plan_artifact": _resign(
                    context.alternate_signer,
                    plan_request.import_plan_artifact,
                    "plan_digest",
                )
            }
        ),
        plan_request.model_copy(
            update={
                "fence_registry_artifact": _resign(
                    context.alternate_signer,
                    plan_request.fence_registry_artifact,
                    "registry_digest",
                )
            }
        ),
    )
    for candidate in candidates:
        before = semantic_counts(database)
        refused = context.migration.bind_alias_plan(
            context.operator,
            candidate,
            command_id=uuid4(),
            telemetry=_telemetry(context.operator),
        )
        assert isinstance(refused, RecordProblem)
        assert semantic_counts(database) == before


def _plan_candidate(
    context: _RunContext,
    request: CtowerProjectAliasPlanBindRequest,
    plan: dict[str, object],
) -> CtowerProjectAliasPlanBindRequest:
    unsigned = {
        key: value for key, value in plan.items() if key not in {"plan_digest", "signature"}
    }
    sealed = context.source.fixture.signer.seal(unsigned, "plan_digest")
    return request.model_copy(update={"import_plan_artifact": canonical_bytes(sealed).decode()})


def _artifact_candidate(
    context: _RunContext,
    request: CtowerProjectAliasPlanBindRequest,
    field: Literal["alias_map_artifact", "fence_registry_artifact"],
    digest_field: Literal["map_digest", "registry_digest"],
    update: dict[str, object],
) -> CtowerProjectAliasPlanBindRequest:
    artifact = getattr(request, field)
    sealed = _reseal(context, artifact, digest_field, update)
    return request.model_copy(update={field: canonical_bytes(sealed).decode()})


def _reseal(
    context: _RunContext,
    artifact_text: str,
    digest_field: Literal["report_digest", "map_digest", "registry_digest"],
    update: dict[str, object],
) -> dict[str, object]:
    artifact = json.loads(artifact_text)
    unsigned = {
        key: value for key, value in artifact.items() if key not in {digest_field, "signature"}
    }
    unsigned.update(update)
    return context.source.fixture.signer.seal(unsigned, digest_field)


def _resign(signer: ArtifactSigner, artifact_text: str, digest_field: str) -> str:
    artifact = json.loads(artifact_text)
    body = {key: value for key, value in artifact.items() if key not in {digest_field, "signature"}}
    return canonical_bytes(signer.seal(body, digest_field)).decode()


def _telemetry(actor: Actor) -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=command_id,
    )
