"""The kernel bridge: each ref-specific op runs in a child bound to that ref's own kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg

from tools.development_runtime._rehearsal_vocabulary import (
    KERNEL_CALL_TIMEOUT_SECONDS,
    KERNEL_SOURCE_RELATIVE,
    LIVE_DSN_ENVIRON,
    LIVE_DSN_SENTINEL,
    UpgradeRehearsalError,
)
from tools.development_runtime._rehearsal_live import live_read

__all__ = ["kernel_call", "kernel_worker", "open_database"]

# ---------------------------------------------------------------------------
# kernel bridge -- every ref-specific operation runs against that ref's own source tree
# ---------------------------------------------------------------------------


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
    # The ref's kernel source comes first; the harness repo root makes `tools.development_runtime`
    # importable in the child. PYTHONPATH wins over the venv's editable install (verified), and
    # _ref_kernel refuses any kernel that did not resolve from the ref's own tree.
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
    # Bounded, check=False: the child's failure IS the result we report (mc parity; the shared
    # tools.process_execution.run has no env= parameter, so the DSN could not travel that way).
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
    return json.loads(payload[-1])  # type: ignore[no-any-return]


def kernel_worker(arguments: argparse.Namespace) -> int:
    """Subprocess entry point. Imports the kernel of exactly one ref and answers in JSON."""

    source = Path(arguments.kernel_source)
    bound = _ref_kernel(source)
    operations = {
        "install": _op_install,
        "semantics": _op_semantics,
        "fingerprint": _op_fingerprint,
    }
    result = operations[arguments.kernel_op](bound, arguments)
    print(json.dumps(result, sort_keys=True))
    return 0


def _ref_kernel(source: Path):
    """Import ``ctower_kernel`` bound to the ref's own source tree, refusing any other origin."""

    root = (source / KERNEL_SOURCE_RELATIVE).resolve()
    environment_path = os.environ.get("PYTHONPATH", "")
    if str(root) not in environment_path.split(os.pathsep):
        raise UpgradeRehearsalError(f"kernel PYTHONPATH is not bound to {root}")
    import ctower_kernel

    if not Path(ctower_kernel.__file__).resolve().is_relative_to(root):  # type: ignore[attr-defined]
        raise UpgradeRehearsalError(
            f"kernel resolved to {ctower_kernel.__file__}, not {root}"
        )
    return ctower_kernel


def _op_install(_source: Any, arguments: argparse.Namespace) -> dict[str, Any]:
    from ctower_kernel.record.postgres import apply_migrations, provision_database_roles

    started = time.monotonic()
    try:
        provision_database_roles(arguments.admin_dsn)
        apply_migrations(arguments.migrator_dsn, role_admin_dsn=arguments.admin_dsn)
    except Exception as error:  # noqa: BLE001 -- the refusal IS the result we report
        return {
            "ok": False,
            "error_class": type(error).__name__,
            "code": getattr(error, "code", type(error).__name__),
            "detail": str(getattr(error, "detail", str(error)))[:600],
            "seconds": round(time.monotonic() - started, 2),
        }
    return {"ok": True, "seconds": round(time.monotonic() - started, 2)}


def _op_semantics(_source: Any, arguments: argparse.Namespace) -> dict[str, Any]:
    module = _ledger_module()
    checks: dict[str, str] = {}
    with open_database(arguments.dsn) as (connection, live):
        for name, query in _named_checks(module):
            try:
                rows = _read_rows(connection, query, live)
                checks[name] = "ok" if rows and rows[0][0] is False else "reject"
            except psycopg.Error as error:
                connection.rollback()
                checks[name] = f"error:{error.sqlstate}"
    return {"checks": checks}


def _op_fingerprint(_source: Any, arguments: argparse.Namespace) -> dict[str, Any]:
    module = _ledger_module()
    with open_database(arguments.dsn) as (connection, live):
        records = _schema_records(module, connection, live)
        fingerprint = module._schema_fingerprint(records)  # noqa: SLF001 - the attestation's own reader
    digested = {
        f"{kind}:{identity}": hashlib.sha256(str(detail).encode()).hexdigest()[:16]
        for kind, identity, detail in records
    }
    return {"fingerprint": fingerprint, "records": digested}


def _ledger_module() -> Any:
    from ctower_kernel.record import _migration_ledger_sql

    return _migration_ledger_sql


def _named_checks(module: Any) -> tuple[tuple[str, str], ...]:
    """Read the check table in either shape: main's (name, query) pairs or dataclasses."""

    declared = getattr(module, "_SEMANTIC_CHECKS", None)
    if isinstance(declared, tuple):
        return tuple((check.name, check.query) for check in declared)
    return tuple(  # type: ignore[no-any-return]
        (name, query) for name, query in module._SEMANTIC_QUERIES  # noqa: SLF001
    )


@contextmanager
def open_database(dsn: str):
    """One door for both worlds: the live sentinel resolves to the guarded read-only session."""

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
    live: bool,
) -> list[tuple[Any, ...]]:
    if live:
        return live_read(connection, statement)
    return connection.execute(statement).fetchall()  # type: ignore[no-any-return]


def _schema_records(module: Any, connection: psycopg.Connection[tuple[object, ...]], live: bool):
    """Run the attestation's own schema readers; against live, through the read-only guard."""

    if not live:
        return module._schema_records(connection)  # noqa: SLF001 - the attestation's own reader
    records: list[tuple[Any, ...]] = []
    for query in module._SCHEMA_QUERIES:  # noqa: SLF001
        parameters = tuple(module._LEDGER for _ in range(query.count("%s")))  # noqa: SLF001
        records.extend(live_read(connection, query, parameters))
    return tuple(sorted(records))


