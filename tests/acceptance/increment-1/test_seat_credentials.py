"""Issued, scoped, revocable project-seat credential acceptance."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime
from itertools import permutations
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.server import proof_policy
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.proof import Proof
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork
from ctower_kernel.workflow import Workflow, WorkflowGraph
from ctower_kernel.workflow.postgres import PostgresWorkflow, PostgresWorkflowPolicyPins

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]

HTTP_PENDING = 202
HTTP_REDIRECTION = 300
HTTP_FORBIDDEN = 403
HTTP_UNAUTHORIZED = 401
HTTP_UNPROCESSABLE = 422
_MISSING = object()


def test_initial_custody_requires_an_explicit_project_grant(tenant: TenantFixture) -> None:
    ungranted_commander = uuid4()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, 'commander', 'Ungranted Commander', false, %s)
            """,
            (ungranted_commander, tenant.tenant_id, datetime.now(UTC)),
        )
    with _client(tenant) as client:
        refused = cast(
            Response,
            client.post(
                "/v1/tickets",
                json={
                    "initial_custodian_id": str(ungranted_commander),
                    "priority": "P2",
                    "source": {"kind": "mission-control", "ref": "grant-required"},
                    "title": "No implicit project authority",
                },
                headers={
                    **_auth(tenant.operator_credential),
                    "Idempotency-Key": str(uuid4()),
                },
            ),
        )

    assert refused.status_code == HTTP_FORBIDDEN
    assert refused.json()["code"] == "project-grant-required"


def test_operator_issues_capture_scope_and_seat_self_places_project_custody(
    tenant: TenantFixture,
) -> None:
    credential = secrets.token_urlsafe(32)
    command_id = uuid4()
    with _client(tenant) as client:
        issued = _issue(
            client,
            tenant.operator_credential,
            command_id=command_id,
            credential=credential,
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("capture",),
        )
        replay = _issue(
            client,
            tenant.operator_credential,
            command_id=command_id,
            credential=credential,
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("capture",),
        )

        assert issued.status_code == HTTP_PENDING
        assert replay.content == issued.content
        receipt = issued.json()
        assert receipt["project_key"] == "manibo"
        assert receipt["seat_key"] == "manibo-commander"
        assert receipt["scopes"] == ["capture"]
        assert receipt["state"] == "active"
        assert "credential" not in receipt

        created = cast(
            Response,
            client.post(
                "/v1/tickets",
                json={
                    "priority": "P2",
                    "source": {"kind": "mission-control", "ref": "manibo-R115"},
                    "title": "Manibo seat-owned ticket",
                },
                headers={**_auth(credential), "Idempotency-Key": str(uuid4())},
            ),
        )
        transition = cast(
            Response,
            client.post(
                f"/v1/tickets/{created.json()['ticket']['ticket_id']}/priority",
                json={"expected_version": 1, "priority": "P1", "reason": "Scope probe"},
                headers={**_auth(credential), "Idempotency-Key": str(uuid4())},
            ),
        )

    assert created.status_code == HTTP_PENDING
    assert transition.status_code == HTTP_FORBIDDEN
    assert transition.json()["code"] == "credential-scope-denied"
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        ticket = connection.execute(
            "SELECT project_key, custodian_principal_id, version FROM tickets WHERE ticket_id = %s",
            (UUID(created.json()["ticket"]["ticket_id"]),),
        ).fetchone()
        facts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM seat_credential_issuances) AS issuances,
                (SELECT count(*) FROM events
                 WHERE kind = 'access.seat_credential_issued') AS issuance_events
            """
        ).fetchone()
    assert ticket == {
        "project_key": "manibo",
        "custodian_principal_id": UUID(receipt["principal_id"]),
        "version": 1,
    }
    assert facts == {"issuances": 1, "issuance_events": 1}


def test_issuance_is_operator_only_and_owner_is_not_a_grantable_scope(
    tenant: TenantFixture,
) -> None:
    with _client(tenant) as client:
        commander_attempt = _issue(
            client,
            tenant.commander_credential,
            command_id=uuid4(),
            credential=secrets.token_urlsafe(32),
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("capture",),
        )
        owner_scope = _issue(
            client,
            tenant.operator_credential,
            command_id=uuid4(),
            credential=secrets.token_urlsafe(32),
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("owner",),
        )

    assert commander_attempt.status_code == HTTP_FORBIDDEN
    assert commander_attempt.json()["code"] == "credential-issuance-refused"
    assert owner_scope.status_code == HTTP_UNPROCESSABLE
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute("SELECT count(*) FROM seat_credential_issuances").fetchone()
    assert count == (0,)


def test_revocation_appends_and_the_next_call_refuses_by_name(
    tenant: TenantFixture,
) -> None:
    credential = secrets.token_urlsafe(32)
    with _client(tenant) as client:
        issued = _issue(
            client,
            tenant.operator_credential,
            command_id=uuid4(),
            credential=credential,
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("capture", "transition", "evidence"),
        )
        credential_id = UUID(issued.json()["credential_id"])
        revoked = cast(
            Response,
            client.post(
                f"/v1/admin/seat-credentials/{credential_id}/revocation",
                json={"reason": "Seat rotation"},
                headers={
                    **_auth(tenant.operator_credential),
                    "Idempotency-Key": str(uuid4()),
                },
            ),
        )
        next_call = cast(
            Response,
            client.get(f"/v1/tickets/{uuid4()}", headers=_auth(credential)),
        )

    assert issued.status_code == HTTP_PENDING
    assert revoked.status_code == HTTP_PENDING
    assert revoked.json()["state"] == "revoked"
    assert next_call.status_code == HTTP_UNAUTHORIZED
    assert next_call.json()["code"] == "credential-revoked"
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        events = connection.execute(
            """
            SELECT kind, payload FROM events
            WHERE aggregate_id = %s ORDER BY sequence
            """,
            (credential_id,),
        ).fetchall()
        revocations = connection.execute(
            """
            SELECT count(*) AS revocations FROM seat_credential_revocations
            WHERE credential_id = %s
            """,
            (credential_id,),
        ).fetchone()
    assert [row["kind"] for row in events] == [
        "access.seat_credential_issued",
        "access.seat_credential_revoked",
    ]
    serialized = json.dumps([row["payload"] for row in events], sort_keys=True)
    assert credential not in serialized
    assert hashlib.sha256(credential.encode()).hexdigest() not in serialized
    assert revocations == {"revocations": 1}


def test_manibo_seat_cannot_mutate_ctower_ticket_by_name(tenant: TenantFixture) -> None:
    credential = secrets.token_urlsafe(32)
    with _client(tenant) as client:
        ctower = cast(
            Response,
            client.post(
                "/v1/tickets",
                json={
                    "initial_custodian_id": str(tenant.commander_id),
                    "priority": "P2",
                    "source": {"kind": "mission-control", "ref": "ctower-R192"},
                    "title": "Ctower-owned ticket",
                },
                headers={
                    **_auth(tenant.operator_credential),
                    "Idempotency-Key": str(uuid4()),
                },
            ),
        )
        issued = _issue(
            client,
            tenant.operator_credential,
            command_id=uuid4(),
            credential=credential,
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("transition",),
        )
        ticket_id = UUID(ctower.json()["ticket"]["ticket_id"])
        refused = cast(
            Response,
            client.post(
                f"/v1/tickets/{ticket_id}/priority",
                json={
                    "expected_version": 1,
                    "priority": "P1",
                    "reason": "Foreign mutation probe",
                },
                headers={**_auth(credential), "Idempotency-Key": str(uuid4())},
            ),
        )

    assert ctower.status_code == HTTP_PENDING
    assert issued.status_code == HTTP_PENDING
    assert refused.status_code == HTTP_FORBIDDEN
    assert refused.json()["code"] == "project-scope-denied"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        fingerprint = connection.execute(
            """
            SELECT ticket.project_key, ticket.version,
                (SELECT count(*) FROM events
                 WHERE aggregate_id = ticket.ticket_id AND kind = 'work.changed')
            FROM tickets AS ticket WHERE ticket.ticket_id = %s
            """,
            (ticket_id,),
        ).fetchone()
    assert fingerprint == ("ctower", 1, 0)


def test_openapi_discovered_ticket_mutations_share_one_project_refusal_seam(
    tenant: TenantFixture,
) -> None:
    credential = secrets.token_urlsafe(32)
    document = _openapi()
    operations = _ticket_mutations(document)
    with _full_client(tenant) as client:
        ctower = cast(
            Response,
            client.post(
                "/v1/tickets",
                json={
                    "initial_custodian_id": str(tenant.commander_id),
                    "priority": "P2",
                    "source": {"kind": "mission-control", "ref": "ctower-route-inventory"},
                    "title": "OpenAPI mutation inventory target",
                },
                headers={
                    **_auth(tenant.operator_credential),
                    "Idempotency-Key": str(uuid4()),
                },
            ),
        )
        ticket_id = UUID(ctower.json()["ticket"]["ticket_id"])
        issued = _issue(
            client,
            tenant.operator_credential,
            command_id=uuid4(),
            credential=credential,
            project_key="manibo",
            seat_key="manibo-route-prober",
            scopes=("capture", "transition", "evidence"),
        )
        before = _ticket_residue(tenant, ticket_id)
        results = {
            operation_id: cast(
                Response,
                client.post(
                    _mutation_path(path, ticket_id),
                    json=_schema_value(document, schema),
                    headers={**_auth(credential), "Idempotency-Key": str(uuid4())},
                ),
            )
            for operation_id, path, schema in operations
        }
        after_foreign = _ticket_residue(tenant, ticket_id)
        controls = {
            operation_id: cast(
                Response,
                client.post(
                    _mutation_path(path, ticket_id),
                    json=_schema_value(document, schema),
                    headers={
                        **_auth(tenant.commander_credential),
                        "Idempotency-Key": str(uuid4()),
                    },
                ),
            )
            for operation_id, path, schema in operations
        }

    assert ctower.status_code == HTTP_PENDING
    assert issued.status_code == HTTP_PENDING
    assert results
    assert {
        operation_id: (response.status_code, response.json().get("code"))
        for operation_id, response in results.items()
    } == dict.fromkeys(results, (HTTP_FORBIDDEN, "project-scope-denied"))
    assert after_foreign == before
    assert all(
        response.json().get("code") != "project-scope-denied" for response in controls.values()
    )
    assert any(response.status_code < HTTP_REDIRECTION for response in controls.values())


def test_all_three_project_pairs_refuse_both_directions(tenant: TenantFixture) -> None:
    projects = ("ctower", "manibo", "bhloop")
    credentials = {project: secrets.token_urlsafe(32) for project in projects}
    tickets: dict[str, UUID] = {}
    with _client(tenant) as client:
        principals: dict[str, UUID] = {}
        for project in projects:
            issued = _issue(
                client,
                tenant.operator_credential,
                command_id=uuid4(),
                credential=credentials[project],
                project_key=project,
                seat_key=("ctower-commander" if project == "ctower" else f"{project}-pair-prober"),
                scopes=("capture", "transition", "evidence"),
            )
            assert issued.status_code == HTTP_PENDING
            principals[project] = UUID(issued.json()["principal_id"])
        for project in projects:
            created = cast(
                Response,
                client.post(
                    "/v1/tickets",
                    json={
                        "initial_custodian_id": str(principals[project]),
                        "priority": "P2",
                        "source": {"kind": "project-pair", "ref": project},
                        "title": f"{project} project pair target",
                    },
                    headers={
                        **_auth(tenant.operator_credential),
                        "Idempotency-Key": str(uuid4()),
                    },
                ),
            )
            assert created.status_code == HTTP_PENDING
            tickets[project] = UUID(created.json()["ticket"]["ticket_id"])

        refusals = {
            (source, target): cast(
                Response,
                client.post(
                    f"/v1/tickets/{tickets[target]}/priority",
                    json={
                        "expected_version": 1,
                        "priority": "P1",
                        "reason": f"{source} to {target} isolation probe",
                    },
                    headers={
                        **_auth(credentials[source]),
                        "Idempotency-Key": str(uuid4()),
                    },
                ),
            )
            for source, target in permutations(projects, 2)
        }

    assert {
        pair: (response.status_code, response.json().get("code"))
        for pair, response in refusals.items()
    } == dict.fromkeys(refusals, (HTTP_FORBIDDEN, "project-scope-denied"))
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        residue = connection.execute(
            """
            SELECT project_key, version,
                (SELECT count(*) FROM events AS event
                 WHERE event.aggregate_id = ticket.ticket_id AND event.kind = 'work.changed')
            FROM tickets AS ticket WHERE ticket_id = ANY(%s) ORDER BY project_key
            """,
            (list(tickets.values()),),
        ).fetchall()
    assert residue == [("bhloop", 1, 0), ("ctower", 1, 0), ("manibo", 1, 0)]


def _client(tenant: TenantFixture) -> TestClient:
    record = PostgresRecord(tenant.database.runtime_dsn)
    return TestClient(
        create_app(
            record,
            work=Work(record, writer=PostgresWork(tenant.database.runtime_dsn)),
        ),
        client=("127.0.0.1", 51000),
    )


def _full_client(tenant: TenantFixture) -> TestClient:
    runtime_dsn = tenant.database.runtime_dsn
    record = PostgresRecord(runtime_dsn)
    proof_store = PostgresProof(
        runtime_dsn,
        policies=(proof_policy(),),
        policy_pins=PostgresWorkflowPolicyPins(),
    )
    graph = WorkflowGraph.from_mapping(
        json.loads(
            (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    return TestClient(
        create_app(
            record,
            work=Work(record, writer=PostgresWork(runtime_dsn)),
            proof=Proof(writer=proof_store),
            workflow=Workflow(
                (graph,),
                writer=PostgresWorkflow(
                    runtime_dsn,
                    proof_gate=proof_store,
                    readiness_gate=PostgresWork(runtime_dsn),
                ),
                policy_digests={
                    "ctower.trust-spine-four-stage.execution@1": _file_digest(
                        "packs/policies/execution/trust-spine-four-stage-v1.yaml"
                    ),
                    "ctower.trust-spine-four-stage.gates@1": _file_digest(
                        "packs/policies/gates/trust-spine-four-stage-v1.yaml"
                    ),
                    "ctower.trust-spine-four-stage.evidence@1": _file_digest(
                        "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
                    ),
                },
            ),
        ),
        client=("127.0.0.1", 51000),
    )


def _openapi() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8")),
    )


def _ticket_mutations(
    document: dict[str, object],
) -> tuple[tuple[str, str, dict[str, object]], ...]:
    paths = cast(dict[str, dict[str, dict[str, object]]], document["paths"])
    discovered: list[tuple[str, str, dict[str, object]]] = []
    for path, methods in paths.items():
        operation = methods.get("post")
        if (
            operation is None
            or not path.startswith("/v1/tickets/{ticket_id}/")
            or operation.get("x-ctower-mutation") is not True
        ):
            continue
        request_body = cast(dict[str, object], operation["requestBody"])
        content = cast(dict[str, dict[str, object]], request_body["content"])
        schema = cast(dict[str, object], content["application/json"]["schema"])
        discovered.append((cast(str, operation["operationId"]), path, schema))
    return tuple(sorted(discovered))


def _mutation_path(path: str, ticket_id: UUID) -> str:
    """Fill every path parameter, not only the ticket.

    A ticket mutation may be nested under a further identifier. Leaving that template
    literal in the URL would make the route refuse the malformed path instead of the
    foreign project, and the seam would look proven while never being probed.
    """

    return re.sub(r"\{[a-z_]+\}", str(uuid4()), path.replace("{ticket_id}", str(ticket_id)))


def _schema_value(
    document: dict[str, object],
    raw_schema: dict[str, object],
    *,
    field: str = "",
) -> object:
    schema = _resolved_schema(document, raw_schema)
    special = _special_schema_value(document, schema, field=field)
    if special is not _MISSING:
        return special
    return _typed_schema_value(document, schema, field=field)


def _special_schema_value(
    document: dict[str, object], schema: dict[str, object], *, field: str
) -> object:
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        values = cast(list[object], schema["enum"])
        if field == "priority" and "P1" in values:
            return "P1"
        return next(value for value in values if value is not None)
    if "oneOf" in schema:
        return _schema_value(
            document,
            cast(list[dict[str, object]], schema["oneOf"])[0],
            field=field,
        )
    return _MISSING


def _typed_schema_value(
    document: dict[str, object], schema: dict[str, object], *, field: str
) -> object:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if "null" in schema_type:
            return None
        schema_type = schema_type[0]
    if schema_type == "object":
        required = cast(list[str], schema.get("required", []))
        properties = cast(dict[str, dict[str, object]], schema["properties"])
        return {name: _schema_value(document, properties[name], field=name) for name in required}
    if schema_type == "array":
        count = max(1, int(cast(int, schema.get("minItems", 0))))
        item = cast(dict[str, object], schema["items"])
        return [_schema_value(document, item, field=field) for _ in range(count)]
    if schema_type == "integer":
        return int(cast(int, schema.get("minimum", 0)))
    if schema_type == "boolean":
        return False
    if schema_type == "string":
        return _schema_string(schema, field)
    raise AssertionError(f"unsupported OpenAPI schema for {field}: {schema}")


def _resolved_schema(document: dict[str, object], schema: dict[str, object]) -> dict[str, object]:
    reference = schema.get("$ref")
    if not isinstance(reference, str):
        return schema
    name = reference.rsplit("/", 1)[-1]
    components = cast(dict[str, dict[str, dict[str, object]]], document["components"])
    return components["schemas"][name]


def _schema_string(schema: dict[str, object], field: str) -> str:
    if schema.get("format") == "uuid":
        return str(uuid4())
    if schema.get("format") == "uri":
        return "https://probe.invalid/artifact"
    pattern = str(schema.get("pattern", ""))
    if "sha256:" in pattern:
        return "sha256:" + "a" * 64
    if "@[1-9]" in pattern:
        return "fixture@1"
    minimum = max(1, int(cast(int, schema.get("minLength", 1))))
    value = field.replace("_", "-") or "probe"
    return (value + "p" * minimum)[:minimum] if len(value) < minimum else value


def _ticket_residue(tenant: TenantFixture, ticket_id: UUID) -> tuple[object, ...]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT ticket.version,
              (SELECT count(*) FROM events WHERE aggregate_id = ticket.ticket_id
               AND kind = 'ticket.comment_added'),
              (SELECT count(*) FROM events WHERE aggregate_id = ticket.ticket_id
               AND kind = 'ticket.custody_transferred'),
              (SELECT count(*) FROM events WHERE aggregate_id = ticket.ticket_id
               AND kind = 'work.changed'),
              (SELECT count(*) FROM proof_bundles WHERE ticket_id = ticket.ticket_id),
              (SELECT count(*) FROM workflow_runs WHERE ticket_id = ticket.ticket_id),
              (SELECT count(*) FROM assignment_intervals WHERE ticket_id = ticket.ticket_id),
              (SELECT count(*) FROM ticket_relations
               WHERE source_ticket_id = ticket.ticket_id OR target_ticket_id = ticket.ticket_id)
            FROM tickets AS ticket WHERE ticket.ticket_id = %s
            """,
            (ticket_id,),
        ).fetchone()
    if row is None:
        raise AssertionError("project-isolation target disappeared")
    return tuple(row)


def _file_digest(relative: str) -> str:
    return "sha256:" + hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def _issue(
    client: TestClient,
    authority: str,
    *,
    command_id: UUID,
    credential: str,
    project_key: str,
    seat_key: str,
    scopes: tuple[str, ...],
) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/admin/seat-credentials",
            json={
                "credential_digest": (f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}"),
                "credential_ref": f"secret-ref:test/{project_key}/{seat_key}",
                "display_name": f"{project_key.title()} Commander",
                "project_key": project_key,
                "scopes": list(scopes),
                "seat_key": seat_key,
            },
            headers={**_auth(authority), "Idempotency-Key": str(command_id)},
        ),
    )


def _auth(credential: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credential}",
        **telemetry_headers(),
    }
