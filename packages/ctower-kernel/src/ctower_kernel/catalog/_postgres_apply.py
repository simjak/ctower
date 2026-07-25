"""Serializable CompanyBundle apply over Record-owned command/event authority."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.catalog._canonical import normalized_bundle
from ctower_kernel.catalog._checkpoint_sql import materialize_checkpoints
from ctower_kernel.catalog._postgres_activation import insert_activation_facts
from ctower_kernel.catalog._postgres_events import catalog_events
from ctower_kernel.catalog._postgres_read import ActiveCatalog, load_active_catalog
from ctower_kernel.catalog._postgres_revisions import (
    RevisionState,
    insert_revisions,
    prepare_revisions,
)
from ctower_kernel.catalog.interface import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    CompanyBundlePlan,
)
from ctower_kernel.catalog.object_interface import CatalogObjectError
from ctower_kernel.catalog.service import CatalogPayloadStager, CatalogPolicy
from ctower_kernel.objects import ObjectStore
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def apply_bundle(
    dsn: str,
    actor: Actor,
    tenant_key: str,
    command: CompanyBundleApply,
    policy: CatalogPolicy,
    stager: CatalogPayloadStager,
    store: ObjectStore,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> CompanyBundleCommandResult | CatalogProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        reserved = _reserve_or_replay(
            transaction,
            actor,
            command,
            request_digest,
            now,
        )
        if reserved is not None:
            return reserved
        return _apply_reserved_bundle(
            connection,
            transaction,
            actor,
            tenant_key,
            command,
            policy,
            stager,
            store,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _apply_reserved_bundle(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    tenant_key: str,
    command: CompanyBundleApply,
    policy: CatalogPolicy,
    stager: CatalogPayloadStager,
    store: ObjectStore,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> CompanyBundleCommandResult | CatalogProblem:
    _lock_active_pointer(connection, actor.tenant_id)
    try:
        active = load_active_catalog(connection, actor.tenant_id, tenant_key, store)
    except CatalogObjectError:
        recovery = _problem(
            command,
            "bundle-recovery-unavailable",
            "Active Catalog payload recovery is unavailable.",
            status=503,
        )
        return _refuse(transaction, actor, command, request_digest, recovery, now)
    plan = policy.prepare_activation(
        tenant_key,
        command,
        active.active if active is not None else None,
    )
    if isinstance(plan, CatalogProblem):
        return _refuse(transaction, actor, command, request_digest, plan, now)
    try:
        staged = stager.stage(actor.tenant_id, command.bundle)
    except CatalogObjectError:
        recovery = _problem(
            command,
            "bundle-recovery-unavailable",
            "Catalog payload staging or read-back is unavailable.",
            status=503,
        )
        return _refuse(transaction, actor, command, request_digest, recovery, now)
    bundle = normalized_bundle(command.bundle)
    prepared = prepare_revisions(connection, actor, command, bundle, staged)
    if isinstance(prepared, CatalogProblem):
        return _refuse(transaction, actor, command, request_digest, prepared, now)
    insert_revisions(connection, actor, prepared, now=now)
    return _commit_bundle(
        connection,
        transaction,
        actor,
        command,
        bundle,
        prepared,
        active,
        plan,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )


def _commit_bundle(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: CompanyBundleApply,
    bundle: CompanyBundle,
    prepared: tuple[RevisionState, ...],
    active: ActiveCatalog | None,
    plan: CompanyBundlePlan,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> CompanyBundleCommandResult:
    prepared, commits = catalog_events(
        connection,
        actor,
        command,
        prepared,
        active_version=plan.base_version + 1,
        bundle_digest=plan.proposed_bundle_digest,
        plan_digest=plan.plan_digest,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    result = CompanyBundleCommandResult(
        command_id=command.client_command_id,
        event_ids=tuple(item.event.event_id for item in commits),
        active_version=plan.base_version + 1,
        bundle_digest=plan.proposed_bundle_digest,
        plan_digest=plan.plan_digest,
    )
    transaction.commit_batch(
        commits,
        response_body=cast(dict[str, object], result.response_payload()),
        status_code=200,
        telemetry=telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command.client_command_id),
        ),
        now=now,
        subjects=(("catalog", actor.tenant_id),),
    )
    insert_activation_facts(
        connection,
        actor,
        command,
        bundle,
        prepared,
        active,
        plan.checks,
        result=result,
        now=now,
    )
    materialize_checkpoints(connection, actor, bundle, prepared, now=now)
    return result


def _reserve_or_replay(
    transaction: RecordTransaction,
    actor: Actor,
    command: CompanyBundleApply,
    request_digest: bytes,
    now: datetime,
) -> CompanyBundleCommandResult | CatalogProblem | None:
    existing = transaction.reserve(
        actor.principal_id,
        command.client_command_id,
        request_digest,
    )
    if isinstance(existing, RecordProblem):
        return catalog_problem(existing)
    if existing is not None:
        return _result_from_payload(existing)
    pending = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        (("catalog", actor.tenant_id),),
        now=now,
    )
    return catalog_problem(pending) if pending is not None else None


def _lock_active_pointer(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID
) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"catalog-pointer:{tenant_id}",),
    )
    connection.execute(
        "SELECT 1 FROM company_bundle_active WHERE tenant_id = %s FOR UPDATE",
        (tenant_id,),
    ).fetchone()


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: CompanyBundleApply,
    request_digest: bytes,
    problem: CatalogProblem,
    now: datetime,
) -> CatalogProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        RecordProblem(
            code=problem.code,
            detail=problem.detail,
            status=problem.status,
            title=problem.title,
            command_id=problem.command_id,
        ),
        now=now,
    )
    return problem


def catalog_problem(problem: RecordProblem) -> CatalogProblem:
    return CatalogProblem(
        code=problem.code,
        detail=problem.detail,
        status=problem.status,
        title=problem.title,
        command_id=problem.command_id,
    )


def _problem(
    command: CompanyBundleApply,
    code: str,
    detail: str,
    *,
    status: int = 422,
) -> CatalogProblem:
    return CatalogProblem(
        code=code,
        detail=detail,
        status=status,
        title="Bundle refused",
        command_id=command.client_command_id,
    )


def _result_from_payload(payload: dict[str, object]) -> CompanyBundleCommandResult:
    stored = {key: value for key, value in payload.items() if key != "durability_state"}
    return CompanyBundleCommandResult.model_validate_json(json.dumps(stored))
