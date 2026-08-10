"""Fail-closed one-way Request import and signed reconciliation acceptance."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from support.acceptance import accept_pending_commands
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.request_cutover import (
    PostgresRequestCutover,
    RequestBatchProof,
    RequestCutover,
    RequestCutoverComplete,
    RequestCutoverImport,
    RequestCutoverPrepare,
    RequestCutoverResult,
    RequestImportReconciliation,
)
from ctower_kernel.work.requests import (
    PostgresRequests,
    RequestCapture,
    RequestCaptureResult,
    Requests,
)
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.operator_requests.dry_run import analyze_cutover

__all__: tuple[str, ...] = ()

_FIXTURE_HIGH_WATER = 12
_FIXTURE_OPEN_COUNT = 2
_HTTP_NOT_FOUND = 404


def test_frozen_open_set_cutover_is_exact_and_one_way(
    tenant: TenantFixture, tmp_path: Path
) -> None:
    """CT-I1-015: every source row is imported, accepted, proved, then sealed."""

    actor = _human_operator(tenant)
    authority = RequestCutover(PostgresRequestCutover(tenant.database.runtime_dsn))
    inventory = authority.authority_inventory(actor)
    assert isinstance(inventory, dict)
    signer, public_key = _signer()
    ledger, owners, freeze = _source_artifacts(
        tmp_path,
        signer,
        tenant,
        target_authority_digest=cast(str, inventory["authority_digest"]),
    )
    report = analyze_cutover(
        ledger,
        owner_map_path=owners,
        fence_proof_path=freeze,
        signer=signer,
    )
    assert report["eligible"] is True
    assert report["blockers"] == []
    assert report["counts"] == {
        "physical_rows": 3,
        "logical_requests": 3,
        "open_requests": 2,
        "open_by_project": [{"project_key": "ctower", "count": 2}],
    }
    manifest = cast(dict[str, Any], report["manifest"])
    manifest_digest = cast(str, report["manifest_digest"])
    imported, reconciliation, completed = _execute_epoch(
        tenant,
        authority,
        actor,
        signer,
        public_key,
        ledger,
        freeze,
        manifest,
        manifest_digest,
    )
    assert reconciliation.source_count == reconciliation.batch_target_count == _FIXTURE_OPEN_COUNT
    assert reconciliation.target_count == _FIXTURE_OPEN_COUNT
    assert all(row["equal"] is True for row in reconciliation.rows)
    assert all(row["implicit_ticket_count"] == 0 for row in reconciliation.rows)
    assert completed.state == "completed"

    absent = authority.reconcile(actor, manifest_digest, 0)
    assert isinstance(absent, RecordProblem)
    assert absent.code == "request-import-forbidden" and absent.status == _HTTP_NOT_FOUND
    assert _target_counts(tenant) == (_FIXTURE_OPEN_COUNT, 0, _FIXTURE_OPEN_COUNT, 1)
    native = Requests(PostgresRequests(tenant.database.runtime_dsn))
    first = RequestCapture(uuid4(), "ctower", "First native Request after cutover.")
    captured = native.capture(
        Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER),
        first,
        telemetry=_telemetry(actor, first.client_command_id),
    )
    assert isinstance(captured, RequestCaptureResult)
    assert captured.request_number > _FIXTURE_HIGH_WATER

    print(
        "REAL_REQUEST_CUTOVER"
        f" manifest={manifest_digest} source_open=2 imported={len(imported)}"
        f" reconciled={reconciliation.target_count} batches=1"
        f" maximum=R{_FIXTURE_HIGH_WATER} first_native=R{captured.request_number}"
    )


def _execute_epoch(
    tenant: TenantFixture,
    authority: RequestCutover,
    actor: Actor,
    signer: ArtifactSigner,
    public_key: str,
    ledger: Path,
    freeze: Path,
    manifest: dict[str, Any],
    manifest_digest: str,
) -> tuple[list[RequestCutoverResult], RequestImportReconciliation, RequestCutoverResult]:
    freeze_text = freeze.read_text(encoding="utf-8")
    prepare = RequestCutoverPrepare(uuid4(), _artifact_text(manifest), freeze_text, public_key)
    prepared = authority.prepare(
        actor, prepare, telemetry=_telemetry(actor, prepare.client_command_id)
    )
    assert not isinstance(prepared, RecordProblem), prepared.detail
    assert isinstance(prepared, RequestCutoverResult) and prepared.state == "prepared"
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    imported = _import_rows(
        tenant, authority, actor, public_key, ledger, freeze_text, manifest, manifest_digest
    )
    reconciliation = authority.reconcile(actor, manifest_digest, 0)
    assert isinstance(reconciliation, RequestImportReconciliation)
    proof = _proof(signer, reconciliation)
    proof_command = RequestBatchProof(uuid4(), _artifact_text(proof), public_key)
    proved = authority.record_batch_proof(
        actor,
        proof_command,
        telemetry=_telemetry(actor, proof_command.client_command_id),
    )
    assert isinstance(proved, RequestCutoverResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    final_fence = _fence(ledger, signer, phase="final")
    complete = RequestCutoverComplete(
        uuid4(), manifest_digest, _artifact_text(final_fence), public_key
    )
    completed = authority.complete(
        actor, complete, telemetry=_telemetry(actor, complete.client_command_id)
    )
    assert isinstance(completed, RequestCutoverResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return imported, reconciliation, completed


def _import_rows(
    tenant: TenantFixture,
    authority: RequestCutover,
    actor: Actor,
    public_key: str,
    ledger: Path,
    freeze_text: str,
    manifest: dict[str, Any],
    manifest_digest: str,
) -> list[RequestCutoverResult]:
    imported: list[RequestCutoverResult] = []
    for row in cast(list[dict[str, object]], manifest["rows"]):
        command = RequestCutoverImport(
            UUID(cast(str, row["command_id"])),
            manifest_digest,
            cast(str, row["id"]),
            _source_text(ledger, cast(str, row["id"])),
            freeze_text,
            public_key,
        )
        outcome = authority.import_row(
            actor, command, telemetry=_telemetry(actor, command.client_command_id)
        )
        assert isinstance(outcome, RequestCutoverResult)
        imported.append(outcome)
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return imported


def test_corrupt_lineage_and_non_request_prohibited_data_are_refused(tmp_path: Path) -> None:
    ledger = tmp_path / "requests.jsonl"
    row = _row("R20", "NEW", "sensitive-token-value")
    row["history"] = [
        {"at": row["created"], "actor": "operator", "event": "created", "to": "NEW"},
        {"at": row["created"], "actor": "operator", "event": "created", "to": "NEW"},
    ]
    decision = {
        "record_type": "decision",
        "id": "D1",
        "kind": "note",
        "actor": "operator",
        "at": "2026-08-10T01:00:00Z",
        "reason": "password=definitely-not-source-data",
        "requests": ["R20"],
    }
    ledger.write_text(f"{json.dumps(row)}\n{json.dumps(decision)}\n", encoding="utf-8")
    ledger.chmod(0o444)

    report = analyze_cutover(ledger)

    assert report["eligible"] is False
    assert any(item.startswith("lineage-second-creation:R20") for item in report["blockers"])
    assert any(item.startswith("prohibited-history:") for item in report["blockers"])
    assert report["manifest"] is None


def _human_operator(tenant: TenantFixture) -> Actor:
    principal_id, binding_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled,
                credential_ref, vault_ref, created_at
            ) VALUES (%s, %s, 'operator', 'Request Cutover Reviewer', false, NULL, NULL, %s)
            """,
            (principal_id, tenant.tenant_id, now),
        )
        connection.execute(
            """
            INSERT INTO human_role_bindings (
                binding_id, tenant_id, principal_id, oidc_issuer, oidc_subject,
                role, project_keys, granted_by, granted_at
            ) VALUES (%s, %s, %s, 'https://issuer.example', 'request-reviewer',
                      'operator', ARRAY['ctower'], %s, %s)
            """,
            (binding_id, tenant.tenant_id, principal_id, tenant.operator_id, now),
        )
    return Actor(principal_id, tenant.tenant_id, PrincipalKind.OPERATOR)


def _signer() -> tuple[ArtifactSigner, str]:
    private_key = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:request-cutover", 1, private_key)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return signer, public_key.decode("ascii")


def _source_artifacts(
    tmp_path: Path,
    signer: ArtifactSigner,
    tenant: TenantFixture,
    *,
    target_authority_digest: str,
) -> tuple[Path, Path, Path]:
    ledger = tmp_path / "requests.jsonl"
    rows = [
        _row("R10", "NEW", "first frozen intent"),
        _row("R11", "BLOCKED", "second frozen intent"),
        _row("R12", "DONE", "closed source history"),
    ]
    ledger.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    ledger.chmod(0o444)
    owners = tmp_path / "owners.json"
    owners.write_text(
        json.dumps(
            {
                "schema": "ctower.request-owner-map/v1",
                "target_tenant_id": str(tenant.tenant_id),
                "target_authority_digest": target_authority_digest,
                "reviewed_at": datetime.now(UTC).isoformat(),
                "reviewed_by": "request-cutover-reviewer",
                "mappings": [
                    {
                        "project_key": "ctower",
                        "source_owner": "legacy-commander",
                        "principal_id": str(tenant.commander_id),
                    }
                ],
                "request_reviews": [{"id": "R11", "priority": "P1"}],
            }
        ),
        encoding="utf-8",
    )
    freeze = tmp_path / "freeze.json"
    freeze.write_text(_artifact_text(_fence(ledger, signer, phase="freeze")), encoding="utf-8")
    return ledger, owners, freeze


def _fence(ledger: Path, signer: ArtifactSigner, *, phase: str) -> dict[str, Any]:
    metadata = ledger.stat()
    digest = f"sha256:{hashlib.sha256(ledger.read_bytes()).hexdigest()}"
    final = phase == "final"
    return signer.seal(
        {
            "schema": "ctower.request-source-fence/v1",
            "phase": phase,
            "ledger_sha256": digest,
            "source_identity": {
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "mode": metadata.st_mode,
                "mtime_ns": str(metadata.st_mtime_ns),
                "size": metadata.st_size,
            },
            "writer_refuses": True,
            "mutation_entrypoints_removed": final,
            "filesystem_read_only": True,
            "callers": [
                {
                    "path": "mission-control/request-writer.py",
                    "sha256": "sha256:" + "1" * 64,
                    "state": "removed" if final else "refuses",
                }
            ],
            "observed_at": datetime.now(UTC).isoformat(),
        },
        "fence_digest",
    )


def _row(request_id: str, status: str, text: str) -> dict[str, object]:
    created = "2026-08-10T01:00:00Z"
    history: list[dict[str, object]] = [
        {"at": created, "actor": "operator", "event": "created", "to": "NEW"}
    ]
    updated = created
    if status != "NEW":
        updated = "2026-08-10T02:00:00Z"
        history.append(
            {
                "at": updated,
                "actor": "operator",
                "event": "status_set",
                "field": "status",
                "from": "NEW",
                "to": status,
            }
        )
    return {
        "id": request_id,
        "record_type": "request",
        "status": status,
        "text": text,
        "owner": "legacy-commander",
        "note": "explicit source blocker" if status == "BLOCKED" else "",
        "project": "ctower",
        "created": created,
        "updated": updated,
        "active": status != "DONE",
        "relationships": [],
        "history": history,
        "refines": [],
    }


def _source_text(ledger: Path, source_id: str) -> str:
    for raw in ledger.read_text(encoding="utf-8").splitlines():
        row = json.loads(raw)
        if row["id"] == source_id:
            return cast(str, row["text"])
    raise AssertionError(f"missing source row {source_id}")


def _proof(signer: ArtifactSigner, reconciliation: RequestImportReconciliation) -> dict[str, Any]:
    payload = reconciliation.response_payload()
    sample_ids = set(cast(list[str], payload.pop("sample_ids")))
    rows = cast(list[dict[str, object]], payload["rows"])
    return signer.seal(
        {
            "schema": "ctower.request-batch-proof/v1",
            **payload,
            "samples": [row for row in rows if row["id"] in sample_ids],
        },
        "proof_digest",
    )


def _artifact_text(value: dict[str, Any]) -> str:
    return rfc8785.dumps(cast(Any, value)).decode("utf-8")


def _target_counts(tenant: TenantFixture) -> tuple[int, int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM requests WHERE tenant_id = %s),
              (SELECT count(*) FROM request_ticket_relation_facts WHERE tenant_id = %s),
              (SELECT count(*) FROM request_import_rows WHERE tenant_id = %s),
              (SELECT count(*) FROM request_import_batch_proofs WHERE tenant_id = %s)
            """,
            (tenant.tenant_id,) * 4,
        ).fetchone()
    assert row is not None
    return cast(tuple[int, int, int, int], tuple(int(item) for item in row))


def _telemetry(actor: Actor, command_id: UUID) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=command_id.hex,
        span_id=command_id.hex[:16],
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )
