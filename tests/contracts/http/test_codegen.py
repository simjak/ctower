"""Deterministic generated Python client contract."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
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
from ruamel.yaml import YAML

from ctower_client import AuditPage
from tools.codegen.generator import CodegenError, check, write

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()
_EXPECTED_OPERATION_COUNT = 103


class _MutatedClient(Protocol):
    _http: httpx.Client

    def create_ticket(self, request: object, *, command_id: UUID) -> object: ...

    def get_ticket(self, ticket_id: UUID, **parameters: str | None) -> object: ...


@contextmanager
def _generated_package(fixture: Path) -> Iterator[ModuleType]:
    cached = {
        name: module
        for name, module in sys.modules.items()
        if name in {"ctower_client", "ctower_contracts"}
        or name.startswith(("ctower_client.", "ctower_contracts."))
    }
    for name in cached:
        del sys.modules[name]
    sys.path.insert(0, str(fixture / "generated/python"))
    try:
        yield importlib.import_module("ctower_client")
    finally:
        sys.path.pop(0)
        for name in tuple(sys.modules):
            if name in {"ctower_client", "ctower_contracts"} or name.startswith(
                ("ctower_client.", "ctower_contracts.")
            ):
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
        "generated/README.md",
        "generated/python/ctower_client/__init__.py",
        "generated/python/ctower_client/client.py",
        "generated/python/ctower_client/models.py",
        "generated/python/ctower_client/operations.py",
        "generated/python/ctower_contracts/__init__.py",
        "generated/python/ctower_contracts/__main__.py",
        "generated/python/ctower_contracts/catalog.py",
        "generated/python/ctower_contracts/schemas.json",
        "generated/typescript/ctower-client/package.json",
        "generated/typescript/ctower-client/src/client.ts",
        "generated/typescript/ctower-client/src/index.ts",
        "generated/typescript/ctower-client/src/models.ts",
        "generated/typescript/ctower-client/src/operations.ts",
        "generated/typescript/ctower-client/src/response-json.ts",
        "generated/typescript/ctower-client/src/validators.ts",
        "generated/typescript/ctower-client/tsconfig.json",
    }
    for entry in outputs:
        digest = hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == f"sha256:{digest}"
    inputs = cast(list[dict[str, str]], entries[0]["inputs"])
    input_paths = {entry["path"] for entry in inputs}
    assert {
        path.relative_to(ROOT).as_posix() for path in (ROOT / "contracts").rglob("*.schema.json")
    } <= input_paths
    assert {
        "tools/codegen/_absolute_uri_codegen.py",
        "tools/codegen/_free_form_json_codegen.py",
        "tools/codegen/_typescript_json_codegen.py",
        "tools/codegen/_typescript_validation_codegen.py",
    } <= input_paths


def test_generated_python_carries_do_not_edit_notice() -> None:
    paths = tuple(sorted((ROOT / "generated/python").glob("ctower_*/*.py")))

    assert {path.relative_to(ROOT / "generated/python").as_posix() for path in paths} == {
        "ctower_client/__init__.py",
        "ctower_client/client.py",
        "ctower_client/models.py",
        "ctower_client/operations.py",
        "ctower_contracts/__init__.py",
        "ctower_contracts/__main__.py",
        "ctower_contracts/catalog.py",
    }
    for path in paths:
        assert path.read_text(encoding="utf-8").startswith(
            '"""DO NOT EDIT: generated file; regenerate from declared inputs.'
        )
    resources = json.loads(
        (ROOT / "generated/python/ctower_contracts/schemas.json").read_text(encoding="utf-8")
    )
    assert resources["_notice"] == "DO NOT EDIT: generated file; regenerate from declared inputs."


def test_generated_typescript_has_exact_intake_models_operations_and_notice() -> None:
    root = ROOT / "generated/typescript/ctower-client"
    sources = tuple(sorted((root / "src").glob("*.ts")))

    assert {path.name for path in sources} == {
        "client.ts",
        "index.ts",
        "models.ts",
        "operations.ts",
        "response-json.ts",
        "validators.ts",
    }
    for path in sources:
        assert path.read_text(encoding="utf-8").startswith(
            "// DO NOT EDIT: generated file; regenerate from declared inputs."
        )
    client = (root / "src/client.ts").read_text(encoding="utf-8")
    models = (root / "src/models.ts").read_text(encoding="utf-8")
    operations = (root / "src/operations.ts").read_text(encoding="utf-8")
    for operation in ("submitIntake", "promoteIntakeEvent"):
        assert f"public async {operation}(" in client
        assert f'"{operation}"' in operations
    for model in ("IntakeSubmitRequest", "IntakePromotionRequest", "IntakeCommandResult"):
        assert f"export type {model} =" in models
    python_client = (ROOT / "generated/python/ctower_client/client.py").read_text(encoding="utf-8")
    assert "def submit_intake(" in python_client
    assert "def promote_intake_event(" in python_client


def test_generated_operation_registry_is_the_exact_authored_replay_allowlist() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    expected: dict[str, tuple[object, ...]] = {}
    for path, path_item in cast(dict[str, dict[str, object]], document["paths"]).items():
        for method, value in path_item.items():
            if method not in {"get", "post"}:
                continue
            operation = cast(dict[str, object], value)
            cli = operation["x-ctower-cli"]
            cli_names = (
                tuple(cli) if isinstance(cli, list) else (() if cli is None else (cast(str, cli),))
            )
            request = _boundary_name(operation.get("requestBody"))
            response = _success_boundary(operation)
            expected[cast(str, operation["operationId"])] = (
                method.upper(),
                path,
                request,
                response,
                cli_names,
                operation["x-ctower-mutation"],
                operation["x-ctower-spool"],
                operation.get("x-ctower-principal"),
                operation.get("x-ctower-refusal-only", False),
            )

    with _generated_package(ROOT):
        generated = importlib.import_module("ctower_client.operations")
        actual = {
            operation_id: (
                spec.method,
                spec.path,
                spec.request_model.__name__ if spec.request_model is not None else None,
                spec.response_model.__name__ if spec.response_model is not None else None,
                spec.cli_names,
                spec.mutation,
                spec.spool_policy.value,
                spec.principal,
                spec.refusal_only,
            )
            for operation_id, spec in generated.OPERATIONS.items()
        }

    assert len(actual) == _EXPECTED_OPERATION_COUNT
    assert actual == expected


def test_http_reference_operation_count_matches_the_authored_contract_inventory() -> None:
    reference = (ROOT / "docs/reference/http-api.md").read_text(encoding="utf-8")
    match = re.search(r"declares \*\*(\d+) operations\*\*", reference)

    assert match is not None
    assert int(match.group(1)) == _EXPECTED_OPERATION_COUNT


def test_estate_import_operations_are_documented_in_the_http_reference() -> None:
    reference = (ROOT / "docs/reference/http-api.md").read_text(encoding="utf-8")
    rows = (
        ("/v1/migrations/estate/inbox", "importEstateInbox", "migration ctower-inbox import"),
        ("/v1/migrations/estate/rulings", "importEstateRulings", "migration ctower-ruling import"),
        (
            "/v1/migrations/estate/knowledge",
            "importEstateKnowledge",
            "migration ctower-knowledge import",
        ),
        (
            "/v1/migrations/estate/company-records",
            "importEstateCompanyRecords",
            "migration ctower-company-record import",
        ),
    )
    for path, operation, cli in rows:
        row = (
            f"| `POST` | `{path}` | `{operation}` | `{cli}` | mutation | forbidden | "
            "`201`, `202`, `401`, `403`, `409`, `422` |"
        )
        assert row in reference, f"missing HTTP reference row: {row}"


def test_generated_runtime_contracts_validate_offline_and_are_defensive() -> None:
    payload = YAML(typ="safe", pure=True).load(
        (ROOT / "company/company.bundle.yaml").read_text(encoding="utf-8")
    )
    with _generated_package(ROOT):
        generated = importlib.import_module("ctower_contracts")
        schema = generated.schema_for("ctower.company-bundle/v1")
        assert schema is not None
        schema["title"] = "mutated caller copy"
        assert generated.schema_for("ctower.company-bundle/v1")["title"] != "mutated caller copy"
        generated.validator_for("ctower.company-bundle/v1").validate(payload)
        assert generated.schema_for("ctower.unknown/v1") is None
        resources = json.loads(
            (ROOT / "generated/python/ctower_contracts/schemas.json").read_text(encoding="utf-8")
        )
        assert generated.verify_all() == len(resources["resources"])


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        ("https://attacker.invalid/schema.json", "network schema reference"),
        ("../../../escaped.schema.json", "escapes contracts"),
    ],
)
def test_codegen_rejects_nonlocal_schema_references(reference: str, message: str) -> None:
    with tempfile.TemporaryDirectory() as name:
        fixture = Path(name)
        shutil.copytree(
            ROOT,
            fixture,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"),
        )
        path = fixture / "contracts/company/company-bundle.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema["properties"]["resources"]["items"]["properties"]["component"]["$ref"] = reference
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

        with pytest.raises(CodegenError, match=message):
            write(fixture)


def test_codegen_rejects_runtime_schema_name_collisions() -> None:
    with tempfile.TemporaryDirectory() as name:
        fixture = Path(name)
        shutil.copytree(
            ROOT,
            fixture,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"),
        )
        original = fixture / "contracts/components/goal.schema.json"
        duplicate = fixture / "contracts/components/goal-collision.schema.json"
        schema = json.loads(original.read_text(encoding="utf-8"))
        schema["$id"] = "https://ctower.local/contracts/components/goal-collision.schema.json"
        duplicate.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

        with pytest.raises(CodegenError, match="runtime schema name collision"):
            write(fixture)


def _boundary_name(value: object) -> str | None:
    if value is None:
        return None
    body = cast(dict[str, object], value)
    content = cast(dict[str, object], body["content"])
    media = cast(dict[str, object], content["application/json"])
    schema = cast(dict[str, str], media["schema"])
    return schema["$ref"].removeprefix("#/components/schemas/")


def _success_boundary(operation: dict[str, object]) -> str | None:
    if operation.get("x-ctower-generated-client", True) is False:
        return None
    responses = cast(dict[str, dict[str, object]], operation["responses"])
    response = next(
        (value for status, value in sorted(responses.items()) if status.startswith("2")),
        None,
    )
    if response is None:
        assert operation.get("x-ctower-refusal-only") is True
        return None
    content = cast(dict[str, object], response.get("content", {}))
    media_value = content.get("application/json")
    if media_value is None:
        return None
    media = cast(dict[str, object], media_value)
    schema = cast(dict[str, str], media["schema"])
    return schema["$ref"].removeprefix("#/components/schemas/")


def test_generated_audit_variants_reject_unknown_and_mismatched_payloads() -> None:
    ticket_id = uuid4()
    ticket_event = _audit_event(
        "ticket.created",
        {
            "custodian_id": str(uuid4()),
            "priority": "P1",
            "project_key": "ctower",
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


def test_generated_client_exposes_only_explicit_i1_7b_methods_and_refusals() -> None:
    client = (ROOT / "generated/python/ctower_client/client.py").read_text(encoding="utf-8")

    for method in (
        "create_ctower_project_import_run",
        "bind_ctower_project_export_equality",
        "bind_ctower_project_alias_plan",
        "apply_ctower_project_import_batch",
        "finalize_ctower_project_import_run",
        "get_ctower_project_import_run",
        "append_ctower_project_import_correction",
        "report_ctower_project_fence_observation",
        "prepare_ctower_project_cutover",
        "commit_ctower_project_development_epoch",
    ):
        assert f"def {method}(" in client
    assert "dispatch_operation" not in client
    assert "def request(" not in client
    assert ") -> NoReturn:" in client


def test_generated_import_union_rejects_unknown_drift_and_cross_project() -> None:
    with _generated_package(ROOT) as generated:
        identity = {
            "namespace": "mission-control:request",
            "immutable_source_id": "R325",
            "source_version_or_digest": "line:1",
            "operation_kind": "ticket_seed",
            "planned_target_ref": "new_ticket",
            "command_id": uuid4(),
        }
        source = {
            "namespace": "mission-control:request",
            "immutable_source_id": "R325",
            "source_version": "line:1",
            "source_digest": "sha256:" + ("0" * 64),
        }
        payload = {
            "operation": "ticket_seed",
            "identity": identity,
            "project_key": "ctower",
            "priority": "P2",
            "title": "Synthetic import",
            "source": source,
            "initial_commander_custodian_id": uuid4(),
        }
        generated.CtowerProjectTicketSeedOperation.model_validate(payload)
        for invalid in (
            {**payload, "proof": {"verdict": "passed"}},
            {**payload, "project_key": "other"},
            {**payload, "operation": "workflow_transition"},
        ):
            with pytest.raises(ValidationError):
                generated.CtowerProjectTicketSeedOperation.model_validate(invalid)


def test_refusal_only_generated_method_raises_typed_i1_7c_problem() -> None:
    with _generated_package(ROOT) as generated:
        client = generated.CtowerClient("http://contract.invalid", credential="opaque")
        request = generated.CtowerProjectEpochRefusalRequest(
            cutover_id=uuid4(),
            run_id=uuid4(),
            reconciliation_digest="sha256:" + ("0" * 64),
            fence_registry_digest="sha256:" + ("1" * 64),
        )

        def handler(_http_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                409,
                headers={"content-type": "application/problem+json"},
                json={
                    "code": "i1-7c-required",
                    "detail": "Live epoch authority is not active",
                    "status": 409,
                    "title": "I1.7C required",
                    "type": "https://ctower.dev/problems/i1-7c-required",
                },
            )

        client._http = httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://contract.invalid"
        )
        with pytest.raises(generated.CtowerProblemError) as raised:
            client.prepare_ctower_project_cutover(request, command_id=uuid4())
        assert raised.value.problem.code == "i1-7c-required"
        client.close()


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
        project_key="ctower",
        source={"kind": "test", "ref": "test:contract"},
        title="ticket",
    )
    with pytest.raises(generated.CtowerProblemError) as raised:
        client.create_ticket(request, command_id=uuid4())
    assert type(raised.value.problem).__name__ == "TicketResource"
    with pytest.raises(ValidationError):
        client.get_ticket(uuid4(), project_key="ctower", filter="x")
    client.get_ticket(uuid4(), project_key="ctower")
    assert captured_query[0] == b"project_key=ctower"
    client.get_ticket(uuid4(), project_key="ctower", filter="open")
    assert captured_query[0] == b"project_key=ctower&filter=open"


def _authored_problem() -> dict[str, object]:
    return {
        "code": "unauthorized",
        "detail": "authored failure",
        "status": 401,
        "title": "Unauthorized",
        "type": "https://ctower.dev/problems/unauthorized",
    }
