"""Generated-client acceptance through a separate API process and real PostgreSQL."""

from __future__ import annotations

import io
import secrets
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from support.postgres import DatabaseFixture
from support.server import running_api
from support.telemetry import telemetry_headers
from support.tenant_fixture import provision_credential

from ctower_client import (
    BootstrapRequest,
    CtowerClient,
    CtowerProblemError,
    CustodyTransferRequest,
    Priority,
    Problem,
    SourceReference,
    TelemetryContext,
    TicketCommandResult,
    TicketCreateRequest,
)
from ctower_kernel.record.postgres import (
    apply_migrations,
    provision_bootstrap,
    provision_database_roles,
)

__all__: tuple[str, ...] = ()

TRANSFERRED_VERSION = 2


@dataclass(frozen=True, slots=True)
class _ProcessTenant:
    database: DatabaseFixture
    base_url: str
    tenant_id: UUID
    operator_id: UUID
    commander_id: UUID
    credential: str


@pytest.fixture
def process_tenant(database: DatabaseFixture) -> Iterator[_ProcessTenant]:
    provision_database_roles(database.admin_dsn)
    apply_migrations(database.migrator_dsn)
    capability = secrets.token_urlsafe(32)
    provision_bootstrap(
        database.migrator_dsn,
        capability_input=io.StringIO(f"{capability}\n"),
        allowed_origin="127.0.0.1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    with running_api(database.runtime_dsn) as base_url, CtowerClient(base_url) as client:
        receipt = client.bootstrap_first_tenant(
            _bootstrap_request(), command_id=uuid4(), capability=capability
        )
        credential = secrets.token_urlsafe(32)
        provision_credential(database.admin_dsn, receipt.tenant_id, receipt.operator_id, credential)
        yield _ProcessTenant(
            database,
            base_url,
            receipt.tenant_id,
            receipt.operator_id,
            receipt.commander_id,
            credential,
        )


def test_generated_client_crosses_real_process_for_complete_ticket_slice(
    process_tenant: _ProcessTenant,
) -> None:
    tenant = process_tenant
    created = _create(tenant, uuid4(), title="Separate-process ticket")
    with _client(tenant) as client:
        shown = client.get_ticket(created.ticket.ticket_id)
        timeline = client.get_ticket_timeline(created.ticket.ticket_id)
        transferred = client.transfer_ticket_custody(
            created.ticket.ticket_id,
            _custody_request(tenant, reason="Generated-client acceptance"),
            command_id=uuid4(),
        )

    assert shown == created.ticket
    assert [event.kind for event in timeline.events] == ["ticket.created"]
    assert transferred.ticket.version == TRANSFERRED_VERSION
    assert transferred.ticket.custodian_id == tenant.operator_id


def test_process_auth_precedes_validation_and_decodes_typed_problems(
    process_tenant: _ProcessTenant,
) -> None:
    tenant = process_tenant
    with httpx.Client(base_url=tenant.base_url) as raw:
        malformed_body = raw.post("/v1/tickets", content=b"{")
        malformed_path = raw.get("/v1/tickets/not-a-uuid")
        validation = raw.post(
            "/v1/tickets",
            content=b"{",
            headers={
                "Authorization": f"Bearer {tenant.credential}",
                **telemetry_headers(),
            },
        )
    denied_body = Problem.model_validate_json(malformed_body.content)
    denied_path = Problem.model_validate_json(malformed_path.content)
    invalid = Problem.model_validate_json(validation.content)
    assert denied_body == denied_path
    assert (denied_body.status, denied_body.code) == (401, "unauthorized")
    assert (invalid.status, invalid.code) == (422, "validation-error")
    with (
        CtowerClient(tenant.base_url, credential="invalid-credential") as denied,
        pytest.raises(CtowerProblemError) as raised,
    ):
        denied.get_ticket(uuid4())
    assert cast(Problem, raised.value.problem).code == "unauthorized"


def test_process_exact_replay_and_changed_body_conflict(
    process_tenant: _ProcessTenant,
) -> None:
    tenant = process_tenant
    command_id = uuid4()
    request = _ticket_request(tenant, title="Replay authority")
    with _client(tenant) as client:
        first = client.create_ticket(request, command_id=command_id)
        replay = client.create_ticket(request, command_id=command_id)
        with pytest.raises(CtowerProblemError) as raised:
            client.create_ticket(
                _ticket_request(tenant, title="Changed replay body"), command_id=command_id
            )

    assert replay == first
    assert cast(Problem, raised.value.problem).code == "idempotency-conflict"
    assert _command_counts(tenant.database.admin_dsn, command_id) == (1, 1, 1)


def test_process_same_ticket_concurrency_serializes_one_transfer(
    process_tenant: _ProcessTenant,
) -> None:
    tenant = process_tenant
    ticket = _create(tenant, uuid4(), title="Same-ticket concurrency")

    def transfer(command_id: UUID) -> TicketCommandResult | Problem:
        with _client(tenant) as client:
            return _outcome(
                lambda: client.transfer_ticket_custody(
                    ticket.ticket.ticket_id,
                    _custody_request(tenant, reason="Concurrent same-ticket transfer"),
                    command_id=command_id,
                )
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(transfer, (uuid4(), uuid4())))

    successes = [item for item in outcomes if isinstance(item, TicketCommandResult)]
    failures = [item for item in outcomes if isinstance(item, Problem)]
    assert len(successes) == len(failures) == 1
    assert successes[0].ticket.version == TRANSFERRED_VERSION
    assert failures[0].code == "version-conflict"


def test_process_cross_aggregate_command_race_has_one_typed_conflict(
    process_tenant: _ProcessTenant,
) -> None:
    tenant = process_tenant
    ticket = _create(tenant, uuid4(), title="Existing aggregate")
    command_id = uuid4()
    _install_command_delay(tenant.database.admin_dsn)

    def create() -> TicketCommandResult | Problem:
        with _client(tenant) as client:
            return _outcome(
                lambda: client.create_ticket(
                    _ticket_request(tenant, title="Competing aggregate"), command_id=command_id
                )
            )

    def transfer() -> TicketCommandResult | Problem:
        with _client(tenant) as client:
            return _outcome(
                lambda: client.transfer_ticket_custody(
                    ticket.ticket.ticket_id,
                    _custody_request(tenant, reason="Competing aggregate command"),
                    command_id=command_id,
                )
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(create), executor.submit(transfer))
        outcomes = tuple(future.result() for future in futures)

    assert len([item for item in outcomes if isinstance(item, TicketCommandResult)]) == 1
    problems = [item for item in outcomes if isinstance(item, Problem)]
    assert len(problems) == 1 and problems[0].code == "idempotency-conflict"
    assert _command_counts(tenant.database.admin_dsn, command_id) == (1, 1, 1)


def test_process_outbox_failure_rolls_back_and_same_command_retries(
    process_tenant: _ProcessTenant,
) -> None:
    tenant = process_tenant
    command_id = uuid4()
    _install_outbox_failure(tenant.database.admin_dsn)
    with _client(tenant) as client, pytest.raises(httpx.HTTPStatusError):
        client.create_ticket(
            _ticket_request(tenant, title="Rollback process failure"), command_id=command_id
        )
    assert _command_counts(tenant.database.admin_dsn, command_id) == (0, 0, 0)
    _remove_outbox_failure(tenant.database.admin_dsn)
    result = _create(tenant, command_id, title="Rollback process failure")
    assert result.command_id == command_id
    assert _command_counts(tenant.database.admin_dsn, command_id) == (1, 1, 1)


def test_generated_telemetry_context_reaches_process_outbox(
    process_tenant: _ProcessTenant,
) -> None:
    tenant = process_tenant
    command_id = uuid4()
    context = TelemetryContext(
        schema_id="ctower.telemetry-context/v1",
        trace_id="a" * 32,
        span_id="b" * 16,
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id="untrusted-tenant",
        actor_id="untrusted-actor",
        command_id="overwritten-command",
    )
    with CtowerClient(tenant.base_url, credential=tenant.credential, telemetry=context) as client:
        result = client.create_ticket(
            _ticket_request(tenant, title="Process telemetry"), command_id=command_id
        )
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT telemetry FROM outbox WHERE event_id = %s", (result.event_ids[0],)
        ).fetchone()
    assert row is not None
    stored = cast(dict[str, object], row[0])
    assert stored["tenant_id"] == str(tenant.tenant_id)
    assert stored["actor_id"] == str(tenant.operator_id)
    assert stored["command_id"] == str(command_id)
    assert stored["ticket_id"] == str(result.ticket.ticket_id)
    assert stored["trace_id"] == "a" * 32


def _bootstrap_request() -> BootstrapRequest:
    return BootstrapRequest(
        commander_name="Ctower Commander",
        commander_vault_ref="vault-ref:ctower/commander",
        operator_credential_ref="credential-ref:ctower/operator",
        operator_name="First Operator",
        operator_vault_ref="vault-ref:ctower/operator",
        tenant_name="Ctower",
        tenant_slug="ctower",
    )


def _ticket_request(tenant: _ProcessTenant, *, title: str) -> TicketCreateRequest:
    return TicketCreateRequest(
        initial_custodian_id=tenant.commander_id,
        priority=Priority.P1,
        source=SourceReference(kind="process", ref="generated-client"),
        title=title,
    )


def _custody_request(tenant: _ProcessTenant, *, reason: str) -> CustodyTransferRequest:
    return CustodyTransferRequest(
        expected_version=1,
        from_custodian_id=tenant.commander_id,
        protected_transfer=True,
        reason=reason,
        to_custodian_id=tenant.operator_id,
    )


def _client(tenant: _ProcessTenant) -> CtowerClient:
    return CtowerClient(tenant.base_url, credential=tenant.credential)


def _create(tenant: _ProcessTenant, command_id: UUID, *, title: str) -> TicketCommandResult:
    with _client(tenant) as client:
        return client.create_ticket(_ticket_request(tenant, title=title), command_id=command_id)


def _outcome(call: Callable[[], TicketCommandResult]) -> TicketCommandResult | Problem:
    try:
        return call()
    except CtowerProblemError as error:
        return cast(Problem, error.problem)


def _command_counts(dsn: str, command_id: UUID) -> tuple[int, int, int]:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM command_results WHERE client_command_id = %s),
                (SELECT count(*) FROM events WHERE client_command_id = %s),
                (SELECT count(*) FROM outbox AS o JOIN events AS e USING (event_id)
                    WHERE e.client_command_id = %s)
            """,
            (command_id, command_id, command_id),
        ).fetchone()
    if row is None:
        raise AssertionError("command counts disappeared")
    return cast(tuple[int, int, int], row)


def _install_command_delay(dsn: str) -> None:
    _execute(
        dsn,
        """
        CREATE FUNCTION delay_process_command() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_sleep(0.25);
            RETURN NEW;
        END
        $$;
        CREATE TRIGGER delay_process_command BEFORE INSERT ON command_results
            FOR EACH ROW EXECUTE FUNCTION delay_process_command();
        """,
    )


def _install_outbox_failure(dsn: str) -> None:
    _execute(
        dsn,
        """
        CREATE FUNCTION reject_process_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'injected process outbox failure';
        END
        $$;
        CREATE TRIGGER reject_process_outbox BEFORE INSERT ON outbox
            FOR EACH ROW EXECUTE FUNCTION reject_process_outbox();
        """,
    )


def _remove_outbox_failure(dsn: str) -> None:
    _execute(
        dsn,
        """
        DROP TRIGGER reject_process_outbox ON outbox;
        DROP FUNCTION reject_process_outbox();
        """,
    )


def _execute(dsn: str, statement: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(statement)
