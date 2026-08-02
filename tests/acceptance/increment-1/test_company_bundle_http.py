"""Authenticated HTTP composition for CompanyBundle and ticket comments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.catalog import (
    FileSchemas,
    InterruptingObjectStore,
    MemoryObjectStore,
    SimulatedProcessLoss,
    actor_for,
    apply_initial_bundle,
    assert_command_replay_precedes_adapters,
    assert_locked_plan_refusals_precede_adapters,
    assert_removal_refusal_precedes_adapters,
    minimal_bundle,
    telemetry_for,
)
from support.http import app_for as _app
from support.http import operator_headers as _headers
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_kernel.catalog import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    PostgresCatalog,
)

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_PENDING = 202
HTTP_FORBIDDEN = 403
HTTP_CONFLICT = 409
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_ENTITY = 422


def test_company_bundle_http_round_trip_preserves_read_only_and_atomic_boundaries(
    tenant: TenantFixture,
) -> None:
    before = _catalog_counts(tenant.database.admin_dsn)
    command_id = uuid4()
    with TestClient(_app(tenant)) as client:
        (
            refused,
            validated,
            planned,
            empty_export,
            applied,
            replay,
            exported,
            replanned,
        ) = _exercise_bundle_round_trip(client, tenant, command_id, before)

    assert (refused.status_code, refused.json()["code"]) == (
        HTTP_UNPROCESSABLE_ENTITY,
        "bundle-grant-refused",
    )
    assert validated.status_code == HTTP_OK
    assert validated.json()["valid"] is True
    assert planned.status_code == HTTP_OK
    assert (empty_export.status_code, empty_export.json()["code"]) == (
        HTTP_NOT_FOUND,
        "bundle-not-active",
    )
    assert applied.status_code == HTTP_PENDING
    assert replay.content == applied.content
    assert applied.json()["active_version"] == 1
    assert exported.status_code == HTTP_OK
    assert exported.json()["bundle_digest"] == applied.json()["bundle_digest"]
    assert exported.json()["metadata"]["command_id"] == str(command_id)
    assert replanned.status_code == HTTP_OK
    assert replanned.json()["actions"] == []
    assert replanned.json()["proposed_bundle_digest"] == applied.json()["bundle_digest"]


def _exercise_bundle_round_trip(
    client: TestClient,
    tenant: TenantFixture,
    command_id: UUID,
    before: tuple[int, int, int],
) -> tuple[Response, Response, Response, Response, Response, Response, Response, Response]:
    request: dict[str, object] = {"bundle": _tenant_bundle().model_dump(mode="json", by_alias=True)}
    refused, validated, planned, empty_export = _bundle_read_requests(client, tenant, request)
    assert _catalog_counts(tenant.database.admin_dsn) == before
    apply_request = {
        **request,
        "expected_active_version": 0,
        "plan_digest": planned.json()["plan_digest"],
    }
    applied = client.post(
        "/v1/company/bundle/apply",
        json=apply_request,
        headers=_headers(tenant, command_id=command_id),
    )
    replay = client.post(
        "/v1/company/bundle/apply",
        json=apply_request,
        headers=_headers(tenant, command_id=command_id),
    )
    exported = client.get("/v1/company/bundle/export", headers=_headers(tenant))
    replanned = client.post(
        "/v1/company/bundle/plan",
        json={"bundle": exported.json()["bundle"]},
        headers=_headers(tenant),
    )
    return (
        refused,
        validated,
        planned,
        empty_export,
        applied,
        replay,
        exported,
        replanned,
    )


def _bundle_read_requests(
    client: TestClient,
    tenant: TenantFixture,
    request: dict[str, object],
) -> tuple[Response, Response, Response, Response]:
    foreign = minimal_bundle()
    foreign = foreign.model_copy(
        update={
            "company": foreign.company.model_copy(
                update={"key": "foreign-company", "display_name": "Foreign Company"}
            ),
            "resources": tuple(
                resource.model_copy(
                    update={
                        "component": resource.component.model_copy(
                            update={
                                "scope": resource.component.scope.model_copy(
                                    update={"tenant": "foreign-company"}
                                )
                            }
                        )
                    }
                )
                for resource in foreign.resources
            ),
        }
    )
    refused = client.post(
        "/v1/company/bundle/validate",
        json={"bundle": foreign.model_dump(mode="json", by_alias=True)},
        headers=_headers(tenant),
    )
    validated = client.post(
        "/v1/company/bundle/validate",
        json=request,
        headers=_headers(tenant),
    )
    planned = client.post(
        "/v1/company/bundle/plan",
        json=request,
        headers=_headers(tenant),
    )
    empty_export = client.get("/v1/company/bundle/export", headers=_headers(tenant))
    return refused, validated, planned, empty_export


def test_ticket_comment_http_appends_replays_and_appears_in_timeline_and_audit(
    tenant: TenantFixture,
) -> None:
    command_id = uuid4()
    with TestClient(_app(tenant)) as client:
        created = _create_ticket(client, tenant)
        ticket_id = UUID(cast(str, created.json()["ticket"]["ticket_id"]))
        invalid = client.post(
            f"/v1/tickets/{ticket_id}/comments",
            json={"body": "   "},
            headers=_headers(tenant, command_id=uuid4()),
        )
        comment = client.post(
            f"/v1/tickets/{ticket_id}/comments",
            json={"body": "HTTP-authenticated append-only comment."},
            headers=_headers(tenant, command_id=command_id),
        )
        replay = client.post(
            f"/v1/tickets/{ticket_id}/comments",
            json={"body": "HTTP-authenticated append-only comment."},
            headers=_headers(tenant, command_id=command_id),
        )
        timeline = client.get(
            f"/v1/tickets/{ticket_id}/timeline",
            params={"project_key": "ctower"},
            headers=_headers(tenant),
        )
        audit = client.get(
            f"/v1/tickets/{ticket_id}/audit",
            params={"project_key": "ctower"},
            headers=_headers(tenant),
        )

    assert (invalid.status_code, invalid.json()["code"]) == (
        HTTP_UNPROCESSABLE_ENTITY,
        "ticket-comment-invalid",
    )
    assert comment.status_code == HTTP_PENDING
    assert replay.content == comment.content
    assert comment.json()["command_id"] == str(command_id)
    assert comment.json()["ticket_id"] == str(ticket_id)
    assert [event["kind"] for event in timeline.json()["events"]] == [
        "ticket.created",
        "ticket.comment_added",
    ]
    assert {event["kind"] for event in audit.json()["events"]} == {
        "ticket.created",
        "ticket.comment_added",
    }


def test_company_bundle_apply_principal_matrix_authorizes_before_effects(
    tenant: TenantFixture,
) -> None:
    store = MemoryObjectStore()
    before = _catalog_counts(tenant.database.admin_dsn)
    unauthenticated_id, commander_id, operator_id = uuid4(), uuid4(), uuid4()
    (
        validated,
        planned,
        unauthenticated,
        commander,
        operator,
        commander_export,
        invalid_plan,
        unsupported_lifecycle,
    ) = _exercise_principal_apply_matrix(
        tenant,
        store,
        before,
        unauthenticated_id,
        commander_id,
        operator_id,
    )

    assert validated.status_code == HTTP_OK
    assert planned.status_code == HTTP_OK
    assert (unauthenticated.status_code, unauthenticated.json()["code"]) == (
        HTTP_UNAUTHORIZED,
        "unauthorized",
    )
    assert (commander.status_code, commander.json()["code"]) == (
        HTTP_FORBIDDEN,
        "unauthorized",
    )
    assert operator.status_code == HTTP_PENDING
    assert commander_export.status_code == HTTP_OK
    assert (invalid_plan.status_code, invalid_plan.json()["code"]) == (
        HTTP_CONFLICT,
        "bundle-plan-mismatch",
    )
    assert (
        unsupported_lifecycle.status_code,
        unsupported_lifecycle.json()["code"],
    ) == (HTTP_UNPROCESSABLE_ENTITY, "bundle-compatibility-refused")


def _exercise_principal_apply_matrix(
    tenant: TenantFixture,
    store: MemoryObjectStore,
    before: tuple[int, int, int],
    unauthenticated_id: UUID,
    commander_id: UUID,
    operator_id: UUID,
) -> tuple[Response, Response, Response, Response, Response, Response, Response, Response]:
    bundle = _tenant_bundle()
    request = {"bundle": bundle.model_dump(mode="json", by_alias=True)}
    with TestClient(_app(tenant, store=store)) as client:
        validated = client.post(
            "/v1/company/bundle/validate",
            json=request,
            headers=_commander_headers(tenant),
        )
        planned = client.post(
            "/v1/company/bundle/plan",
            json=request,
            headers=_commander_headers(tenant),
        )
        apply_request = {
            **request,
            "expected_active_version": 0,
            "plan_digest": planned.json()["plan_digest"],
        }
        unauthenticated = client.post(
            "/v1/company/bundle/apply",
            json=apply_request,
            headers={"Idempotency-Key": str(unauthenticated_id), **telemetry_headers()},
        )
        commander = client.post(
            "/v1/company/bundle/apply",
            json=apply_request,
            headers=_commander_headers(tenant, command_id=commander_id),
        )
        _assert_principal_refusals_have_no_effects(
            tenant,
            store,
            before,
            (unauthenticated_id, commander_id),
        )
        operator = client.post(
            "/v1/company/bundle/apply",
            json=apply_request,
            headers=_headers(tenant, command_id=operator_id),
        )
        commander_export = client.get(
            "/v1/company/bundle/export",
            headers=_commander_headers(tenant),
        )
        invalid_plan, unsupported_lifecycle = _http_post_activation_refusals(
            client,
            tenant,
            bundle,
            store,
        )
    return (
        validated,
        planned,
        unauthenticated,
        commander,
        operator,
        commander_export,
        invalid_plan,
        unsupported_lifecycle,
    )


def _assert_principal_refusals_have_no_effects(
    tenant: TenantFixture,
    store: MemoryObjectStore,
    before: tuple[int, int, int],
    command_ids: tuple[UUID, UUID],
) -> None:
    assert (
        store.put_attempts,
        store.read_attempts,
        store.erase_attempts,
        store.write_count,
    ) == (0, 0, 0, 0)
    assert _catalog_counts(tenant.database.admin_dsn) == before
    assert _command_result_count(tenant.database.admin_dsn, command_ids) == 0


def _http_post_activation_refusals(
    client: TestClient,
    tenant: TenantFixture,
    bundle: CompanyBundle,
    store: MemoryObjectStore,
) -> tuple[Response, Response]:
    request = {"bundle": bundle.model_dump(mode="json", by_alias=True)}
    writes = store.put_attempts, store.write_count
    invalid_plan = client.post(
        "/v1/company/bundle/apply",
        json={
            **request,
            "expected_active_version": 1,
            "plan_digest": "sha256:" + "0" * 64,
        },
        headers=_headers(tenant, command_id=uuid4()),
    )
    removal = bundle.model_copy(
        update={
            "resources": tuple(
                resource
                for resource in bundle.resources
                if resource.component.key != "local.process"
            )
        }
    )
    planned = client.post(
        "/v1/company/bundle/plan",
        json={"bundle": removal.model_dump(mode="json", by_alias=True)},
        headers=_headers(tenant),
    )
    unsupported = client.post(
        "/v1/company/bundle/apply",
        json={
            "bundle": removal.model_dump(mode="json", by_alias=True),
            "expected_active_version": 1,
            "plan_digest": planned.json()["plan_digest"],
        },
        headers=_headers(tenant, command_id=uuid4()),
    )
    assert (store.put_attempts, store.write_count) == writes
    return invalid_plan, unsupported


def test_apply_refusals_and_replay_precede_payload_writes_and_lifecycle_effects(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    store = MemoryObjectStore()
    catalog = _catalog(tenant, store)
    bundle = _tenant_bundle()
    command, first = apply_initial_bundle(catalog, actor, bundle)
    writes = store.write_count
    facts = _catalog_counts(tenant.database.admin_dsn)

    assert_command_replay_precedes_adapters(catalog, actor, command, first, store)
    assert_locked_plan_refusals_precede_adapters(catalog, actor, bundle, store)
    assert_removal_refusal_precedes_adapters(catalog, actor, bundle, store)

    assert store.write_count == writes
    assert _catalog_counts(tenant.database.admin_dsn) == facts
    assert _deprecated_fact_count(tenant.database.admin_dsn) == 0
    exported = catalog.export(actor)
    assert not isinstance(exported, CatalogProblem)
    assert exported.active_version == 1
    assert any(resource.component.key == "local.process" for resource in exported.bundle.resources)


def test_retry_reconciles_payload_receipts_after_post_write_process_loss(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    bundle = _tenant_bundle()
    store = InterruptingObjectStore(len(bundle.resources))
    catalog = _catalog(tenant, store)
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem)
    command_id = uuid4()
    command = CompanyBundleApply(
        client_command_id=command_id,
        bundle=bundle,
        expected_active_version=0,
        plan_digest=plan.plan_digest,
    )

    with pytest.raises(SimulatedProcessLoss):
        catalog.apply(actor, command, telemetry=telemetry_for(actor, command_id))

    assert store.write_count == len(bundle.resources)
    assert _catalog_counts(tenant.database.admin_dsn) == (0, 0, 0)
    assert _command_result_count(tenant.database.admin_dsn, (command_id,)) == 0
    recovered = catalog.apply(actor, command, telemetry=telemetry_for(actor, command_id))

    assert isinstance(recovered, CompanyBundleCommandResult)
    assert recovered.active_version == 1
    assert store.write_count == len(bundle.resources)
    assert store.put_attempts == len(bundle.resources) * 2


def _catalog(tenant: TenantFixture, store: MemoryObjectStore) -> PostgresCatalog:
    return PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        store,
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 7, 24, tzinfo=UTC),
    )


def _tenant_bundle() -> CompanyBundle:
    bundle = minimal_bundle()
    return bundle.model_copy(
        update={
            "company": bundle.company.model_copy(
                update={"key": "ctower", "display_name": "Ctower"}
            ),
            "resources": tuple(
                resource.model_copy(
                    update={
                        "component": resource.component.model_copy(
                            update={
                                "scope": resource.component.scope.model_copy(
                                    update={"tenant": "ctower"}
                                )
                            }
                        )
                    }
                )
                for resource in bundle.resources
            ),
        }
    )


def _create_ticket(client: TestClient, tenant: TenantFixture) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(tenant.commander_id),
                "priority": "P1",
                "project_key": "ctower",
                "source": {"kind": "test", "ref": "test:company-bundle-http"},
                "title": "HTTP comment authority",
            },
            headers=_headers(tenant, command_id=uuid4()),
        ),
    )


def _commander_headers(
    tenant: TenantFixture,
    *,
    command_id: UUID | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {tenant.commander_credential}",
        **telemetry_headers(),
    }
    if command_id is not None:
        headers["Idempotency-Key"] = str(command_id)
    return headers


def _catalog_counts(dsn: str) -> tuple[int, int, int]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM catalog_component_revisions) AS components,
                (SELECT count(*) FROM company_bundle_revisions) AS bundles,
                (SELECT count(*) FROM events WHERE kind LIKE 'catalog.%') AS events
            """
        ).fetchone()
    assert row is not None
    return (
        int(cast(int, row["components"])),
        int(cast(int, row["bundles"])),
        int(cast(int, row["events"])),
    )


def _command_result_count(dsn: str, command_ids: tuple[UUID, ...]) -> int:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            "SELECT count(*) FROM command_results WHERE client_command_id = ANY(%s)",
            (list(command_ids),),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _deprecated_fact_count(dsn: str) -> int:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            "SELECT count(*) FROM catalog_component_lifecycle_facts WHERE action = 'deprecated'"
        ).fetchone()
    assert row is not None
    return int(row[0])
