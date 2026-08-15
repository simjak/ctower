"""Acceptance boundary vectors for operator-only estate import commands."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from support.postgres import DatabaseFixture
from support.server import application
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.estate_import_contracts import EstateImportBatchResult
from ctower_api.estate_imports import PostgresEstateImports
from ctower_client.models import EstateImportParity
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.postgres import apply_migrations, provision_database_roles
from ctower_kernel.telemetry import TelemetryContext
from ctowerctl import parse_arguments
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.estate_imports import build_estate_manifest

__all__: tuple[str, ...] = ()

_HTTP_PENDING = 202
_HTTP_UNPROCESSABLE_ENTITY = 422


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("ctower-inbox", "migration ctower-inbox import"),
        ("ctower-ruling", "migration ctower-ruling import"),
        ("ctower-knowledge", "migration ctower-knowledge import"),
        ("ctower-company-record", "migration ctower-company-record import"),
    ],
)
def test_each_estate_import_is_an_explicit_online_operator_command(
    subject: str, expected: str
) -> None:
    parsed = parse_arguments(
        [
            "migration",
            subject,
            "import",
            "--request-file",
            "estate-batch.json",
            "--command-id",
            "018f0d5e-7b9a-7c01-8000-000000000100",
        ]
    )
    assert parsed.cli_name == expected
    assert parsed.command_id.int > 0


def test_product_migration_engine_applies_and_attests_final_estate_schema(
    database: DatabaseFixture,
) -> None:
    """Fresh product migration apply reaches the estate schema and attests it."""
    provision_database_roles(database.admin_dsn)
    apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)

    manifest_path = Path(__file__).parents[3] / "packages/ctower-kernel/migrations/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT migration_id, result_schema_sha256
            FROM ctower_schema_migrations
            ORDER BY migration_id DESC
            LIMIT 1
            """
        ).fetchone()

    assert row == (
        manifest["adoption_baseline"]["through"],
        manifest["adoption_baseline"]["schema_sha256"],
    )


@pytest.mark.parametrize(
    "tier",
    ["inbox_history", "agreed_decisions", "knowledge_documents", "company_records"],
)
def test_estate_import_authority_is_operator_scoped_in_postgres(
    tenant: TenantFixture, tier: str
) -> None:
    """Each estate tier commits through a fresh product-migrated PostgreSQL database."""
    if tier == "agreed_decisions":
        _provision_operator_project_seat(tenant)
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:acceptance", 1, private_key)
    manifest_rows, rows = _tier_rows(tier)
    manifest = build_estate_manifest(
        tier=tier,
        source_identity={
            "namespace": "mission-control:estate",
            "source_path": f"acceptance/{tier}.jsonl",
            "source_sha256": _digest_text(tier),
        },
        rows=manifest_rows,
        seat_mapping_digest=None,
        project_key="ctower" if tier == "agreed_decisions" else None,
        signer=signer,
    )
    actor, command_id = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR), uuid4()
    authority_inventory_before = _authority_inventory(tenant)
    importer = PostgresEstateImports(
        tenant.database.runtime_dsn,
        {("signing-key-ref:acceptance", 1): private_key.public_key()},
        parity_signer=signer,
    )
    result = importer.import_batch(
        actor,
        tier=tier,
        batch_index=0,
        command_id=command_id,
        manifest=manifest,
        rows=rows,
        now=datetime.now(UTC),
        telemetry=_telemetry(actor, command_id),
    )

    assert not isinstance(result, RecordProblem), result
    assert result.source_count == result.imported_count == 1
    assert result.parity["emitted_before_closure"] is True
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT origin FROM events WHERE event_id = %s", (result.event_ids[0],)
        ).fetchone() == ("estate_import",)
    assert _authority_inventory(tenant) == authority_inventory_before

    replay = importer.import_batch(
        actor,
        tier=tier,
        batch_index=0,
        command_id=command_id,
        manifest=manifest,
        rows=rows,
        now=datetime.now(UTC),
        telemetry=_telemetry(actor, command_id),
    )
    assert not isinstance(replay, RecordProblem), replay
    assert replay.manifest_digest == result.manifest_digest
    assert replay.parity["emitted_before_closure"] is True
    assert _authority_inventory(tenant) == authority_inventory_before


def test_inbox_import_refuses_and_counts_prohibited_rows_in_postgres(
    tenant: TenantFixture,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:acceptance", 1, private_key)
    manifest_rows, rows = _inbox_rows_with_prohibited()
    manifest = build_estate_manifest(
        tier="inbox_history",
        source_identity={
            "namespace": "mission-control:estate",
            "source_path": "acceptance/inbox_history.jsonl",
            "source_sha256": _digest_text("inbox-history-with-prohibited-row"),
        },
        rows=manifest_rows,
        seat_mapping_digest=None,
        signer=signer,
    )
    actor, command_id = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR), uuid4()
    importer = PostgresEstateImports(
        tenant.database.runtime_dsn,
        {("signing-key-ref:acceptance", 1): private_key.public_key()},
        parity_signer=signer,
    )

    result = importer.import_batch(
        actor,
        tier="inbox_history",
        batch_index=0,
        command_id=command_id,
        manifest=manifest,
        rows=rows,
        now=datetime.now(UTC),
        telemetry=_telemetry(actor, command_id),
    )

    assert not isinstance(result, RecordProblem), result
    _assert_refused_prohibited_parity(result, rows)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM estate_import_source_only_messages WHERE source_ref = %s",
            ("inbox.jsonl#credential",),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM inbox_messages WHERE source_ref = %s",
            ("inbox.jsonl#credential",),
        ).fetchone() == (0,)


def _assert_refused_prohibited_parity(
    result: EstateImportBatchResult, rows: list[dict[str, object]]
) -> None:
    validated_parity = EstateImportParity.model_validate_json(json.dumps(result.parity))
    assert validated_parity.refused_prohibited_count == 1
    assert result.source_count == len(rows)
    assert result.imported_count == 1
    assert result.parity["source_count"] == len(rows)
    assert result.parity["imported_count"] == 1
    assert result.parity["refused_prohibited_count"] == 1
    assert result.parity["refused_prohibited_rows"] == [
        {
            "content_sha256": rows[1]["content_sha256"],
            "disposition": "refused_prohibited",
            "problem_code": "prohibited-data-class",
            "prohibited_classes": ["credential_material"],
            "source_ref": "inbox.jsonl#credential",
        }
    ]
    parity = cast(dict[str, object], result.parity)
    batches = cast(list[dict[str, object]], parity["batches"])
    assert batches[0]["source_count"] == len(rows)
    assert batches[0]["imported_count"] == 1
    assert batches[0]["refused_prohibited_count"] == 1
    assert batches[0]["refused_prohibited_rows"] == parity["refused_prohibited_rows"]


def test_company_records_import_is_reachable_through_http_contract(
    tenant: TenantFixture,
) -> None:
    importer, manifest, rows = _signed_import_fixture(
        tenant.database.runtime_dsn, "company_records"
    )
    command_id = uuid4()
    request_rows = [
        {key: value for key, value in row.items() if key not in {"_disposition", "source_seat"}}
        for row in rows
    ]
    with TestClient(application(tenant.database.runtime_dsn, estate_imports=importer)) as client:
        response = client.post(
            "/v1/migrations/estate/company-records",
            json={"batch_index": 0, "manifest": manifest, "rows": request_rows},
            headers={
                "Authorization": f"Bearer {tenant.operator_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        )

    assert response.status_code == _HTTP_PENDING
    assert response.json()["tier"] == "company_records"
    assert response.json()["imported_count"] == 1
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT natural_key FROM company_records WHERE source_ref = %s",
            ("state/escapes.jsonl#1",),
        ).fetchone() == ("escape:acceptance-1",)


def test_estate_import_http_refusal_uses_the_problem_contract(
    tenant: TenantFixture,
) -> None:
    importer, manifest, rows = _signed_import_fixture(
        tenant.database.runtime_dsn, "company_records"
    )
    manifest = {**manifest, "manifest_digest": _digest_text("tampered")}
    request_rows = [
        {key: value for key, value in row.items() if key not in {"_disposition", "source_seat"}}
        for row in rows
    ]
    command_id = uuid4()
    with TestClient(application(tenant.database.runtime_dsn, estate_imports=importer)) as client:
        response = client.post(
            "/v1/migrations/estate/company-records",
            json={"batch_index": 0, "manifest": manifest, "rows": request_rows},
            headers={
                "Authorization": f"Bearer {tenant.operator_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        )

    assert response.status_code == _HTTP_UNPROCESSABLE_ENTITY
    assert response.json()["code"] == "estate-import-invalid"


def _inbox_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    message_id = str(uuid4())
    subject = "Acceptance inbox message"
    body = "The estate importer committed this source-only message."
    content_digest = _digest_text(json.dumps({"subject": subject, "body": body}, sort_keys=True))
    projection: dict[str, object] = {
        "_disposition": "source_only",
        "content_sha256": content_digest,
        "source_ref": "inbox.jsonl#1",
        "source_seat": "external-sender",
        "target_seat_key": None,
    }
    return [projection], [
        {
            **projection,
            "message_id": message_id,
            "source_sender": "external-sender",
            "source_recipient": "operator",
            "sent_at": "2026-08-15T12:00:00+00:00",
            "subject": subject,
            "body": body,
            "read_state": "delivered",
        }
    ]


def _inbox_rows_with_prohibited() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    manifest_rows, rows = _inbox_rows()
    subject = "Leaked session"
    body = "session_token=not-a-real-super-admin-token"
    content_digest = _digest_text(json.dumps({"subject": subject, "body": body}, sort_keys=True))
    manifest_rows.append(
        {
            **manifest_rows[0],
            "content_sha256": content_digest,
            "source_ref": "inbox.jsonl#credential",
        }
    )
    rows.append(
        {
            **rows[0],
            "body": body,
            "content_sha256": content_digest,
            "message_id": str(uuid4()),
            "source_ref": "inbox.jsonl#credential",
            "subject": subject,
        }
    )
    return manifest_rows, rows


def _tier_rows(tier: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    digest = _digest_text(tier)
    if tier == "inbox_history":
        return _inbox_rows()
    if tier == "agreed_decisions":
        verbatim = "# Accepted decision\n\nKeep the project provenance."
        return _generic_rows(
            tier,
            "board/agreed-acceptance.md",
            _digest_content(verbatim),
            {
                "source_ref": "board/agreed-acceptance.md",
                "verbatim": verbatim,
                "recorded_at": "2026-08-15T12:00:00+00:00",
                "content_sha256": _digest_content(verbatim),
            },
        )
    if tier == "knowledge_documents":
        body = "A knowledge document from a path-shaped source reference."
        return _generic_rows(
            tier,
            "board/policy-reference.md",
            _digest_content(body),
            {
                "document_id": str(uuid4()),
                "source_ref": "board/policy-reference.md",
                "title": "Policy reference",
                "body": body,
                "recorded_at": "2026-08-15T12:00:00+00:00",
                "content_sha256": _digest_content(body),
            },
        )
    if tier == "company_records":
        return _generic_rows(
            tier,
            "state/escapes.jsonl#1",
            digest,
            {
                "schema": "ctower.company-record-import/v1",
                "record_type": "escape",
                "natural_key": "escape:acceptance-1",
                "occurred_on": "2026-08-15",
                "payload": {"summary": "Acceptance escape"},
                "source_ref": "state/escapes.jsonl#1",
                "seat": "unknown-owner",
                "imported_at": "2026-08-15T12:00:00+00:00",
                "content_sha256": digest,
            },
        )
    raise AssertionError(f"unknown estate tier: {tier}")


def _signed_import_fixture(
    dsn: str, tier: str
) -> tuple[PostgresEstateImports, dict[str, object], list[dict[str, object]]]:
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:acceptance", 1, private_key)
    manifest_rows, rows = _tier_rows(tier)
    manifest = build_estate_manifest(
        tier=tier,
        source_identity={
            "namespace": "mission-control:estate",
            "source_path": f"acceptance/{tier}.jsonl",
            "source_sha256": _digest_text(tier),
        },
        rows=manifest_rows,
        seat_mapping_digest=None,
        project_key="ctower" if tier == "agreed_decisions" else None,
        signer=signer,
    )
    return (
        PostgresEstateImports(
            dsn,
            {("signing-key-ref:acceptance", 1): private_key.public_key()},
            parity_signer=signer,
        ),
        manifest,
        rows,
    )


def _generic_rows(
    tier: str, source_ref: str, digest: str, row: dict[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    projection: dict[str, object] = {
        "_disposition": "source_only",
        "content_sha256": digest,
        "source_ref": source_ref,
        "source_seat": "unknown-owner",
    }
    if tier == "company_records":
        projection.update(
            {
                "natural_key": row["natural_key"],
                "target_seat_key": None,
                "payload": row["payload"],
            }
        )
    return [projection], [{**row, "source_seat": "unknown-owner", "_disposition": "source_only"}]


def _provision_operator_project_seat(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO project_seats (
                principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
            ) VALUES (%s, %s, 'ctower', 'ctower-operator', %s, %s)
            """,
            (tenant.operator_id, tenant.tenant_id, tenant.operator_id, datetime.now(UTC)),
        )


def _authority_inventory(tenant: TenantFixture) -> tuple[int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM principals WHERE tenant_id = %s),
                (SELECT COUNT(*) FROM project_seats WHERE tenant_id = %s),
                (SELECT COUNT(*) FROM seat_credential_issuances WHERE tenant_id = %s)
            """,
            (tenant.tenant_id, tenant.tenant_id, tenant.tenant_id),
        ).fetchone()
    assert row is not None
    return (int(row[0]), int(row[1]), int(row[2]))


def _telemetry(actor: Actor, command_id: UUID) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _digest_content(value: str) -> str:
    return _digest_text(value)
