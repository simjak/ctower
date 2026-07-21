"""Deterministic generated Python client contract."""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError

from tools.codegen.generator import check, write

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()


class _MutatedClient(Protocol):
    _http: httpx.Client

    def create_ticket(self, request: object, *, command_id: UUID) -> object: ...

    def get_ticket(self, ticket_id: UUID, **parameters: str | None) -> object: ...


@contextmanager
def _generated_package(fixture: Path) -> Iterator[ModuleType]:
    cached = {
        name: module
        for name, module in sys.modules.items()
        if name == "ctower_client" or name.startswith("ctower_client.")
    }
    for name in cached:
        del sys.modules[name]
    sys.path.insert(0, str(fixture / "generated/python"))
    try:
        yield importlib.import_module("ctower_client")
    finally:
        sys.path.pop(0)
        for name in tuple(sys.modules):
            if name == "ctower_client" or name.startswith("ctower_client."):
                del sys.modules[name]
        sys.modules.update(cached)


def test_generated_client_is_owned_and_byte_stable() -> None:
    check(ROOT)
    manifest = json.loads((ROOT / "generated/.generated-manifest.json").read_text(encoding="utf-8"))
    artifacts = cast(list[dict[str, object]], manifest["artifacts"])
    entries = [item for item in artifacts if item["id"] == "http-python-client"]

    assert len(entries) == 1
    outputs = cast(list[dict[str, str]], entries[0]["outputs"])
    assert {entry["path"] for entry in outputs} == {
        "generated/python/ctower_client/__init__.py",
        "generated/python/ctower_client/client.py",
        "generated/python/ctower_client/models.py",
    }
    for entry in outputs:
        digest = hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == f"sha256:{digest}"


def test_generated_python_carries_do_not_edit_notice() -> None:
    paths = tuple(sorted((ROOT / "generated/python/ctower_client").glob("*.py")))

    assert {path.name for path in paths} == {"__init__.py", "client.py", "models.py"}
    for path in paths:
        assert path.read_text(encoding="utf-8").startswith(
            '"""DO NOT EDIT: generated file; regenerate from declared inputs.'
        )


def test_generated_audit_variants_reject_unknown_and_mismatched_payloads() -> None:
    from ctower_client import AuditPage

    ticket_id = uuid4()
    ticket_event = _audit_event(
        "ticket.created",
        {
            "custodian_id": str(uuid4()),
            "priority": "P1",
            "source_kind": "test",
            "source_ref": "test:audit",
            "title": "Strict audit payload",
        },
    )
    valid = AuditPage.model_validate_json(
        json.dumps({"events": [ticket_event], "next_cursor": None, "ticket_id": str(ticket_id)})
    )
    assert valid.events[0].kind == "ticket.created"

    unknown = json.loads(json.dumps(ticket_event))
    unknown["payload"]["unexpected"] = True
    with pytest.raises(ValidationError):
        AuditPage.model_validate_json(
            json.dumps({"events": [unknown], "next_cursor": None, "ticket_id": str(ticket_id)})
        )

    mismatch = json.loads(json.dumps(ticket_event))
    mismatch["kind"] = "ticket.custody_transferred"
    with pytest.raises(ValidationError):
        AuditPage.model_validate_json(
            json.dumps({"events": [mismatch], "next_cursor": None, "ticket_id": str(ticket_id)})
        )

    work = _audit_event(
        "work.changed",
        {
            "data": {"episode_number": 1, "reason": "Ready"},
            "operation": "priority_changed",
            "ticket_id": str(ticket_id),
            "work_version": 2,
        },
    )
    with pytest.raises(ValidationError):
        AuditPage.model_validate_json(
            json.dumps({"events": [work], "next_cursor": None, "ticket_id": str(ticket_id)})
        )


def _audit_event(kind: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "actor_principal_id": str(uuid4()),
        "command_id": str(uuid4()),
        "event_hash": "sha256:" + "0" * 64,
        "event_id": str(uuid4()),
        "kind": kind,
        "occurred_at": "2026-07-21T12:00:00Z",
        "payload": payload,
        "record_position": 1,
        "sequence": 1,
        "stream_id": f"ticket:{uuid4()}",
    }


def test_generated_client_exposes_proof_and_workflow_commands() -> None:
    client = (ROOT / "generated/python/ctower_client/client.py").read_text(encoding="utf-8")

    assert "def freeze_proof_criteria(" in client
    assert "def record_proof_evidence(" in client
    assert "def record_proof_verdict(" in client
    assert "def transition_workflow(" in client
    assert "def resolve_close_workflow(" in client


def test_contract_semantics_drive_generated_model_constraints_and_client_paths() -> None:
    with tempfile.TemporaryDirectory() as name:
        fixture = Path(name)
        shutil.copytree(
            ROOT,
            fixture,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"),
        )
        contract_path = fixture / "contracts/http/openapi.yaml"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        schemas = contract["components"]["schemas"]
        schemas["TicketCreateRequest"]["properties"]["title"]["maxLength"] = 199
        schemas["TicketCommandResult"]["properties"]["event_ids"]["minItems"] = 2
        contract["paths"]["/v2/tickets"] = contract["paths"].pop("/v1/tickets")
        contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")

        write(fixture)
        models = (fixture / "generated/python/ctower_client/models.py").read_text(encoding="utf-8")
        client = (fixture / "generated/python/ctower_client/client.py").read_text(encoding="utf-8")

    assert "Field(min_length=1, max_length=199)" in models
    assert "Field(min_length=2)" in models
    assert '"/v2/tickets"' in client


def test_parameter_and_failure_contracts_drive_executable_client_code() -> None:
    with tempfile.TemporaryDirectory() as name:
        fixture = Path(name)
        shutil.copytree(
            ROOT,
            fixture,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"),
        )
        _mutate_executable_contract(fixture)
        write(fixture)
        client = (fixture / "generated/python/ctower_client/client.py").read_text(encoding="utf-8")
        with _generated_package(fixture) as generated:
            _assert_mutated_runtime(generated)

    assert "Annotated[str, Field(min_length=4, max_length=8)]" in client
    assert "filter: Annotated[str, Field(min_length=2, max_length=12)] | None = None" in client
    assert "params=" in client
    assert "401: TicketResource" in client


def _mutate_executable_contract(fixture: Path) -> None:
    contract_path = fixture / "contracts/http/openapi.yaml"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    parameters = contract["components"]["parameters"]
    parameters["BootstrapCapability"]["schema"].update({"minLength": 4, "maxLength": 8})
    contract["components"]["schemas"]["BootstrapReceipt"]["properties"]["event_ids"]["maxItems"] = 1
    contract["components"]["schemas"]["TicketResource"] = contract["components"]["schemas"][
        "Problem"
    ]
    parameters["TicketFilter"] = {
        "name": "filter",
        "in": "query",
        "required": False,
        "schema": {"type": "string", "minLength": 2, "maxLength": 12},
    }
    contract["paths"]["/v1/tickets/{ticket_id}"]["get"]["parameters"].append(
        {"$ref": "#/components/parameters/TicketFilter"}
    )
    contract["paths"]["/v1/tickets"]["post"]["responses"]["401"] = {
        "description": "Authored typed failure",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/TicketResource"}}
        },
    }
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def _assert_mutated_runtime(generated: ModuleType) -> None:
    client = generated.CtowerClient("http://contract.invalid")
    bootstrap = generated.BootstrapRequest(
        commander_name="commander",
        commander_vault_ref="vault-ref:commander",
        operator_credential_ref="credential-ref:operator",
        operator_name="operator",
        operator_vault_ref="vault-ref:operator",
        tenant_name="tenant",
        tenant_slug="tenant",
    )
    with pytest.raises(ValidationError):
        client.bootstrap_first_tenant(bootstrap, command_id=uuid4(), capability="too-long!")
    with pytest.raises(ValidationError):
        client.bootstrap_first_tenant(bootstrap, command_id=uuid4())
    with pytest.raises(ValidationError):
        generated.BootstrapReceipt(
            command_id=uuid4(),
            commander_id=uuid4(),
            durability_state=generated.DurabilityState.DURABILITY_PENDING,
            event_ids=(uuid4(), uuid4()),
            operator_id=uuid4(),
            receipt_digest="sha256:" + "0" * 64,
            tenant_id=uuid4(),
        )
    _assert_mutated_http(generated, client)
    client.close()


def _assert_mutated_http(generated: ModuleType, client: _MutatedClient) -> None:
    captured_query = [b""]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            captured_query[0] = request.url.query
            return httpx.Response(200, json=_authored_problem())
        return httpx.Response(
            401,
            headers={"content-type": "application/problem+json"},
            json=_authored_problem(),
        )

    client._http = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://contract.invalid"
    )
    request = generated.TicketCreateRequest(
        initial_custodian_id=uuid4(),
        priority=generated.Priority.P1,
        source={"kind": "test", "ref": "test:contract"},
        title="ticket",
    )
    with pytest.raises(generated.CtowerProblemError) as raised:
        client.create_ticket(request, command_id=uuid4())
    assert type(raised.value.problem).__name__ == "TicketResource"
    with pytest.raises(ValidationError):
        client.get_ticket(uuid4(), filter="x")
    client.get_ticket(uuid4())
    assert captured_query[0] == b""
    client.get_ticket(uuid4(), filter="open")
    assert captured_query[0] == b"filter=open"


def _authored_problem() -> dict[str, object]:
    return {
        "code": "unauthorized",
        "detail": "authored failure",
        "status": 401,
        "title": "Unauthorized",
        "type": "https://ctower.dev/problems/unauthorized",
    }
