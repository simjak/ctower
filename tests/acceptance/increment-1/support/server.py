"""Separate-process HTTP lifecycle for generated-client acceptance."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

import uvicorn

from ctower_api.interface import create_app
from ctower_api.telemetry import TelemetryRecorder
from ctower_client import (
    AdmitIntent,
    CtowerClient,
    TicketIntentRequest,
    WorkflowStartRequest,
)
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.proof import Criterion, Proof, ProofPolicy
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork
from ctower_kernel.workflow import Workflow, WorkflowGraph
from ctower_kernel.workflow.postgres import PostgresWorkflow, PostgresWorkflowPolicyPins

__all__: tuple[str, ...] = ()
ROOT = Path(__file__).parents[4]


def start_and_admit(client: CtowerClient, ticket_id: UUID) -> None:
    """Prepare the authored I1 Workflow through its explicit public commands."""

    graph_payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    graph = WorkflowGraph.from_mapping(graph_payload)
    client.start_ticket_workflow(
        ticket_id,
        WorkflowStartRequest(
            workflow_ref=graph.reference,
            workflow_digest=graph.digest,
            execution_policy_ref="ctower.trust-spine-four-stage.execution@1",
            execution_policy_digest=_digest(
                "packs/policies/execution/trust-spine-four-stage-v1.yaml"
            ),
            gate_policy_ref="ctower.trust-spine-four-stage.gates@1",
            gate_policy_digest=_digest("packs/policies/gates/trust-spine-four-stage-v1.yaml"),
            evidence_policy_ref="ctower.trust-spine-four-stage.evidence@1",
            evidence_policy_digest=_digest(
                "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
            ),
        ),
        command_id=uuid4(),
    )
    client.apply_ticket_intent(
        ticket_id,
        TicketIntentRequest(
            intent=AdmitIntent(kind="admit", expected_version=1, reason="Ready for Workflow")
        ),
        command_id=uuid4(),
    )


def _digest(relative: str) -> str:
    return f"sha256:{hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()}"


def _policy_digests() -> dict[str, str]:
    return {
        "ctower.trust-spine-four-stage.execution@1": _digest(
            "packs/policies/execution/trust-spine-four-stage-v1.yaml"
        ),
        "ctower.trust-spine-four-stage.gates@1": _digest(
            "packs/policies/gates/trust-spine-four-stage-v1.yaml"
        ),
        "ctower.trust-spine-four-stage.evidence@1": _digest(
            "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
        ),
    }


def proof_policy() -> ProofPolicy:
    """Load proof obligations from the exact authored bytes pinned by Workflow."""

    gate_bytes = (ROOT / "packs/policies/gates/trust-spine-four-stage-v1.yaml").read_bytes()
    evidence_bytes = (ROOT / "packs/policies/evidence/trust-spine-four-stage-v1.yaml").read_bytes()
    return ProofPolicy.from_mappings(
        json.loads(gate_bytes),
        json.loads(evidence_bytes),
        gate_policy_digest="sha256:" + hashlib.sha256(gate_bytes).hexdigest(),
        evidence_policy_digest="sha256:" + hashlib.sha256(evidence_bytes).hexdigest(),
    )


def fixture_proof_policy(workflow_ref: str, criterion: Criterion) -> ProofPolicy:
    """Build the exact synthetic pin used by direct persistence acceptance fixtures."""

    return ProofPolicy(
        workflow_ref=workflow_ref,
        gate_policy_ref="fixture.gates@1",
        gate_policy_digest="sha256:" + "2" * 64,
        evidence_policy_ref="fixture.evidence@1",
        evidence_policy_digest="sha256:" + "3" * 64,
        criteria=(criterion,),
        reviewer_kind="operator",
        self_review_forbidden=True,
    )


def fixture_proof_store(
    dsn: str, workflow_ref: str, criterion_key: str, description: str
) -> PostgresProof:
    """Compose a fail-closed Proof store for one synthetic Workflow pin."""

    criterion = Criterion(
        key=criterion_key,
        description=description,
        candidate_dependent=True,
        requires_verdict=True,
    )
    return PostgresProof(
        dsn,
        policies=(fixture_proof_policy(workflow_ref, criterion),),
        policy_pins=PostgresWorkflowPolicyPins(),
    )


class _Process(Protocol):
    @property
    def exitcode(self) -> int | None: ...


@contextmanager
def running_api(
    runtime_dsn: str,
    *,
    standby_dsn: str | None = None,
    telemetry_capture: Path | None = None,
    telemetry_failure: bool = False,
    projection_dsn: str | None = None,
) -> Iterator[str]:
    """Run the composed API in another process and yield its loopback URL."""

    host = "127.0.0.1"
    port = _available_port(host)
    process = multiprocessing.get_context("spawn").Process(
        target=_serve,
        args=(
            runtime_dsn,
            standby_dsn,
            projection_dsn,
            host,
            port,
            telemetry_capture,
            int(telemetry_failure),
        ),
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
    standby_dsn: str | None,
    projection_dsn: str | None,
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
    proof_store = PostgresProof(
        runtime_dsn,
        policies=(proof_policy(),),
        policy_pins=PostgresWorkflowPolicyPins(),
        telemetry=recorder,
    )
    workflow_store = PostgresWorkflow(
        runtime_dsn,
        proof_gate=proof_store,
        readiness_gate=PostgresWork(runtime_dsn),
        telemetry=recorder,
    )
    graph_payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    record = PostgresRecord(runtime_dsn, standby_dsn=standby_dsn, telemetry=recorder)
    work = Work(record, writer=PostgresWork(runtime_dsn), telemetry=recorder)
    uvicorn.run(
        create_app(
            record,
            proof=Proof(writer=proof_store),
            workflow=Workflow(
                (WorkflowGraph.from_mapping(graph_payload),),
                writer=workflow_store,
                policy_digests=_policy_digests(),
            ),
            work=work,
            projections=(
                Projections(PostgresProjections(projection_dsn))
                if projection_dsn is not None
                else None
            ),
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
