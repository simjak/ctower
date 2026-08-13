"""TestClient plus real-PostgreSQL acceptance for Request-maintenance proposals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from support.acceptance import accept_pending_commands
from support.server import application
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_kernel.workflow import WorkflowGraph

__all__: tuple[str, ...] = ()
HTTP_OK = 200
HTTP_PENDING = 202
HTTP_FORBIDDEN = 403
HTTP_CONFLICT = 409
CONFIRMED_REQUEST_VERSION = 2
PROPOSAL_EVENT_COUNT = 2
ROOT = Path(__file__).parents[3]


def test_append_is_separate_and_similarity_preserves_both_requests_until_operator_confirm(
    tenant: TenantFixture,
) -> None:
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        first_command, first = _capture(client, tenant, "Keep the first exact Request text.")
        _, second = _capture(client, tenant, "Keep the second exact Request text.")
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        before = _request_snapshot(tenant, _uuid(first["request_id"]))
        listing = _request_list(client, tenant)
        target = _row(listing, _uuid(first["request_id"]))
        related = _row(listing, _uuid(second["request_id"]))
        evidence = _event_evidence(tenant, first_command)

        tampered = client.post(
            "/v1/request-maintenance/proposals",
            headers=_mutation_headers(tenant.commander_credential),
            json=_append_payload(
                target,
                evidence,
                kind="keep",
                target_text="A semantic paraphrase is not the exact Request.",
            ),
        )
        appended = client.post(
            "/v1/request-maintenance/proposals",
            headers=_mutation_headers(tenant.commander_credential),
            json=_append_payload(
                target,
                evidence,
                kind="duplicate",
                basis="similarity",
                related=related,
            ),
        )

        assert tampered.status_code == HTTP_CONFLICT
        assert tampered.json()["code"] == "proposal-quote-mismatch"
        assert appended.status_code == HTTP_PENDING
        receipt = appended.json()
        assert receipt["ambiguity_reason"] == "duplicate-uncertain"
        assert _request_snapshot(tenant, _uuid(first["request_id"])) == before

        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        proposal_id = UUID(receipt["proposal_id"])
        proposal = _proposal(client, tenant, proposal_id)
        assert proposal["target_request_id"] == first["request_id"]
        assert proposal["related_request_id"] == second["request_id"]
        assert proposal["target_text"] == target["content"]
        assert proposal["related_text"] == related["content"]
        assert proposal["proposer_principal_id"] == str(tenant.commander_id)
        assert proposal["seat_credential_id"] is None
        assert _request_snapshot(tenant, _uuid(first["request_id"])) == before

        unscoped = client.get(
            "/v1/request-maintenance/proposals",
            headers=_query_headers(tenant.commander_credential),
        )
        scoped = client.get(
            "/v1/request-maintenance/proposals",
            headers=_query_headers(tenant.commander_credential),
            params={"project_key": "ctower"},
        )
        assert unscoped.status_code == HTTP_FORBIDDEN
        assert scoped.status_code == HTTP_OK

        _assert_duplicate_confirmation(client, tenant, proposal_id, _uuid(first["request_id"]))


def test_rejection_is_immutable_terminal_history_and_stale_targets_remain_open(
    tenant: TenantFixture,
) -> None:
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        capture_command, captured = _capture(client, tenant, "A Request retained after rejection.")
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        target = _row(_request_list(client, tenant), _uuid(captured["request_id"]))
        evidence = _event_evidence(tenant, capture_command)
        stale = client.post(
            "/v1/request-maintenance/proposals",
            headers=_mutation_headers(tenant.commander_credential),
            json=_append_payload(target, evidence, kind="kill", expected_version=99),
        )
        assert stale.status_code == HTTP_PENDING
        assert stale.json()["ambiguity_reason"] == "target-version-stale"
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        stale_id = UUID(stale.json()["proposal_id"])
        assert _proposal(client, tenant, stale_id)["state"] == "OPEN"

        reject_headers = _mutation_headers(tenant.operator_credential)
        rejected = client.post(
            f"/v1/request-maintenance/proposals/{stale_id}/reject",
            headers=reject_headers,
            json={"expected_proposal_version": 1},
        )
        assert rejected.status_code == HTTP_PENDING
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        replay = client.post(
            f"/v1/request-maintenance/proposals/{stale_id}/reject",
            headers=reject_headers,
            json={"expected_proposal_version": 1},
        )
        second_decision = client.post(
            f"/v1/request-maintenance/proposals/{stale_id}/confirm",
            headers=_mutation_headers(tenant.operator_credential),
            json={"expected_proposal_version": 1},
        )
        retained = _proposal(client, tenant, stale_id)

    assert replay.status_code == HTTP_OK
    assert retained["state"] == "REJECTED"
    decision = cast(dict[str, object], retained["decision"])
    assert decision["reason"] is None
    assert second_decision.status_code == HTTP_CONFLICT
    assert second_decision.json()["code"] == "proposal-already-decided"
    _assert_database_immutability(tenant, stale_id)


def test_all_ambiguity_reasons_are_typed_open_facts(tenant: TenantFixture) -> None:
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        first_command, first = _capture(client, tenant, "Primary ambiguity Request.")
        _, second = _capture(client, tenant, "Related ambiguity Request.")
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        listing = _request_list(client, tenant)
        target = _row(listing, _uuid(first["request_id"]))
        related = _row(listing, _uuid(second["request_id"]))
        evidence = _event_evidence(tenant, first_command)
        before_target = _request_snapshot(tenant, _uuid(first["request_id"]))
        before_related = _request_snapshot(tenant, _uuid(second["request_id"]))
        cases = (
            _append_payload(
                target,
                evidence,
                kind="keep",
                ambiguity="evidence-conflicting-or-incomplete",
            ),
            _append_payload(
                target,
                evidence,
                kind="supersession",
                related=related,
                ambiguity="supersession-unclear",
            ),
            _append_payload(target, evidence, kind="kill", expected_version=99),
            _append_payload(target, evidence, kind="completed-but-open"),
            _append_payload(
                target,
                evidence,
                kind="duplicate",
                basis="similarity",
                related=related,
            ),
        )
        responses = tuple(
            client.post(
                "/v1/request-maintenance/proposals",
                headers=_mutation_headers(tenant.commander_credential),
                json=case,
            )
            for case in cases
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        reasons = {
            _proposal(client, tenant, UUID(response.json()["proposal_id"]))["ambiguity_reason"]
            for response in responses
        }
        assert _request_snapshot(tenant, _uuid(first["request_id"])) == before_target
        assert _request_snapshot(tenant, _uuid(second["request_id"])) == before_related

    assert all(response.status_code == HTTP_PENDING for response in responses)
    assert reasons == {
        "completion-unproven",
        "duplicate-uncertain",
        "evidence-conflicting-or-incomplete",
        "supersession-unclear",
        "target-version-stale",
    }


def test_completed_proposal_requires_current_closed_required_ticket_evidence(
    tenant: TenantFixture,
) -> None:
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        _, captured = _capture(client, tenant, "Completion evidence must belong to this Request.")
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        target = _row(_request_list(client, tenant), _uuid(captured["request_id"]))
        unrelated = _proof_pointer(client, tenant, "unrelated")
        unproven = client.post(
            "/v1/request-maintenance/proposals",
            headers=_mutation_headers(tenant.commander_credential),
            json=_append_payload(target, unrelated, kind="completed-but-open"),
        )
        assert unproven.status_code == HTTP_PENDING
        assert unproven.json()["ambiguity_reason"] == "completion-unproven"
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

        prioritized = client.post(
            f"/v1/requests/{captured['request_id']}/priority",
            headers=_mutation_headers(tenant.operator_credential),
            json={"expected_version": 1, "priority": "P2", "reason": "Fulfillment."},
        )
        assert prioritized.status_code == HTTP_PENDING, prioritized.json()
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        triaged = client.post(
            f"/v1/requests/{captured['request_id']}/triage",
            headers=_mutation_headers(tenant.operator_credential),
            json={
                "canonical_request_id": None,
                "disposition": "ACCEPTED",
                "expected_version": 2,
                "reason": None,
            },
        )
        assert triaged.status_code == HTTP_PENDING, triaged.json()
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        shipped = _proof_pointer(client, tenant, "required")
        _relate_required_ticket(client, tenant, captured["request_id"], shipped, 3)
        also_required = _proof_pointer(client, tenant, "also-required")
        _relate_required_ticket(client, tenant, captured["request_id"], also_required, 4)
        current = _row(_request_list(client, tenant), _uuid(captured["request_id"]))
        incomplete_payload = _append_payload(
            current, also_required, kind="completed-but-open", expected_version=5
        )
        incomplete_payload["evidence"] = _evidence_payload(shipped)
        incomplete = client.post(
            "/v1/request-maintenance/proposals",
            headers=_mutation_headers(tenant.commander_credential),
            json=incomplete_payload,
        )
        assert incomplete.status_code == HTTP_PENDING
        assert incomplete.json()["ambiguity_reason"] == "completion-unproven"
        complete_payload = _append_payload(
            current, also_required, kind="completed-but-open", expected_version=5
        )
        complete_payload["evidence"] = _evidence_payload(shipped, also_required)
        proven = client.post(
            "/v1/request-maintenance/proposals",
            headers=_mutation_headers(tenant.commander_credential),
            json=complete_payload,
        )

    assert proven.status_code == HTTP_PENDING
    assert proven.json()["ambiguity_reason"] is None


def test_confirm_time_related_request_race_refuses_target_command_without_merge(
    tenant: TenantFixture,
) -> None:
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        target_command, target_receipt = _capture(client, tenant, "Race target exact text.")
        _, related_receipt = _capture(client, tenant, "Race related exact text.")
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        listing = _request_list(client, tenant)
        target = _row(listing, _uuid(target_receipt["request_id"]))
        related = _row(listing, _uuid(related_receipt["request_id"]))
        appended = client.post(
            "/v1/request-maintenance/proposals",
            headers=_mutation_headers(tenant.commander_credential),
            json=_append_payload(
                target,
                _event_evidence(tenant, target_command),
                kind="duplicate",
                related=related,
            ),
        )
        assert appended.status_code == HTTP_PENDING
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        proposal_id = UUID(appended.json()["proposal_id"])
        before = _request_snapshot(tenant, _uuid(target_receipt["request_id"]))

        priority = client.post(
            f"/v1/requests/{related_receipt['request_id']}/priority",
            headers=_mutation_headers(tenant.commander_credential),
            json={"expected_version": 1, "priority": "P1", "reason": "Recorded race."},
        )
        assert priority.status_code == HTTP_PENDING
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        confirmed = client.post(
            f"/v1/request-maintenance/proposals/{proposal_id}/confirm",
            headers=_mutation_headers(tenant.operator_credential),
            json={"expected_proposal_version": 1},
        )

    assert confirmed.status_code == HTTP_PENDING
    assert confirmed.json()["target_outcome"] == "refused"
    assert confirmed.json()["target_problem_code"] == "proposal-related-changed"
    assert _request_snapshot(tenant, _uuid(target_receipt["request_id"])) == before


def test_existing_operator_path_can_directly_triage_a_request(tenant: TenantFixture) -> None:
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        _, captured = _capture(client, tenant, "Direct operator triage uses ordinary authority.")
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        triaged = client.post(
            f"/v1/requests/{captured['request_id']}/triage",
            headers=_mutation_headers(tenant.operator_credential),
            json={
                "canonical_request_id": None,
                "disposition": "REJECTED",
                "expected_version": 1,
                "reason": "Operator used the existing protected triage path.",
            },
        )

    assert triaged.status_code == HTTP_PENDING
    assert triaged.json()["operation"] == "triage"


def _capture(
    client: TestClient, tenant: TenantFixture, text: str
) -> tuple[UUID, dict[str, object]]:
    command_id = uuid4()
    response = client.post(
        "/v1/requests",
        headers=_mutation_headers(tenant.commander_credential, command_id),
        json={"project_key": "ctower", "text": text},
    )
    assert response.status_code == HTTP_PENDING
    return command_id, cast(dict[str, object], response.json())


def _assert_duplicate_confirmation(
    client: TestClient,
    tenant: TenantFixture,
    proposal_id: UUID,
    request_id: UUID,
) -> None:
    commander = client.post(
        f"/v1/request-maintenance/proposals/{proposal_id}/confirm",
        headers=_mutation_headers(tenant.commander_credential),
        json={"expected_proposal_version": 1},
    )
    confirmation_headers = _mutation_headers(tenant.operator_credential)
    confirmed = client.post(
        f"/v1/request-maintenance/proposals/{proposal_id}/confirm",
        headers=confirmation_headers,
        json={"expected_proposal_version": 1},
    )
    assert commander.status_code == HTTP_FORBIDDEN
    assert commander.json()["code"] == "proposal-decision-forbidden"
    assert confirmed.status_code == HTTP_PENDING
    decision = confirmed.json()
    assert decision["operation"] == "confirmed"
    assert decision["target_outcome"] == "accepted"
    assert decision["target_command_id"] != decision["command_id"]

    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    replay = client.post(
        f"/v1/request-maintenance/proposals/{proposal_id}/confirm",
        headers=confirmation_headers,
        json={"expected_proposal_version": 1},
    )
    changed = _row(_request_list(client, tenant), request_id)
    assert replay.status_code == HTTP_OK
    assert replay.json()["decision_id"] == decision["decision_id"]
    assert _request_snapshot(tenant, request_id)[0] == CONFIRMED_REQUEST_VERSION
    assert changed["triage"] == "DUPLICATE"
    assert _proposal_event_count(tenant, proposal_id) == PROPOSAL_EVENT_COUNT


def _request_list(client: TestClient, tenant: TenantFixture) -> dict[str, object]:
    response = client.get(
        "/v1/requests",
        headers=_query_headers(tenant.commander_credential),
        params={"project_key": "ctower"},
    )
    assert response.status_code == HTTP_OK
    return cast(dict[str, object], response.json())


def _row(listing: dict[str, object], request_id: UUID) -> dict[str, object]:
    return next(
        cast(dict[str, object], row)
        for row in cast(list[object], listing["rows"])
        if cast(dict[str, object], row)["request_id"] == str(request_id)
    )


def _event_evidence(tenant: TenantFixture, command_id: UUID) -> dict[str, object]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT event_id, kind, event_hash
            FROM events
            WHERE tenant_id = %s AND client_command_id = %s AND kind = 'request.changed'
            """,
            (tenant.tenant_id, command_id),
        ).fetchone()
    assert row is not None
    return {
        "event_digest": f"sha256:{bytes(row['event_hash']).hex()}",
        "event_id": str(row["event_id"]),
        "event_kind": str(row["kind"]),
        "kind": "record-event",
        "_source_record_position": _record_watermark(tenant),
    }


def _proof_pointer(client: TestClient, tenant: TenantFixture, label: str) -> dict[str, object]:
    ticket_id = _proof_ticket(client, tenant, label)
    candidate = "sha256:" + "c" * 64
    frozen = client.post(
        f"/v1/tickets/{ticket_id}/proof/criteria",
        headers=_mutation_headers(tenant.commander_credential),
        json={
            "candidate_digest": candidate,
            "criteria": [
                {
                    "candidate_dependent": True,
                    "description": "Artifact evidence matches the current candidate.",
                    "key": "artifact-current",
                    "requires_verdict": True,
                }
            ],
            "expected_version": 0,
        },
    )
    assert frozen.status_code == HTTP_PENDING, frozen.json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    content = f"accepted shipped proof {label}"
    artifact = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    evidence_id = uuid4()
    recorded = client.post(
        f"/v1/tickets/{ticket_id}/proof/evidence",
        headers=_mutation_headers(tenant.commander_credential),
        json={
            "artifact_digest": artifact,
            "candidate_digest": candidate,
            "content": content,
            "criterion_key": "artifact-current",
            "evidence_id": str(evidence_id),
            "expected_version": 1,
        },
    )
    assert recorded.status_code == HTTP_PENDING, recorded.json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return {
        "artifact_digest": artifact,
        "evidence_id": str(evidence_id),
        "kind": "proof-evidence",
        "proof_id": frozen.json()["proof_id"],
        "ticket_id": str(ticket_id),
        "_source_record_position": _record_watermark(tenant),
    }


def _proof_ticket(client: TestClient, tenant: TenantFixture, label: str) -> UUID:
    ticket = client.post(
        "/v1/tickets",
        headers=_mutation_headers(tenant.commander_credential),
        json={
            "initial_custodian_id": str(tenant.commander_id),
            "priority": "P2",
            "project_key": "ctower",
            "source": {"kind": "test", "ref": f"proposal-proof:{label}:{uuid4()}"},
            "title": f"Proposal proof {label}",
        },
    )
    assert ticket.status_code == HTTP_PENDING
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    ticket_id = UUID(ticket.json()["ticket"]["ticket_id"])
    graph = WorkflowGraph.from_mapping(
        json.loads((ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text())
    )
    started = client.post(
        f"/v1/tickets/{ticket_id}/workflow/start",
        headers=_mutation_headers(tenant.commander_credential),
        json={
            "workflow_ref": graph.reference,
            "workflow_digest": graph.digest,
            **_policy_digests(),
        },
    )
    assert started.status_code == HTTP_PENDING, started.json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return ticket_id


def _close_ticket(tenant: TenantFixture, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """UPDATE lifecycle_episodes SET state = 'closed', closed_at = now()
               WHERE tenant_id = %s AND ticket_id = %s""",
            (tenant.tenant_id, ticket_id),
        )


def _relate_required_ticket(
    client: TestClient,
    tenant: TenantFixture,
    request_id: object,
    evidence: dict[str, object],
    expected_version: int,
) -> None:
    relation = client.post(
        f"/v1/requests/{request_id}/ticket-relations",
        headers=_mutation_headers(tenant.commander_credential),
        json={
            "active": True,
            "expected_ticket_version": 1,
            "expected_version": expected_version,
            "purpose": "required",
            "reason": "This Ticket fulfills the Request.",
            "ticket_id": evidence["ticket_id"],
        },
    )
    assert relation.status_code == HTTP_PENDING, relation.json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    _close_ticket(tenant, UUID(str(evidence["ticket_id"])))


def _evidence_payload(*items: dict[str, object]) -> list[dict[str, object]]:
    return [
        {key: value for key, value in item.items() if not key.startswith("_")} for item in items
    ]


def _policy_digests() -> dict[str, str]:
    result: dict[str, str] = {}
    policy_names = (
        ("execution", "execution"),
        ("gates", "gate"),
        ("evidence", "evidence"),
    )
    for directory, name in policy_names:
        path = ROOT / f"packs/policies/{directory}/trust-spine-four-stage-v1.yaml"
        result[f"{name}_policy_ref"] = f"ctower.trust-spine-four-stage.{directory}@1"
        result[f"{name}_policy_digest"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _append_payload(
    target: dict[str, object],
    evidence: dict[str, object],
    *,
    kind: str,
    basis: str = "recorded-evidence",
    related: dict[str, object] | None = None,
    target_text: str | None = None,
    expected_version: int | None = None,
    ambiguity: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ambiguity_reason": ambiguity,
        "basis": basis,
        "evidence": [{key: value for key, value in evidence.items() if not key.startswith("_")}],
        "kind": kind,
        "project_key": target["project_key"],
        "source_record_position": evidence["_source_record_position"],
        "target_expected_version": expected_version or 1,
        "target_request_id": target["request_id"],
        "target_text": target_text or target["content"],
    }
    if related is not None:
        payload.update(
            related_expected_version=1,
            related_request_id=related["request_id"],
            related_text=related["content"],
        )
    return payload


def _proposal(client: TestClient, tenant: TenantFixture, proposal_id: UUID) -> dict[str, object]:
    response = client.get(
        "/v1/request-maintenance/proposals",
        headers=_query_headers(tenant.operator_credential),
        params={"proposal_id": str(proposal_id)},
    )
    assert response.status_code == HTTP_OK
    rows = response.json()["rows"]
    assert len(rows) == 1
    return cast(dict[str, object], rows[0])


def _request_snapshot(tenant: TenantFixture, request_id: UUID) -> tuple[object, ...]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT request.version, request.content,
                   (SELECT count(*) FROM events
                    WHERE stream_id = 'request:' || request.request_id::text),
                   (SELECT count(*) FROM request_triage_facts
                    WHERE request_id = request.request_id),
                   (SELECT count(*) FROM request_ticket_relation_facts
                    WHERE request_id = request.request_id),
                   (SELECT count(*) FROM request_blocker_facts
                    WHERE request_id = request.request_id),
                   (SELECT count(*) FROM request_closure_evaluations
                    WHERE request_id = request.request_id)
            FROM requests AS request WHERE request.request_id = %s
            """,
            (request_id,),
        ).fetchone()
    assert row is not None
    return cast(tuple[object, ...], row)


def _record_watermark(tenant: TenantFixture) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT last_position FROM record_position_ledger WHERE singleton"
        ).fetchone()
    assert row is not None
    return int(row[0])


def _proposal_event_count(tenant: TenantFixture, proposal_id: UUID) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT count(*) FROM events WHERE stream_id = %s",
            (f"request-proposal:{proposal_id}",),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _assert_database_immutability(tenant: TenantFixture, proposal_id: UUID) -> None:
    for statement in (
        "UPDATE request_maintenance_proposals SET kind = 'keep' WHERE proposal_id = %s",
        "DELETE FROM request_maintenance_proposals WHERE proposal_id = %s",
        "UPDATE request_maintenance_proposal_evidence SET recorded_at = recorded_at "
        "WHERE proposal_id = %s",
        "DELETE FROM request_maintenance_proposal_evidence WHERE proposal_id = %s",
        "UPDATE request_maintenance_proposal_decisions SET reason = reason WHERE proposal_id = %s",
        "DELETE FROM request_maintenance_proposal_decisions WHERE proposal_id = %s",
    ):
        with (
            pytest.raises(psycopg.Error),
            psycopg.connect(tenant.database.admin_dsn) as connection,
        ):
            connection.execute(statement, (proposal_id,))


def _mutation_headers(credential: str, command_id: UUID | None = None) -> dict[str, str]:
    identity = command_id or uuid4()
    return {
        "Authorization": f"Bearer {credential}",
        "Idempotency-Key": str(identity),
        **telemetry_headers(identity),
    }


def _query_headers(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}", **telemetry_headers()}


def _uuid(value: object) -> UUID:
    return UUID(str(value))
