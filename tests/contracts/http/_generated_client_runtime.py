"""Focused raw-response harness for both generated HTTP clients."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

from ctower_client import CtowerClient

__all__ = [
    "compile_typescript_client",
    "node_executable",
    "python_client",
    "run_command",
]

ROOT = Path(__file__).parents[3]


def python_client(
    raw_text: str,
    *,
    status: int,
    problem: bool = False,
) -> CtowerClient:
    """Return the actual Python client over one exact UTF-8 response body."""

    def handler(_request: httpx.Request) -> httpx.Response:
        content_type = "application/problem+json" if problem else "application/json"
        return httpx.Response(
            status,
            headers={"content-type": content_type},
            content=raw_text.encode(),
        )

    client = CtowerClient("http://contract.invalid", credential="opaque")
    client._http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://contract.invalid",
    )
    return client


def compile_typescript_client(target: Path, *, source_root: Path | None = None) -> None:
    """Compile the actual generated TypeScript package into ``target``."""

    package = source_root or ROOT / "generated/typescript/ctower-client"
    completed = run_command(
        (
            node_executable(),
            str(_typescript_compiler()),
            "--project",
            str(package / "tsconfig.json"),
            "--noEmit",
            "false",
            "--outDir",
            str(target),
        ),
        cwd=ROOT,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout + completed.stderr)
    (target / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")


def node_executable() -> str:
    """Resolve Node from the process PATH and fail closed when unavailable."""

    node = shutil.which("node", path=os.environ.get("PATH"))
    if node is None:
        raise RuntimeError("Node.js is required on PATH for TypeScript runtime vectors")
    return node


def run_command(
    command: tuple[str, ...],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run a verifier command without shell interpolation."""

    environment = {**os.environ, "CTOWER_TEST_COMMAND": json.dumps(command)}
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            "import json, os; "
            "command = json.loads(os.environ.pop('CTOWER_TEST_COMMAND')); "
            "os.execv(command[0], command)",
        ),
        check=False,
        cwd=cwd,
        capture_output=True,
        env=environment,
        text=True,
        timeout=30,
    )


def _typescript_compiler() -> Path:
    candidates = (
        ROOT / "node_modules/typescript/bin/tsc",
        Path(sys.prefix).resolve().parent / "node_modules/typescript/bin/tsc",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    executable = shutil.which("tsc", path=os.environ.get("PATH"))
    if executable is not None:
        return Path(executable)
    raise RuntimeError("TypeScript compiler is required from the repository toolchain")
