"""Public custody transfer, isolation, concurrency, and restart acceptance."""

from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from support.server import running_api, start_and_admit
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_client import (
    CtowerClient,
    CtowerProblemError,
    CustodyTransferRequest,
    EvidenceRequest,
    FreezeCriteriaRequest,
    Priority,
    ProofCriterion,
    ResolveCloseRequest,
    SourceReference,
    TicketCreateRequest,
    VerdictDecision,
    VerdictRequest,
    WorkflowTransitionRequest,
)
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

HTTP_PENDING = 202
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
VERSION_AFTER_FIRST_TRANSFER = 2


def test_create_requires_authority_to_place_initial_custody(
    tenant: TenantFixture,
) -> None:
    occupied_ref = f"custody-authority:{uuid4()}"
    with _client(tenant) as client:
        occupied = client.post(
            "/v1/tickets",
            json={
                "priority": "P2",
                "source": {"kind": "mission-control", "ref": occupied_ref},
                "title": "Existing source owner",
            },
            headers={
                **_auth(tenant.commander_credential),
                "Idempotency-Key": str(uuid4()),
            },
        )
        delegated = client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(tenant.operator_id),
                "priority": "P2",
                "source": {"kind": "mission-control", "ref": occupied_ref},
                "title": "Unauthorized delegated custody",
            },
            headers={
                **_auth(tenant.commander_credential),
                "Idempotency-Key": str(uuid4()),
            },
        )
        operator_default = client.post(
            "/v1/tickets",
            json={
                "priority": "P2",
                "source": {
                    "kind": "mission-control",
                    "ref": f"operator-default:{uuid4()}",
                },
                "title": "Operator cannot default into custody",
            },
            headers={
                **_auth(tenant.operator_credential),
                "Idempotency-Key": str(uuid4()),
            },
        )

    assert occupied.status_code == HTTP_PENDING
    for refusal in (delegated, operator_default):
        assert refusal.status_code == HTTP_FORBIDDEN
        assert refusal.json()["code"] == "unauthorized"
        assert "unmet_facts" not in refusal.json()
    assert _source_ticket_count(tenant, "mission-control", occupied_ref) == 1


def test_atomic_reassign_exact_replay_and_stale_from(tenant: TenantFixture) -> None:
    ticket = _create_ticket(tenant)
    ticket_id = UUID(str(ticket["ticket_id"]))
    first_command = uuid4()
    with _client(tenant) as client:
        first = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=first_command,
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Operator suspension",
        )
        replay = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=first_command,
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Operator suspension",
        )
        stale = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=2,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Stale declared custodian",
        )
    _assert_transfer_outcomes(first, replay, stale)


def _assert_transfer_outcomes(
    first: Response,
    replay: Response,
    stale: Response,
) -> None:
    assert first.status_code == HTTP_PENDING
    assert first.content == replay.content
    assert first.json()["durability_state"] == "durability_pending"
    assert first.json()["ticket"]["version"] == VERSION_AFTER_FIRST_TRANSFER
    assert stale.status_code == HTTP_CONFLICT
    assert stale.json()["code"] == "version-conflict"
    assert stale.json()["current_version"] == VERSION_AFTER_FIRST_TRANSFER


def test_operator_custody_can_transfer_to_commander_after_restart(tenant: TenantFixture) -> None:
    ticket_id = UUID(str(_create_ticket(tenant)["ticket_id"]))
    with _client(tenant) as client:
        suspended = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Protected operator suspension",
        )
    assert suspended.status_code == HTTP_PENDING
    with _client(tenant) as client:
        transferred = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=2,
            from_id=tenant.operator_id,
            to_id=tenant.commander_id,
            reason="Commander accountability restored",
        )
    with _client(tenant) as restarted:
        shown = _show(restarted, tenant.operator_credential, ticket_id)
        timeline = _timeline(restarted, tenant.operator_credential, ticket_id)

    assert transferred.status_code == HTTP_PENDING
    assert shown.json() == transferred.json()["ticket"]
    assert shown.json()["custodian_id"] == str(tenant.commander_id)
    assert [event["sequence"] for event in timeline.json()["events"]] == [1, 2, 3]
    assert timeline.json()["events"][2]["payload"] == {
        "from_custodian_id": str(tenant.operator_id),
        "reason": "Commander accountability restored",
        "to_custodian_id": str(tenant.commander_id),
    }


def test_protected_authority_and_eligible_same_tenant_targets(tenant: TenantFixture) -> None:
    ticket_id = UUID(str(_create_ticket(tenant)["ticket_id"]))
    with _client(tenant) as client:
        unprotected = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Unprotected attempt",
            protected=False,
        )
        commander = _transfer(
            client,
            tenant.commander_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Commander cannot execute protected transfer",
        )
        ineligible = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=uuid4(),
            reason="Unknown target",
        )
        shown = _show(client, tenant.operator_credential, ticket_id)
        timeline = _timeline(client, tenant.operator_credential, ticket_id)

    assert unprotected.status_code == HTTP_FORBIDDEN
    assert commander.status_code == HTTP_FORBIDDEN
    assert ineligible.status_code == HTTP_NOT_FOUND
    assert shown.json()["custodian_id"] == str(tenant.commander_id)
    assert shown.json()["version"] == 1
    assert len(timeline.json()["events"]) == 1


def test_real_second_tenant_is_denied_without_existence_reveal(
    tenant: TenantFixture, second_tenant: TenantFixture
) -> None:
    ticket_id = UUID(str(_create_ticket(tenant)["ticket_id"]))
    missing_id = uuid4()
    with _client(second_tenant) as client:
        real_show = _show(client, second_tenant.operator_credential, ticket_id)
        missing_show = _show(client, second_tenant.operator_credential, missing_id)
        real_timeline = _timeline(client, second_tenant.operator_credential, ticket_id)
        foreign_target = _transfer(
            client,
            second_tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=second_tenant.commander_id,
            reason="Cross-tenant transfer refused",
        )

    assert real_show.status_code == missing_show.status_code == HTTP_NOT_FOUND
    assert real_show.content == missing_show.content
    assert real_timeline.status_code == HTTP_NOT_FOUND
    assert real_timeline.json()["code"] == "tenant-scope-denied"
    assert foreign_target.status_code == HTTP_NOT_FOUND
    assert foreign_target.json()["code"] == "tenant-scope-denied"


def test_concurrent_transfers_append_one_ordered_event(tenant: TenantFixture) -> None:
    ticket_id = UUID(str(_create_ticket(tenant)["ticket_id"]))

    def attempt() -> Response:
        with _client(tenant) as client:
            return _transfer(
                client,
                tenant.operator_credential,
                ticket_id=ticket_id,
                command_id=uuid4(),
                expected_version=1,
                from_id=tenant.commander_id,
                to_id=tenant.operator_id,
                reason="Concurrent protected transfer",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = tuple(executor.map(lambda _: attempt(), range(2)))

    assert sorted(response.status_code for response in responses) == [
        HTTP_PENDING,
        HTTP_CONFLICT,
    ]
    conflict = next(response for response in responses if response.status_code == HTTP_CONFLICT)
    assert conflict.json()["current_version"] == VERSION_AFTER_FIRST_TRANSFER
    with _client(tenant) as client:
        shown = _show(client, tenant.operator_credential, ticket_id)
        timeline = _timeline(client, tenant.operator_credential, ticket_id)
    assert shown.json()["version"] == VERSION_AFTER_FIRST_TRANSFER
    assert shown.json()["custodian_id"] == str(tenant.operator_id)
    events = timeline.json()["events"]
    assert [event["sequence"] for event in events] == [1, 2]
    assert len({event["event_id"] for event in events}) == VERSION_AFTER_FIRST_TRANSFER


def test_close_and_custody_race_serialize_without_dangling_ownership(
    tenant: TenantFixture,
) -> None:
    with running_api(tenant.database.runtime_dsn) as base_url:
        ticket_id = _terminal_public_ticket(base_url, tenant)
        barrier = threading.Barrier(2)

        def close() -> str:
            barrier.wait()
            with CtowerClient(base_url, credential=tenant.commander_credential) as client:
                client.resolve_close_workflow(
                    ticket_id,
                    ResolveCloseRequest(
                        expected_version=4,
                        workflow_ref="ctower.trust-spine-four-stage@1",
                    ),
                    command_id=uuid4(),
                )
            return "closed"

        def transfer() -> str:
            barrier.wait()
            with CtowerClient(base_url, credential=tenant.operator_credential) as client:
                try:
                    client.transfer_ticket_custody(
                        ticket_id,
                        CustodyTransferRequest(
                            expected_version=2,
                            from_custodian_id=tenant.commander_id,
                            protected_transfer=True,
                            reason="Race terminal close",
                            to_custodian_id=tenant.operator_id,
                        ),
                        command_id=uuid4(),
                    )
                except CtowerProblemError as error:
                    return error.problem.code
            return "transferred"

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (executor.submit(close), executor.submit(transfer))
            outcomes = tuple(future.result() for future in futures)

    assert outcomes[0] == "closed"
    assert outcomes[1] in {"transferred", "version-conflict"}
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT episode.state,
                (SELECT count(*) FROM assignment_intervals AS assignment
                 WHERE assignment.tenant_id = ticket.tenant_id
                   AND assignment.ticket_id = ticket.ticket_id
                   AND assignment.released_at IS NULL) AS open_assignments
            FROM tickets AS ticket
            JOIN lifecycle_episodes AS episode
              ON episode.tenant_id = ticket.tenant_id
             AND episode.ticket_id = ticket.ticket_id
             AND episode.episode_number = ticket.current_episode
            WHERE ticket.tenant_id = %s AND ticket.ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
    assert row == ("closed", 0)


def _terminal_public_ticket(base_url: str, tenant: TenantFixture) -> UUID:
    candidate = "sha256:" + "e" * 64
    content = "race proof"
    with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
        ticket_id = commander.create_ticket(
            TicketCreateRequest(
                initial_custodian_id=tenant.commander_id,
                priority=Priority.P1,
                source=SourceReference(kind="test", ref=f"test:close-race:{uuid4()}"),
                title="Close custody race",
            ),
            command_id=uuid4(),
        ).ticket.ticket_id
        start_and_admit(commander, ticket_id)
        _record_public_proof(commander, ticket_id, candidate, content)
    with CtowerClient(base_url, credential=tenant.operator_credential) as operator:
        operator.record_proof_verdict(
            ticket_id,
            VerdictRequest(
                expected_version=2,
                verdict_id=uuid4(),
                criterion_key="artifact-current",
                candidate_digest=candidate,
                decision=VerdictDecision.PASS,
            ),
            command_id=uuid4(),
        )
    with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
        commander.transition_workflow(
            ticket_id,
            WorkflowTransitionRequest(
                expected_version=3,
                workflow_ref="ctower.trust-spine-four-stage@1",
                source_stage="verify",
                destination_stage="close",
            ),
            command_id=uuid4(),
        )
    return ticket_id


def _record_public_proof(
    commander: CtowerClient, ticket_id: UUID, candidate: str, content: str
) -> None:
    commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=1,
            workflow_ref="ctower.trust-spine-four-stage@1",
            source_stage="capture",
            destination_stage="frame",
        ),
        command_id=uuid4(),
    )
    commander.freeze_proof_criteria(
        ticket_id,
        FreezeCriteriaRequest(
            expected_version=0,
            candidate_digest=candidate,
            criteria=(
                ProofCriterion(
                    key="artifact-current",
                    description="Artifact evidence matches the current candidate.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
        command_id=uuid4(),
    )
    commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=2,
            workflow_ref="ctower.trust-spine-four-stage@1",
            source_stage="frame",
            destination_stage="verify",
        ),
        command_id=uuid4(),
    )
    commander.record_proof_evidence(
        ticket_id,
        EvidenceRequest(
            expected_version=1,
            evidence_id=uuid4(),
            criterion_key="artifact-current",
            candidate_digest=candidate,
            artifact_digest="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
            content=content,
        ),
        command_id=uuid4(),
    )


def test_one_principal_command_key_is_reserved_before_different_aggregate_work(
    tenant: TenantFixture,
) -> None:
    ticket = _create_ticket(tenant)
    ticket_id = UUID(str(ticket["ticket_id"]))
    command_id = uuid4()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            CREATE FUNCTION delay_command_result() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_sleep(0.25);
                RETURN NEW;
            END
            $$;
            CREATE TRIGGER delay_command_result BEFORE INSERT ON command_results
                FOR EACH ROW EXECUTE FUNCTION delay_command_result();
            """
        )

    def create_different_ticket() -> Response:
        with TestClient(
            create_app(PostgresRecord(tenant.database.runtime_dsn)),
            client=("127.0.0.1", 51000),
            raise_server_exceptions=False,
        ) as client:
            return cast(
                Response,
                client.post(
                    "/v1/tickets",
                    json={
                        "initial_custodian_id": str(tenant.commander_id),
                        "priority": "P1",
                        "source": {"kind": "mission-control", "ref": "idempotency:create"},
                        "title": "Competing command",
                    },
                    headers={
                        **_auth(tenant.operator_credential),
                        "Idempotency-Key": str(command_id),
                    },
                ),
            )

    def transfer_existing_ticket() -> Response:
        with TestClient(
            create_app(PostgresRecord(tenant.database.runtime_dsn)),
            client=("127.0.0.1", 51000),
            raise_server_exceptions=False,
        ) as client:
            return _transfer(
                client,
                tenant.operator_credential,
                ticket_id=ticket_id,
                command_id=command_id,
                expected_version=1,
                from_id=tenant.commander_id,
                to_id=tenant.operator_id,
                reason="Competing command key",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = tuple(
            future.result()
            for future in (
                executor.submit(create_different_ticket),
                executor.submit(transfer_existing_ticket),
            )
        )

    assert sorted(response.status_code for response in responses) == [HTTP_PENDING, HTTP_CONFLICT]
    conflict = next(response for response in responses if response.status_code == HTTP_CONFLICT)
    assert conflict.json()["code"] == "idempotency-conflict"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM command_results WHERE client_command_id = %s),
                (SELECT count(*) FROM events)
            """,
            (command_id,),
        ).fetchone()
    assert counts == (1, 3)


def test_service_role_cannot_update_or_delete_immutable_record_rows(
    tenant: TenantFixture,
) -> None:
    statements = (
        "UPDATE events SET payload = payload WHERE false",
        "DELETE FROM events WHERE false",
        "UPDATE command_results SET response_body = response_body WHERE false",
        "DELETE FROM command_results WHERE false",
        "UPDATE outbox SET payload = payload WHERE false",
        "DELETE FROM outbox WHERE false",
    )

    for statement in statements:
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            psycopg.connect(tenant.database.runtime_dsn) as connection,
        ):
            connection.execute("SET ROLE ctower_svc")
            connection.execute(statement)


def test_runtime_login_cannot_assume_migration_authority(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.runtime_dsn) as connection:
        current_user = connection.execute("SELECT current_user").fetchone()
        assert current_user == ("ctower_runtime",)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("SET ROLE ctower_admin")


def _client(tenant: TenantFixture) -> TestClient:
    return TestClient(
        create_app(PostgresRecord(tenant.database.runtime_dsn)), client=("127.0.0.1", 51000)
    )


def _create_ticket(tenant: TenantFixture, *, custodian_id: UUID | None = None) -> dict[str, object]:
    with _client(tenant) as client:
        response = client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(custodian_id or tenant.commander_id),
                "priority": "P1",
                "source": {"kind": "mission-control", "ref": "mission-control:custody"},
                "title": "Custody acceptance ticket",
            },
            headers={
                **_auth(tenant.operator_credential),
                "Idempotency-Key": str(uuid4()),
            },
        )
    assert response.status_code == HTTP_PENDING
    return cast(dict[str, object], response.json()["ticket"])


def _transfer(
    client: TestClient,
    credential: str,
    *,
    ticket_id: UUID,
    command_id: UUID,
    expected_version: int,
    from_id: UUID,
    to_id: UUID,
    reason: str,
    protected: bool = True,
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/tickets/{ticket_id}/custody",
            json={
                "expected_version": expected_version,
                "from_custodian_id": str(from_id),
                "protected_transfer": protected,
                "reason": reason,
                "to_custodian_id": str(to_id),
            },
            headers={**_auth(credential), "Idempotency-Key": str(command_id)},
        ),
    )


def _show(client: TestClient, credential: str, ticket_id: UUID) -> Response:
    return cast(
        Response,
        client.get(f"/v1/tickets/{ticket_id}", headers=_auth(credential)),
    )


def _timeline(client: TestClient, credential: str, ticket_id: UUID) -> Response:
    return cast(
        Response,
        client.get(f"/v1/tickets/{ticket_id}/timeline", headers=_auth(credential)),
    )


def _auth(credential: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credential}",
        **telemetry_headers(),
    }


def _source_ticket_count(tenant: TenantFixture, source_kind: str, source_ref: str) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT count(*) FROM tickets
            WHERE tenant_id = %s AND source_kind = %s AND source_ref = %s
            """,
            (tenant.tenant_id, source_kind, source_ref),
        ).fetchone()
    if row is None:
        raise RuntimeError("ticket count query returned no row")
    return int(row[0])
