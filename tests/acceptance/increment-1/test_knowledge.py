"""Real PostgreSQL, API, generated-client, and CLI acceptance for knowledge documents."""

from __future__ import annotations

import io
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from support.acceptance import accept_pending_commands
from support.server import running_api
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture, provision_credential

from ctower_api.interface import create_app
from ctower_kernel.knowledge import (
    Knowledge,
    PostgresKnowledge,
    StaticFileKnowledgeSource,
    bundled_static_root,
)
from ctower_kernel.record.postgres import PostgresRecord
from ctowerctl import main

__all__: tuple[str, ...] = ()

EXIT_SUCCESS = 0
EXIT_PERMANENT = 69
EXIT_TEMPORARY = 75
HTTP_OK = 200
HTTP_CREATED = 201


class _MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


@pytest.fixture
def protected_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _MemoryBackend()
    monkeypatch.setattr("ctowerctl.spool._keyring._secure_backend", lambda: backend)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "initial-state"))


def test_knowledge_cli_roundtrip_preserves_org_and_project_scope(
    tenant: TenantFixture,
    protected_state: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A1/A2/V1/V2: mounted source plus two isolated projects round-trip through CLI."""

    del protected_state
    entries = _exercise_roundtrip(tenant, monkeypatch, tmp_path)
    _assert_roundtrip(tenant, entries)
    _print_transcript(**entries)


def test_knowledge_http_routes_execute_in_process(tenant: TenantFixture) -> None:
    """Credit the strict HTTP and SQL paths while retaining real PostgreSQL authority."""

    record = PostgresRecord(tenant.database.runtime_dsn)
    knowledge = Knowledge(
        PostgresKnowledge(
            tenant.database.runtime_dsn,
            source=StaticFileKnowledgeSource(bundled_static_root()),
        )
    )
    with TestClient(create_app(record, knowledge=knowledge)) as client:
        responses = _exercise_http_mutations(client, tenant)
        document_id = cast(str, responses["accepted"].json()["document_id"])
        responses.update(_exercise_http_reads(client, tenant, document_id))
    _assert_http_responses(responses)


def _exercise_http_mutations(
    client: TestClient, tenant: TenantFixture
) -> dict[str, httpx.Response]:
    command_id = uuid4()
    operator_headers = _http_headers(tenant.operator_credential, command_id=command_id)
    payload = {
        "body": None,
        "project_key": None,
        "scope": "org",
        "source_ref": "ctower-knowledge",
        "title": None,
    }
    responses = {
        "unauthenticated": client.get("/v1/knowledge/documents", params={"scope": "org"}),
        "malformed": client.post(
            "/v1/knowledge/documents",
            headers=_http_headers(tenant.operator_credential, command_id=uuid4()),
            json={**payload, "body": "Direct body", "title": "Ambiguous"},
        ),
        "denied": client.post(
            "/v1/knowledge/documents",
            headers=_http_headers(tenant.commander_credential, command_id=uuid4()),
            json={**payload, "body": "Denied body", "source_ref": None, "title": "Denied"},
        ),
        "pending": client.post("/v1/knowledge/documents", headers=operator_headers, json=payload),
    }
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    responses["accepted"] = client.post(
        "/v1/knowledge/documents", headers=operator_headers, json=payload
    )
    assert responses["accepted"].status_code == HTTP_CREATED, responses["accepted"].text
    return responses


def _exercise_http_reads(
    client: TestClient, tenant: TenantFixture, document_id: str
) -> dict[str, httpx.Response]:
    headers = _http_headers(tenant.commander_credential)
    return {
        "listing": client.get("/v1/knowledge/documents", headers=headers, params={"scope": "org"}),
        "fetched": client.get(
            f"/v1/knowledge/documents/{document_id}",
            headers=headers,
            params={"scope": "org"},
        ),
        "invalid_id": client.get(
            "/v1/knowledge/documents/not-a-uuid",
            headers=headers,
            params={"scope": "org"},
        ),
        "unavailable": client.get(
            f"/v1/knowledge/documents/{uuid4()}",
            headers=headers,
            params={"scope": "org"},
        ),
        "invalid_scope": client.get(
            "/v1/knowledge/documents", headers=headers, params={"scope": "team"}
        ),
        "invalid_project": client.get(
            "/v1/knowledge/documents", headers=headers, params={"scope": "project"}
        ),
    }


def _assert_http_responses(responses: dict[str, httpx.Response]) -> None:
    assert (
        responses["unauthenticated"].status_code,
        responses["unauthenticated"].json()["code"],
    ) == (
        401,
        "unauthorized",
    )
    assert (responses["malformed"].status_code, responses["malformed"].json()["code"]) == (
        422,
        "validation-error",
    )
    assert (responses["denied"].status_code, responses["denied"].json()["code"]) == (
        403,
        "auth-role-denied",
    )
    assert (
        responses["pending"].status_code,
        responses["pending"].json()["durability_state"],
    ) == (
        202,
        "durability_pending",
    )
    assert (
        responses["accepted"].status_code,
        responses["accepted"].json()["durability_state"],
    ) == (
        HTTP_CREATED,
        "accepted",
    )
    assert responses["listing"].status_code == HTTP_OK
    assert responses["listing"].json()["documents"] == [responses["fetched"].json()]
    assert responses["fetched"].status_code == HTTP_OK
    assert responses["fetched"].json()["source_ref"] == "ctower-knowledge"
    assert (
        responses["invalid_id"].status_code,
        responses["invalid_id"].json()["code"],
    ) == (422, "validation-error")
    assert (
        responses["unavailable"].status_code,
        responses["unavailable"].json()["code"],
    ) == (
        404,
        "tenant-scope-denied",
    )
    assert (
        responses["invalid_scope"].status_code,
        responses["invalid_scope"].json()["code"],
    ) == (
        422,
        "knowledge-invalid-scope",
    )
    assert (
        responses["invalid_project"].status_code,
        responses["invalid_project"].json()["code"],
    ) == (
        422,
        "knowledge-invalid-project",
    )


def _http_headers(credential: str, *, command_id: UUID | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {credential}",
        **telemetry_headers(command_id),
    }
    if command_id is not None:
        headers["Idempotency-Key"] = str(command_id)
    return headers


def _exercise_roundtrip(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> dict[str, dict[str, object]]:
    manibo_credential = _provision_project_seat(tenant, "manibo", "manibo-commander")
    states = {
        "operator": tmp_path / "operator-state",
        "ctower": tmp_path / "ctower-state",
        "manibo": tmp_path / "manibo-state",
    }
    with running_api(tenant.database.runtime_dsn) as base_url:
        _assert_malformed_payloads_are_refused(base_url, tenant.operator_credential)
        entries = _register_documents(
            tenant, monkeypatch, tmp_path, states, base_url, manibo_credential
        )
        entries.update(
            _read_documents(tenant, monkeypatch, states, base_url, manibo_credential, entries)
        )
    return entries


def _register_documents(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    states: dict[str, Path],
    base_url: str,
    manibo_credential: str,
) -> dict[str, dict[str, object]]:
    org = _accepted_add(
        tenant,
        monkeypatch,
        state=states["operator"],
        base_url=base_url,
        credential=tenant.operator_credential,
        arguments=("--scope", "org", "--source-ref", "ctower-knowledge"),
    )
    ctower = _accepted_project_add(
        tenant,
        monkeypatch,
        tmp_path,
        states["ctower"],
        base_url,
        tenant.commander_credential,
        "ctower",
    )
    manibo = _accepted_project_add(
        tenant,
        monkeypatch,
        tmp_path,
        states["manibo"],
        base_url,
        manibo_credential,
        "manibo",
    )
    return {"org": org, "ctower": ctower, "manibo": manibo}


def _accepted_project_add(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    state: Path,
    base_url: str,
    credential: str,
    project_key: str,
) -> dict[str, object]:
    title = f"{project_key.title()} runbook"
    body_file = tmp_path / f"{project_key}.md"
    body_file.write_text(f"{project_key.title()} project-only runbook.", encoding="utf-8")
    return _accepted_add(
        tenant,
        monkeypatch,
        state=state,
        base_url=base_url,
        credential=credential,
        arguments=(
            "--scope",
            "project",
            "--project-key",
            project_key,
            "--title",
            title,
            "--body-file",
            str(body_file),
        ),
    )


def _read_documents(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    states: dict[str, Path],
    base_url: str,
    manibo_credential: str,
    registered: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    org_reads = _org_reads(tenant, monkeypatch, states["ctower"], base_url, registered["org"])
    ctower_reads = _project_reads(
        monkeypatch,
        states["ctower"],
        base_url,
        tenant.commander_credential,
        "ctower",
        registered["ctower"],
    )
    manibo_reads = _project_reads(
        monkeypatch,
        states["manibo"],
        base_url,
        manibo_credential,
        "manibo",
        registered["manibo"],
    )
    refusal = _refused_project_list(
        monkeypatch, states["ctower"], base_url, tenant.commander_credential, "manibo"
    )
    return {**org_reads, **ctower_reads, **manibo_reads, "refusal": refusal}


def _org_reads(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    base_url: str,
    registered: dict[str, object],
) -> dict[str, dict[str, object]]:
    listing = _query(
        monkeypatch,
        state,
        tenant.commander_credential,
        ["--base-url", base_url, "knowledge", "list", "--scope", "org"],
    )
    document = _get(
        monkeypatch,
        state,
        base_url,
        tenant.commander_credential,
        UUID(str(registered["document_id"])),
        "org",
    )
    return {"org_list": listing, "org_get": document}


def _project_reads(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    base_url: str,
    credential: str,
    project_key: str,
    registered: dict[str, object],
) -> dict[str, dict[str, object]]:
    listing = _project_list(monkeypatch, state, base_url, credential, project_key)
    document = _get(
        monkeypatch,
        state,
        base_url,
        credential,
        UUID(str(registered["document_id"])),
        "project",
        project_key=project_key,
    )
    return {f"{project_key}_list": listing, f"{project_key}_get": document}


def _assert_roundtrip(tenant: TenantFixture, entries: dict[str, dict[str, object]]) -> None:
    org, org_get = entries["org"], entries["org_get"]
    ctower, ctower_get = entries["ctower"], entries["ctower_get"]
    manibo_get, refusal = entries["manibo_get"], entries["refusal"]
    assert org["scope"] == "org" and org["source_ref"] == "ctower-knowledge"
    assert org["project_key"] is None
    assert org_get["source_ref"] == "ctower-knowledge"
    assert "immutable tenant- or project-scoped snapshots" in cast(str, org_get["body"])
    assert _titles(entries["ctower_list"]) == ["Ctower runbook"]
    assert _titles(entries["manibo_list"]) == ["Manibo runbook"]
    assert ctower_get["project_key"] == "ctower"
    assert manibo_get["project_key"] == "manibo"
    assert cast(list[object], entries["org_list"]["documents"])[0] == org_get
    assert refusal["code"] == "project-scope-denied"
    evidence = _database_evidence(tenant)
    assert evidence == {"events": 3, "facts": 3, "org": 1, "projections": 3, "projects": 2}
    _assert_authority_is_immutable(tenant, UUID(str(ctower["document_id"])))


def _accepted_add(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    *,
    state: Path,
    base_url: str,
    credential: str,
    arguments: tuple[str, ...],
) -> dict[str, object]:
    command_id = uuid4()
    command = [
        "--base-url",
        base_url,
        "knowledge",
        "add",
        "--command-id",
        str(command_id),
        *arguments,
    ]
    pending_status, pending = _run(monkeypatch, state, credential, command)
    assert pending_status == EXIT_TEMPORARY and pending["state"] == "queued"
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    accepted_status, accepted = _run(monkeypatch, state, credential, command)
    assert accepted_status == EXIT_SUCCESS and accepted["state"] == "accepted"
    return cast(dict[str, object], accepted["result"])


def _project_list(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    base_url: str,
    credential: str,
    project_key: str,
) -> dict[str, object]:
    return _query(
        monkeypatch,
        state,
        credential,
        [
            "--base-url",
            base_url,
            "knowledge",
            "list",
            "--scope",
            "project",
            "--project-key",
            project_key,
        ],
    )


def _get(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    base_url: str,
    credential: str,
    document_id: UUID,
    scope: str,
    *,
    project_key: str | None = None,
) -> dict[str, object]:
    arguments = [
        "--base-url",
        base_url,
        "knowledge",
        "get",
        str(document_id),
        "--scope",
        scope,
    ]
    if project_key is not None:
        arguments.extend(("--project-key", project_key))
    return _query(monkeypatch, state, credential, arguments)


def _query(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    credential: str,
    arguments: list[str],
) -> dict[str, object]:
    status, payload = _run(monkeypatch, state, credential, arguments)
    assert status == EXIT_SUCCESS
    return payload


def _run(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    credential: str,
    arguments: list[str],
) -> tuple[int, dict[str, object]]:
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    stdout, stderr = io.StringIO(), io.StringIO()
    status = main(arguments, stdin=io.StringIO(credential + "\n"), stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return status, cast(dict[str, object], json.loads(stdout.getvalue()))


def _refused_project_list(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    base_url: str,
    credential: str,
    project_key: str,
) -> dict[str, object]:
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    stdout, stderr = io.StringIO(), io.StringIO()
    status = main(
        [
            "--base-url",
            base_url,
            "knowledge",
            "list",
            "--scope",
            "project",
            "--project-key",
            project_key,
        ],
        stdin=io.StringIO(credential + "\n"),
        stdout=stdout,
        stderr=stderr,
    )
    assert status == EXIT_PERMANENT and stdout.getvalue() == ""
    return cast(dict[str, object], json.loads(stderr.getvalue()))


def _provision_project_seat(tenant: TenantFixture, project_key: str, seat_key: str) -> str:
    principal_id, credential = uuid4(), secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, 'commander', %s, false, %s)
            """,
            (principal_id, tenant.tenant_id, "Manibo Commander", now),
        )
        connection.execute(
            """
            INSERT INTO project_seats (
                principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (principal_id, tenant.tenant_id, project_key, seat_key, tenant.operator_id, now),
        )
    provision_credential(tenant.database.admin_dsn, tenant.tenant_id, principal_id, credential)
    return credential


def _database_evidence(tenant: TenantFixture) -> dict[str, int]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM events WHERE tenant_id = %s
                 AND kind = 'knowledge.document_registered') AS events,
              (SELECT count(*) FROM knowledge_documents WHERE tenant_id = %s) AS facts,
              (SELECT count(*) FROM knowledge_documents WHERE tenant_id = %s
                 AND scope = 'org' AND project_key IS NULL) AS org,
              (SELECT count(*) FROM knowledge_projection_documents WHERE tenant_id = %s)
                 AS projections,
              (SELECT count(DISTINCT project_key) FROM knowledge_documents WHERE tenant_id = %s
                 AND scope = 'project') AS projects
            """,
            (tenant.tenant_id,) * 5,
        ).fetchone()
    assert row is not None
    return {key: int(value) for key, value in row.items()}


def _assert_authority_is_immutable(tenant: TenantFixture, document_id: UUID) -> None:
    with (
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
        psycopg.connect(tenant.database.admin_dsn) as connection,
    ):
        connection.execute(
            "UPDATE knowledge_documents SET title = 'changed' WHERE document_id = %s",
            (document_id,),
        )


def _assert_malformed_payloads_are_refused(base_url: str, credential: str) -> None:
    headers = {"Authorization": f"Bearer {credential}", **telemetry_headers()}
    payload = {
        "scope": "org",
        "project_key": None,
        "title": "Ambiguous",
        "body": "Direct body",
        "source_ref": "ctower-knowledge",
    }
    with httpx.Client(base_url=base_url) as client:
        ambiguous = client.post(
            "/v1/knowledge/documents",
            headers={"Idempotency-Key": str(uuid4()), **headers},
            json=payload,
        )
        extra = client.post(
            "/v1/knowledge/documents",
            headers={"Idempotency-Key": str(uuid4()), **headers},
            json={**payload, "source_ref": None, "unexpected": True},
        )
    assert (ambiguous.status_code, ambiguous.json()["code"]) == (422, "validation-error")
    assert (extra.status_code, extra.json()["code"]) == (422, "validation-error")


def _titles(listing: dict[str, object]) -> list[str]:
    documents = cast(list[dict[str, object]], listing["documents"])
    return [cast(str, document["title"]) for document in documents]


def _print_transcript(**entries: dict[str, object]) -> None:
    print(
        "REAL_KNOWLEDGE_TRANSCRIPT "
        + json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )
