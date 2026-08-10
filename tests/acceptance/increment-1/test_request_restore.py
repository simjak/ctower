"""Isolated physical restore proof for first-class Request authority."""

from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from psycopg import sql
from support.acceptance import accept_pending_commands
from support.postgres import (
    PostgresServer,
    create_database,
    drop_database,
)
from support.recovery import accepted_roots, signature_verification
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.postgres_recovery import PostgresRecovery
from ctower_kernel.record.recovery import AnchorRecord, RecoveryPolicy
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.requests import (
    PostgresRequests,
    RequestCapture,
    RequestCaptureResult,
    RequestChangeResult,
    RequestList,
    RequestPriority,
    Requests,
)
from tools.migration.ctower_project.ctower_project_source.refusal import MigrationRefusal
from tools.migration.ctower_project.ctower_project_source.signing import (
    ArtifactSigner,
    ArtifactVerifier,
)
from tools.process_execution import run

__all__: tuple[str, ...] = ()

_REQUEST_TABLES = (
    "request_number_allocators",
    "requests",
    "request_owner_facts",
    "request_priority_facts",
    "request_triage_facts",
    "request_ticket_relation_facts",
    "request_blocker_facts",
    "request_closure_evaluations",
    "request_attention_facts",
    "request_import_manifests",
    "request_cutover_epoch_facts",
    "request_import_rows",
    "request_import_batch_proofs",
    "request_owner_aliases",
    "request_refinement_facts",
)
_PROCESS_TIMEOUT_SECONDS = 30
_READ_AT = datetime(2030, 1, 1, tzinfo=UTC)


def test_request_authority_restores_from_signed_server_inventory(
    tenant: TenantFixture,
    postgres_17: PostgresServer,
    tmp_path: Path,
) -> None:
    """OR-08: allocator, facts, aliases, events, ACKs, and outbox restore together."""

    authority, actor, captured, command_ids = _seed_request_authority(tenant)
    source_inventory = _inventory(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        command_ids=command_ids,
    )
    source_projection = _read_projection(authority, actor)
    signed_inventory, verifier = _signed_restore_inventory(
        tenant.tenant_id,
        source_inventory,
        source_projection,
    )
    _assert_event_complete(tenant.database.admin_dsn, tenant.tenant_id)
    next_number = _restore_and_verify(
        tenant,
        postgres_17,
        tmp_path / "request-authority.dump",
        actor,
        captured,
        command_ids,
        signed_inventory,
        verifier,
    )
    print(
        "SIGNED_REQUEST_RESTORE"
        f" digest={_digest(source_inventory)}"
        f" signed_inventory={signed_inventory['inventory_digest']}"
        f" requests={len(source_inventory['requests'])}"
        f" request_events={len(source_inventory['request_events'])}"
        f" anchors={len(source_inventory['request_anchors'])}"
        f" next_number={next_number}"
    )


def _seed_request_authority(
    tenant: TenantFixture,
) -> tuple[Requests, Actor, RequestCaptureResult, tuple[UUID, UUID]]:
    authority = Requests(PostgresRequests(tenant.database.runtime_dsn), clock=lambda: _READ_AT)
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    capture = RequestCapture(uuid4(), "ctower", "Restore this durable operator intent.")
    captured = authority.capture(
        actor, capture, telemetry=_telemetry(actor, capture.client_command_id)
    )
    assert isinstance(captured, RequestCaptureResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    replay = authority.capture(
        actor, capture, telemetry=_telemetry(actor, capture.client_command_id)
    )
    assert replay == captured
    priority = RequestPriority(uuid4(), captured.request_id, 1, "P1", "restore denominator")
    prioritized = authority.prioritize(
        actor,
        priority,
        telemetry=_telemetry(actor, priority.client_command_id),
    )
    assert isinstance(prioritized, RequestChangeResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    _anchor_accepted_record(tenant)
    return authority, actor, captured, (capture.client_command_id, priority.client_command_id)


def _signed_restore_inventory(
    tenant_id: UUID,
    source_inventory: dict[str, list[object]],
    source_projection: dict[str, object],
) -> tuple[dict[str, object], ArtifactVerifier]:
    signer = ArtifactSigner(
        "signing-key-ref:test/request-restore",
        1,
        Ed25519PrivateKey.generate(),
    )
    signed_inventory = signer.seal(
        {
            "schema": "ctower.request-restore-inventory/v1",
            "tenant_id": str(tenant_id),
            "inventory": source_inventory,
            "read_projection": source_projection,
        },
        "inventory_digest",
    )
    verifier = signer.verifier()
    assert (
        verifier.verify(signed_inventory, "inventory_digest")
        == signed_inventory["inventory_digest"]
    )
    return signed_inventory, verifier


def _restore_and_verify(
    tenant: TenantFixture,
    postgres_17: PostgresServer,
    dump: Path,
    actor: Actor,
    captured: RequestCaptureResult,
    command_ids: tuple[UUID, UUID],
    signed_inventory: dict[str, object],
    verifier: ArtifactVerifier,
) -> int:
    restored = create_database(postgres_17)
    try:
        _physical_restore(tenant.database.admin_dsn, restored.admin_dsn, dump)
        restored_inventory = _inventory(
            restored.admin_dsn,
            tenant.tenant_id,
            command_ids=command_ids,
        )
        _assert_event_complete(restored.admin_dsn, tenant.tenant_id)
        restored_authority = Requests(
            PostgresRequests(restored.runtime_dsn), clock=lambda: _READ_AT
        )
        restored_projection = _read_projection(restored_authority, actor)
        assert (
            _restore_findings(
                signed_inventory,
                verifier,
                restored_inventory,
                restored_projection,
            )
            == ()
        )
        _assert_faults_quarantine(
            signed_inventory,
            verifier,
            restored_inventory,
            restored_projection,
        )
        next_command = RequestCapture(uuid4(), "ctower", "First request after restore.")
        next_result = restored_authority.capture(
            actor,
            next_command,
            telemetry=_telemetry(actor, next_command.client_command_id),
        )
        assert isinstance(next_result, RequestCaptureResult)
        assert next_result.request_number == captured.request_number + 1
        return next_result.request_number
    finally:
        drop_database(restored)


def _anchor_accepted_record(tenant: TenantFixture) -> None:
    roots = accepted_roots(tenant.database.admin_dsn, tenant.tenant_id)
    digest = RecoveryPolicy().build_anchor(roots, previous_anchor_sha256=None)
    anchor = AnchorRecord(
        anchor_id=uuid4(),
        tenant_id=tenant.tenant_id,
        source_start_position=roots[0].acceptance_position,
        source_end_position=roots[-1].acceptance_position,
        previous_anchor_sha256=None,
        anchor_sha256=digest,
        signature="request-restore-inventory-anchor",
        signing_key_reference="kms-ref:test/request-restore",
        signing_key_version="v1",
        public_key_sha256="sha256:" + "a" * 64,
        object_key=f"test/request-restore/{roots[-1].acceptance_position}.json",
        object_version="version-1",
        anchored_at=datetime.now(UTC),
    )
    PostgresRecovery(tenant.database.admin_dsn).record_anchor(
        anchor,
        verification=signature_verification(anchor),
    )


def _read_projection(authority: Requests, actor: Actor) -> dict[str, object]:
    outcome = authority.list(
        actor,
        project_key="ctower",
        telemetry=_telemetry(actor, uuid4()),
    )
    assert isinstance(outcome, RequestList)
    return outcome.response_payload()


def _physical_restore(source_dsn: str, target_dsn: str, dump: Path) -> None:
    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if pg_dump is None or pg_restore is None:
        raise RuntimeError("PostgreSQL client tools are required for restore acceptance")
    run(
        (pg_dump, "--format=custom", f"--file={dump}", source_dsn),
        check=True,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
        capture_output=True,
    )
    run(
        (pg_restore, "--no-owner", f"--dbname={target_dsn}", str(dump)),
        check=True,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
        capture_output=True,
    )


def _inventory(
    dsn: str,
    tenant_id: UUID,
    *,
    command_ids: tuple[UUID, ...],
) -> dict[str, list[object]]:
    inventory: dict[str, list[object]] = {}
    with psycopg.connect(dsn) as connection:
        for table in _REQUEST_TABLES:
            query = sql.SQL(
                "SELECT to_jsonb(row_value) FROM {} AS row_value "
                "WHERE tenant_id = %s ORDER BY to_jsonb(row_value)::text"
            ).format(sql.Identifier(table))
            inventory[table] = [row[0] for row in connection.execute(query, (tenant_id,))]
        inventory["request_events"] = _json_rows(
            connection,
            "SELECT to_jsonb(event_row) FROM events AS event_row "
            "WHERE tenant_id = %s AND kind = 'request.changed' "
            "ORDER BY stream_id, sequence",
            (tenant_id,),
        )
        inventory["request_event_links"] = _json_rows(
            connection,
            "SELECT to_jsonb(link_row) FROM event_links AS link_row "
            "WHERE tenant_id = %s AND subject_kind = 'request' "
            "ORDER BY event_id, subject_id",
            (tenant_id,),
        )
        inventory["request_outbox"] = _json_rows(
            connection,
            "SELECT to_jsonb(outbox_row) FROM outbox AS outbox_row "
            "WHERE tenant_id = %s AND event_id IN ("
            "SELECT event_id FROM events WHERE tenant_id = %s AND kind = 'request.changed'"
            ") ORDER BY event_id, topic",
            (tenant_id, tenant_id),
        )
        inventory["request_command_results"] = _json_rows(
            connection,
            "SELECT to_jsonb(result_row) FROM command_results AS result_row "
            "WHERE tenant_id = %s AND client_command_id = ANY(%s) "
            "ORDER BY client_command_id",
            (tenant_id, list(command_ids)),
        )
        for table in (
            "durability_acknowledgements",
            "durability_acceptance_finalizations",
            "durability_acceptance_confirmations",
        ):
            query = sql.SQL(
                "SELECT to_jsonb(row_value) FROM {} AS row_value "
                "WHERE tenant_id = %s AND client_command_id = ANY(%s) "
                "ORDER BY client_command_id"
            ).format(sql.Identifier(table))
            inventory[f"request_{table}"] = _json_rows(
                connection,
                query.as_string(connection),
                (tenant_id, list(command_ids)),
            )
        inventory["request_durability_heads"] = _json_rows(
            connection,
            "SELECT to_jsonb(head_row) FROM durability_subject_heads AS head_row "
            "WHERE tenant_id = %s AND subject_kind = 'request' "
            "ORDER BY subject_id",
            (tenant_id,),
        )
        inventory["request_source_aliases"] = _json_rows(
            connection,
            "SELECT to_jsonb(alias_row) FROM inbound_source_aliases AS alias_row "
            "WHERE tenant_id = %s AND inbound_event_id IN ("
            "SELECT inbound_event_id FROM requests WHERE tenant_id = %s"
            ") ORDER BY source_kind, source_ref, project_key",
            (tenant_id, tenant_id),
        )
        inventory["request_anchors"] = _json_rows(
            connection,
            "SELECT to_jsonb(anchor_row) FROM record_anchor_receipts AS anchor_row "
            "WHERE tenant_id = %s ORDER BY source_end_position",
            (tenant_id,),
        )
        inventory["record_position_ledger"] = _json_rows(
            connection,
            "SELECT to_jsonb(position_row) FROM record_position_ledger AS position_row",
            (),
        )
        inventory["request_inbound_events"] = _json_rows(
            connection,
            "SELECT to_jsonb(inbound_row) FROM inbound_events AS inbound_row "
            "WHERE tenant_id = %s AND initial_outcome = 'request_created' "
            "ORDER BY inbound_event_id",
            (tenant_id,),
        )
    return inventory


def _restore_findings(
    signed_inventory: dict[str, object],
    verifier: ArtifactVerifier,
    observed_inventory: dict[str, list[object]],
    observed_projection: dict[str, object],
) -> tuple[str, ...]:
    try:
        verifier.verify(signed_inventory, "inventory_digest")
    except MigrationRefusal:
        return ("unverifiable-signed-inventory",)
    expected_inventory = signed_inventory.get("inventory")
    expected_projection = signed_inventory.get("read_projection")
    findings: list[str] = []
    if expected_inventory != observed_inventory:
        findings.append("inventory-mismatch")
    if expected_projection != observed_projection:
        findings.append("read-projection-mismatch")
    findings.extend(_stream_findings(observed_inventory))
    findings.extend(_allocator_findings(observed_inventory))
    return tuple(dict.fromkeys(findings))


def _stream_findings(inventory: dict[str, list[object]]) -> tuple[str, ...]:
    requests = [row for row in inventory["requests"] if isinstance(row, dict)]
    events = [row for row in inventory["request_events"] if isinstance(row, dict)]
    keys = [(str(row.get("aggregate_id")), int(row.get("sequence", 0))) for row in events]
    findings: list[str] = []
    if len(keys) != len(set(keys)):
        findings.append("duplicate-request-event")
    for request in requests:
        request_id = str(request.get("request_id"))
        version = int(request.get("version", 0))
        stream = sorted(
            (row for row in events if str(row.get("aggregate_id")) == request_id),
            key=lambda row: int(row.get("sequence", 0)),
        )
        sequences = [int(row.get("sequence", 0)) for row in stream]
        payload_versions = [
            int(payload.get("version", 0))
            for row in stream
            if isinstance((payload := row.get("payload")), dict)
        ]
        if sequences != list(range(1, version + 1)) or payload_versions != sequences:
            findings.append("gapped-or-unverifiable-request-stream")
    return tuple(findings)


def _allocator_findings(inventory: dict[str, list[object]]) -> tuple[str, ...]:
    allocators = [row for row in inventory["request_number_allocators"] if isinstance(row, dict)]
    requests = [row for row in inventory["requests"] if isinstance(row, dict)]
    maximum = max((int(row.get("request_number", 0)) for row in requests), default=0)
    if len(allocators) != 1 or int(allocators[0].get("last_number", -1)) != maximum:
        return ("request-allocator-mismatch",)
    return ()


def _assert_faults_quarantine(
    signed_inventory: dict[str, object],
    verifier: ArtifactVerifier,
    restored_inventory: dict[str, list[object]],
    restored_projection: dict[str, object],
) -> None:
    rebound = deepcopy(signed_inventory)
    rebound["tenant_id"] = str(uuid4())
    assert _restore_findings(rebound, verifier, restored_inventory, restored_projection) == (
        "unverifiable-signed-inventory",
    )

    missing = deepcopy(restored_inventory)
    missing["request_events"].pop()
    missing_findings = _restore_findings(signed_inventory, verifier, missing, restored_projection)
    assert "inventory-mismatch" in missing_findings
    assert "gapped-or-unverifiable-request-stream" in missing_findings

    duplicate = deepcopy(restored_inventory)
    duplicate["request_events"].append(deepcopy(duplicate["request_events"][0]))
    duplicate_findings = _restore_findings(
        signed_inventory, verifier, duplicate, restored_projection
    )
    assert "inventory-mismatch" in duplicate_findings
    assert "duplicate-request-event" in duplicate_findings

    changed_projection = deepcopy(restored_projection)
    watermark = changed_projection["watermark"]
    assert isinstance(watermark, int)
    changed_projection["watermark"] = watermark + 1
    assert "read-projection-mismatch" in _restore_findings(
        signed_inventory,
        verifier,
        restored_inventory,
        changed_projection,
    )


def _json_rows(
    connection: psycopg.Connection[tuple[object, ...]],
    statement: str,
    parameters: tuple[object, ...],
) -> list[object]:
    return [row[0] for row in connection.execute(statement, parameters)]


def _assert_event_complete(dsn: str, tenant_id: UUID) -> None:
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            """
            SELECT request.request_id, request.version,
                   count(event.event_id), min(event.sequence), max(event.sequence),
                   bool_and((event.payload ->> 'version')::integer = event.sequence)
            FROM requests AS request
            JOIN events AS event
              ON event.tenant_id = request.tenant_id
             AND event.aggregate_id = request.request_id
             AND event.kind = 'request.changed'
            WHERE request.tenant_id = %s
            GROUP BY request.request_id, request.version
            ORDER BY request.request_id
            """,
            (tenant_id,),
        ).fetchall()
        allocator = connection.execute(
            "SELECT last_number FROM request_number_allocators WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
        maximum = connection.execute(
            "SELECT max(request_number) FROM requests WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
    assert rows
    assert all(
        count == version and minimum == 1 and maximum_sequence == version
        for _, version, count, minimum, maximum_sequence, _payload_matches in rows
    )
    assert all(payload_matches for *_, payload_matches in rows)
    assert allocator is not None and maximum is not None
    assert allocator[0] == maximum[0]


def _digest(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


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
