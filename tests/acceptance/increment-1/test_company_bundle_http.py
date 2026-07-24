"""Authenticated HTTP composition for CompanyBundle and ticket comments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
from ctower_contracts import CATALOG
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.catalog import MemoryObjectStore, minimal_bundle
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.catalog import CompanyBundle, PostgresCatalog
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_PENDING = 202
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
    refused = client.post(
        "/v1/company/bundle/validate",
        json={"bundle": minimal_bundle().model_dump(mode="json", by_alias=True)},
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
            headers=_headers(tenant),
        )
        audit = client.get(
            f"/v1/tickets/{ticket_id}/audit",
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


def test_new_routes_authenticate_before_path_or_body_validation(
    tenant: TenantFixture,
) -> None:
    with TestClient(_app(tenant)) as client:
        unauthenticated = (
            client.post("/v1/company/bundle/validate", content=b"{"),
            client.post("/v1/company/bundle/plan", content=b"{"),
            client.post("/v1/company/bundle/apply", content=b"{"),
            client.get("/v1/company/bundle/export"),
            client.post("/v1/tickets/not-a-uuid/comments", content=b"{"),
        )
        authenticated = (
            client.post(
                "/v1/company/bundle/validate",
                content=b"{",
                headers=_headers(tenant),
            ),
            client.post(
                "/v1/company/bundle/plan",
                content=b"{",
                headers=_headers(tenant),
            ),
            client.post(
                "/v1/company/bundle/apply",
                content=b"{",
                headers=_headers(tenant, command_id=uuid4()),
            ),
            client.post(
                "/v1/tickets/not-a-uuid/comments",
                content=b"{",
                headers=_headers(tenant, command_id=uuid4()),
            ),
        )

    assert {(response.status_code, response.json()["code"]) for response in unauthenticated} == {
        (HTTP_UNAUTHORIZED, "unauthorized")
    }
    assert {(response.status_code, response.json()["code"]) for response in authenticated} == {
        (HTTP_UNPROCESSABLE_ENTITY, "validation-error")
    }


def _app(tenant: TenantFixture) -> FastAPI:
    store = MemoryObjectStore()
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        CATALOG,
        store,
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 7, 24, tzinfo=UTC),
    )
    return create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        catalog=catalog,
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
                "source": {"kind": "test", "ref": "test:company-bundle-http"},
                "title": "HTTP comment authority",
            },
            headers=_headers(tenant, command_id=uuid4()),
        ),
    )


def _headers(
    tenant: TenantFixture,
    *,
    command_id: UUID | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {tenant.operator_credential}",
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
