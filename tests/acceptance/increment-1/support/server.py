"""Separate-process HTTP lifecycle for generated-client acceptance."""

from __future__ import annotations

import json
import multiprocessing
import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

import uvicorn

from ctower_api.interface import create_app
from ctower_api.telemetry import TelemetryRecorder
from ctower_kernel.proof import Proof
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.workflow import Workflow, WorkflowGraph
from ctower_kernel.workflow.postgres import PostgresWorkflow

__all__: tuple[str, ...] = ()
ROOT = Path(__file__).parents[4]


class _Process(Protocol):
    @property
    def exitcode(self) -> int | None: ...


@contextmanager
def running_api(
    runtime_dsn: str,
    *,
    telemetry_capture: Path | None = None,
    telemetry_failure: bool = False,
) -> Iterator[str]:
    """Run the composed API in another process and yield its loopback URL."""

    host = "127.0.0.1"
    port = _available_port(host)
    process = multiprocessing.get_context("spawn").Process(
        target=_serve,
        args=(runtime_dsn, host, port, telemetry_capture, int(telemetry_failure)),
        daemon=True,
    )
    process.start()
    try:
        _wait_until_listening(process, host, port)
        yield f"http://{host}:{port}"
    finally:
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)


def _serve(
    runtime_dsn: str,
    host: str,
    port: int,
    telemetry_capture: Path | None,
    telemetry_failure: int,
) -> None:
    recorder = TelemetryRecorder(
        _exporter(telemetry_capture, fail=bool(telemetry_failure))
        if telemetry_capture is not None or telemetry_failure
        else None
    )
    proof_store = PostgresProof(runtime_dsn, telemetry=recorder)
    workflow_store = PostgresWorkflow(
        runtime_dsn,
        proof_gate=proof_store,
        telemetry=recorder,
    )
    graph_payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    uvicorn.run(
        create_app(
            PostgresRecord(runtime_dsn, telemetry=recorder),
            proof=Proof(writer=proof_store),
            workflow=Workflow((WorkflowGraph.from_mapping(graph_payload),), writer=workflow_store),
            telemetry=recorder,
        ),
        host=host,
        port=port,
        log_level="error",
        access_log=False,
    )


def _exporter(capture: Path | None, *, fail: bool) -> Callable[[dict[str, object]], None]:
    def export(record: dict[str, object]) -> None:
        if fail:
            raise OSError("injected telemetry exporter failure")
        if capture is None:
            raise RuntimeError("telemetry capture path is missing")
        with capture.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")

    return export


def _available_port(host: str) -> int:
    with socket.socket() as listener:
        listener.bind((host, 0))
        return int(listener.getsockname()[1])


def _wait_until_listening(process: _Process, host: str, port: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.exitcode is not None:
            raise RuntimeError(f"API process exited before listening: {process.exitcode}")
        try:
            with socket.create_connection((host, port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError("API process did not listen within ten seconds")
