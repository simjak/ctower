"""The kernel bridge: each ref-specific op runs in a child bound to that ref's own kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, cast

import psycopg

from tools.development_runtime._rehearsal_live import assert_read_only, live_read
from tools.development_runtime._rehearsal_vocabulary import (
    KERNEL_CALL_TIMEOUT_SECONDS,
    KERNEL_SOURCE_RELATIVE,
    LIVE_DSN_ENVIRON,
    LIVE_DSN_SENTINEL,
    UpgradeRehearsalError,
)

__all__ = ["kernel_call", "kernel_worker", "open_database"]


class _SemanticCheck(Protocol):
    name: str
    query: str


class _LedgerModule(Protocol):
    _LEDGER: str
    _SCHEMA_QUERIES: tuple[str, ...]
    _SEMANTIC_CHECKS: tuple[_SemanticCheck, ...]
    _SEMANTIC_QUERIES: tuple[tuple[str, str], ...]

    def _schema_fingerprint(self, records: tuple[tuple[object, ...], ...]) -> str: ...

    def _schema_records(
        self, connection: psycopg.Connection[tuple[object, ...]]
    ) -> tuple[tuple[object, ...], ...]: ...


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def kernel_call(
    source: Path,
    operation: str,
    live_dsn: str | None = None,
    **arguments: str,
) -> dict[str, Any]:
    """Run one migration-kernel operation inside a subprocess bound to ``source``.

    The resolved live DSN (a secret) travels in the environment only — never in argv.
    """

    kernel_source = str((source / KERNEL_SOURCE_RELATIVE).resolve())
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([kernel_source, str(_repo_root())]),
    }
    if live_dsn is not None:
        environment[LIVE_DSN_ENVIRON] = live_dsn
    command = [
        sys.executable,
        "-m",
        "tools.development_runtime.rehearsal",
        "--kernel-op",
        operation,
        "--kernel-source",
        str(source),
        *[
            part
            for key, value in arguments.items()
            if value is not None
            for part in (f"--{key.replace('_', '-')}", value)
        ],
    ]
    # The child failure is the result we report. process_execution.run cannot carry the
    # ref-bound PYTHONPATH or secret-bearing DSN environment, so this boundary stays explicit.
    finished = subprocess.run(  # noqa: S603 - bounded, fixed argv, no shell
        command,
        cwd=str(_repo_root()),
        env=environment,
        capture_output=True,
        text=True,
        timeout=KERNEL_CALL_TIMEOUT_SECONDS,
        check=False,
    )
    payload = finished.stdout.strip().splitlines()
    if not payload:
        raise UpgradeRehearsalError(
            f"kernel op {operation} produced no result: {finished.stderr[-400:]}"
        )
    parsed = json.loads(payload[-1])
    if not isinstance(parsed, dict):
        raise UpgradeRehearsalError(f"kernel op {operation} returned a non-object result")
    return cast(dict[str, Any], parsed)


def kernel_worker(arguments: argparse.Namespace) -> int:
    """Import the kernel of exactly one ref and answer one operation in JSON."""

    source = Path(arguments.kernel_source)
    _assert_ref_kernel(source)
    match arguments.kernel_op:
        case "install":
            result = _op_install(arguments)
        case "semantics":
            result = _op_semantics(arguments)
        case "fingerprint":
            result = _op_fingerprint(arguments)
        case operation:
            raise UpgradeRehearsalError(f"unknown kernel operation: {operation}")
    print(json.dumps(result, sort_keys=True))
    return 0


def _assert_ref_kernel(source: Path) -> None:
    """Refuse a kernel that did not resolve from the named ref's source tree."""

    root = (source / KERNEL_SOURCE_RELATIVE).resolve()
    environment_path = os.environ.get("PYTHONPATH", "")
    if str(root) not in environment_path.split(os.pathsep):
        raise UpgradeRehearsalError(f"kernel PYTHONPATH is not bound to {root}")
    import ctower_kernel  # noqa: PLC0415 - import must happen after the ref binds PYTHONPATH

    resolved = ctower_kernel.__file__
    if resolved is None or not Path(resolved).resolve().is_relative_to(root):
        raise UpgradeRehearsalError(f"kernel resolved to {resolved}, not {root}")


def _op_install(arguments: argparse.Namespace) -> dict[str, Any]:
    # Import after _assert_ref_kernel so this child uses the named ref's kernel and migrations.
    from ctower_kernel.record.postgres import (  # noqa: PLC0415
        apply_migrations,
        provision_database_roles,
    )

    started = time.monotonic()
    try:
        provision_database_roles(arguments.admin_dsn)
        apply_migrations(arguments.migrator_dsn, role_admin_dsn=arguments.admin_dsn)
    except Exception as error:  # noqa: BLE001 - the typed refusal is the reported result
        return {
            "ok": False,
            "error_class": type(error).__name__,
            "code": getattr(error, "code", type(error).__name__),
            "detail": str(getattr(error, "detail", str(error)))[:600],
            "seconds": round(time.monotonic() - started, 2),
        }
    return {"ok": True, "seconds": round(time.monotonic() - started, 2)}


def _op_semantics(arguments: argparse.Namespace) -> dict[str, Any]:
    module = _ledger_module()
    checks: dict[str, str] = {}
    with open_database(arguments.dsn) as (connection, live):
        for name, query in _named_checks(module):
            try:
                rows = _read_rows(connection, query, live=live)
                checks[name] = "ok" if rows and rows[0][0] is False else "reject"
            except psycopg.Error as error:
                connection.rollback()
                checks[name] = f"error:{error.sqlstate}"
    return {"checks": checks}


def _op_fingerprint(arguments: argparse.Namespace) -> dict[str, Any]:
    module = _ledger_module()
    with open_database(arguments.dsn) as (connection, live):
        records = _schema_records(module, connection, live=live)
        fingerprint = module._schema_fingerprint(records)
    digested = {
        f"{kind}:{identity}": hashlib.sha256(str(detail).encode()).hexdigest()[:16]
        for kind, identity, detail in records
    }
    return {"fingerprint": fingerprint, "records": digested}


def _ledger_module() -> _LedgerModule:
    # This private kernel module is imported only inside the ref-bound child. The parent process
    # never imports it, preserving target-ref isolation for semantic checks and attestation.
    from ctower_kernel.record import _migration_ledger_sql  # noqa: PLC0415

    return cast(_LedgerModule, _migration_ledger_sql)


def _named_checks(module: _LedgerModule) -> tuple[tuple[str, str], ...]:
    """Read the check table in either current or legacy kernel shape."""

    declared = getattr(module, "_SEMANTIC_CHECKS", None)
    if isinstance(declared, tuple):
        checks = cast(tuple[_SemanticCheck, ...], declared)
        return tuple((check.name, check.query) for check in checks)
    return module._SEMANTIC_QUERIES


@contextmanager
def open_database(
    dsn: str,
) -> Iterator[tuple[psycopg.Connection[tuple[object, ...]], bool]]:
    """Open a clone normally, or the live sentinel as an enforced read-only session."""

    if dsn != LIVE_DSN_SENTINEL:
        with psycopg.connect(dsn, connect_timeout=10) as connection:
            yield connection, False
        return
    guarded = os.environ.get(LIVE_DSN_ENVIRON)
    if not guarded:
        raise UpgradeRehearsalError(
            f"live probe requested without {LIVE_DSN_ENVIRON} in the environment"
        )
    with psycopg.connect(guarded, connect_timeout=10) as connection:
        assert_read_only(connection)
        yield connection, True


def _read_rows(
    connection: psycopg.Connection[tuple[object, ...]],
    statement: str,
    *,
    live: bool,
) -> list[tuple[object, ...]]:
    if live:
        return live_read(connection, statement)
    return connection.execute(statement).fetchall()


def _schema_records(
    module: _LedgerModule,
    connection: psycopg.Connection[tuple[object, ...]],
    *,
    live: bool,
) -> tuple[tuple[object, ...], ...]:
    """Run the attestation's own schema readers; live reads go through the guard."""

    if not live:
        return module._schema_records(connection)
    records: list[tuple[object, ...]] = []
    for query in module._SCHEMA_QUERIES:
        parameters = tuple(module._LEDGER for _ in range(query.count("%s")))
        records.extend(live_read(connection, query, parameters))
    return tuple(sorted(records))
