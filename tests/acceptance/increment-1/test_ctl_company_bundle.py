"""Thin company-bundle CLI acceptance through the generated HTTP client."""

from __future__ import annotations

import io
import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
import uvicorn
from ctower_contracts import CATALOG
from fastapi import FastAPI
from support.catalog import MemoryObjectStore, minimal_bundle
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.catalog import CompanyBundle, PostgresCatalog
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork
from ctowerctl import main

__all__: tuple[str, ...] = ()

EXIT_TEMPORARY = 75


class _MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


@pytest.fixture
def cli_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _MemoryBackend:
    backend = _MemoryBackend()
    monkeypatch.setattr("ctowerctl.spool._keyring._secure_backend", lambda: backend)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return backend


def test_company_bundle_cli_validate_plan_apply_export_round_trip(
    tenant: TenantFixture,
    cli_state: _MemoryBackend,
    tmp_path: Path,
) -> None:
    del cli_state
    bundle_file = tmp_path / "company-bundle.yaml"
    bundle_file.write_text(
        json.dumps(_tenant_bundle().model_dump(mode="json", by_alias=True)),
        encoding="utf-8",
    )
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        CATALOG,
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
    )
    with _server(tenant.database.runtime_dsn, catalog=catalog) as base_url:
        validated, planned, applied, exported, replanned = _company_round_trip(
            base_url,
            bundle_file,
            tenant.operator_credential,
            tmp_path,
        )

    assert validated[0] == 0
    assert json.loads(validated[1])["valid"] is True
    assert planned[0] == 0
    assert applied[0] == EXIT_TEMPORARY
    assert json.loads(applied[1])["state"] == "queued"
    assert exported[0] == 0
    assert exported[1].endswith("\n") and not exported[1].endswith("\n\n")
    assert "metadata:" not in exported[1]
    assert json.loads(replanned[1])["actions"] == []


def _run(arguments: list[str], *, authority: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    status = main(
        arguments,
        stdin=io.StringIO(f"{authority}\n"),
        stdout=stdout,
        stderr=stderr,
    )
    return status, stdout.getvalue(), stderr.getvalue()


def _run_company(
    base_url: str,
    command: list[str],
    authority: str,
) -> tuple[int, str, str]:
    return _run(
        ["--base-url", base_url, "company", "bundle", *command],
        authority=authority,
    )


def _company_round_trip(
    base_url: str,
    bundle_file: Path,
    authority: str,
    output_directory: Path,
) -> tuple[
    tuple[int, str, str],
    tuple[int, str, str],
    tuple[int, str, str],
    tuple[int, str, str],
    tuple[int, str, str],
]:
    validated = _run_company(base_url, ["validate", str(bundle_file)], authority)
    planned = _run_company(base_url, ["plan", str(bundle_file)], authority)
    plan = json.loads(planned[1])
    applied = _run_company(
        base_url,
        [
            "apply",
            str(bundle_file),
            "--command-id",
            str(uuid4()),
            "--expected-active-version",
            "0",
            "--plan-digest",
            plan["plan_digest"],
        ],
        authority,
    )
    exported = _run_company(base_url, ["export"], authority)
    exported_file = output_directory / "exported.yaml"
    exported_file.write_text(exported[1], encoding="utf-8")
    replanned = _run_company(base_url, ["plan", str(exported_file)], authority)
    return validated, planned, applied, exported, replanned


def _tenant_bundle() -> CompanyBundle:
    bundle = minimal_bundle()
    return bundle.model_copy(
        update={
            "company": bundle.company.model_copy(
                update={"key": "ctower", "display_name": "Ctower"}
            ),
            "resources": tuple(
                resource.model_copy(
                    update={
                        "component": resource.component.model_copy(
                            update={
                                "scope": resource.component.scope.model_copy(
                                    update={"tenant": "ctower"}
                                )
                            }
                        )
                    }
                )
                for resource in bundle.resources
            ),
        }
    )


@contextmanager
def _server(
    dsn: str,
    *,
    catalog: PostgresCatalog | None = None,
) -> Iterator[str]:
    record = PostgresRecord(dsn)
    application = create_app(
        record,
        work=Work(record, writer=PostgresWork(dsn)),
        catalog=catalog,
    )
    with _serve(application) as base_url:
        yield base_url


@contextmanager
def _serve(application: FastAPI) -> Iterator[str]:
    port = _unused_port()
    config = uvicorn.Config(
        application,
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_config=None,
        log_level="critical",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_until_started(server, thread)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("acceptance API server did not stop")


def _wait_until_started(server: uvicorn.Server, thread: threading.Thread) -> None:
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        raise RuntimeError("acceptance API server did not start")


def _unused_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return cast(int, candidate.getsockname()[1])
