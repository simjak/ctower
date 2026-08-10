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
from fastapi import FastAPI
from support.catalog import FileSchemas, MemoryObjectStore

from ctower_api.catalog_resolver import CatalogComponentResolver
from ctower_api.interface import create_app
from ctower_api.telemetry import TelemetryRecorder
from ctower_client import (
    AdmitIntent,
    CtowerClient,
    TicketIntentRequest,
    WorkflowStartRequest,
)
from ctower_kernel.attention import Attention
from ctower_kernel.attention.postgres import PostgresAttention
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.postgres import PostgresBoardContextFacts
from ctower_kernel.catalog import PostgresCatalog
from ctower_kernel.inbox import Inbox, PostgresInbox
from ctower_kernel.knowledge import (
    Knowledge,
    PostgresKnowledge,
    StaticFileKnowledgeSource,
    bundled_static_root,
)
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.proof import Criterion, Proof, ProofPolicy
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork
from ctower_kernel.work.requests import PostgresRequests, Requests
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
    return ProofPolicy.from_bytes(gate_bytes, evidence_bytes)


def fixture_proof_policy(workflow_ref: str, *criteria: Criterion) -> ProofPolicy:
    """Build the exact synthetic pin used by direct persistence acceptance fixtures."""

    gate_bytes = json.dumps(
        {
            "schema": "ctower.gate-policy/v1",
            "key": "fixture.gates",
            "revision": 1,
            "workflow_ref": workflow_ref,
            "evidence_policy_ref": "fixture.evidence@1",
            "criteria": [
                {
                    "key": criterion.key,
                    "description": criterion.description,
                    "candidate_dependent": criterion.candidate_dependent,
                    "requires_verdict": criterion.requires_verdict,
                }
                for criterion in criteria
            ],
            "protected_verdict": {
                "reviewer_kind": "operator",
                "self_review": "forbidden",
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    evidence_bytes = json.dumps(
        {
            "schema": "ctower.evidence-policy/v1",
            "key": "fixture.evidence",
            "revision": 1,
            "digest_algorithm": "sha256",
            "content_encoding": "utf-8",
            "candidate_binding": "current_digest",
            "corruption_policy": "reject",
            "missing_policy": "reject",
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return ProofPolicy.from_bytes(
        gate_bytes,
        evidence_bytes,
    )


def fixture_proof_store(dsn: str, policy: ProofPolicy) -> PostgresProof:
    """Compose a fail-closed Proof store for one synthetic Workflow pin."""

    return PostgresProof(
        dsn,
        policies=(policy,),
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
    catalog_backed: bool = False,
    workflow_graph: WorkflowGraph | None = None,
    proof_policy_override: ProofPolicy | None = None,
    execution_policy_digest: str | None = None,
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
            int(catalog_backed),
            workflow_graph,
            proof_policy_override,
            execution_policy_digest,
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
    catalog_backed: int,
    workflow_graph: WorkflowGraph | None,
    proof_policy_override: ProofPolicy | None,
    execution_policy_digest: str | None,
) -> None:
    app = application(
        runtime_dsn,
        standby_dsn=standby_dsn,
        projection_dsn=projection_dsn,
        telemetry_capture=telemetry_capture,
        telemetry_failure=bool(telemetry_failure),
        catalog_backed=bool(catalog_backed),
        workflow_graph=workflow_graph,
        proof_policy_override=proof_policy_override,
        execution_policy_digest=execution_policy_digest,
    )
    uvicorn.run(app, host=host, port=port, log_level="error", access_log=False)


def application(
    runtime_dsn: str,
    *,
    standby_dsn: str | None = None,
    projection_dsn: str | None = None,
    telemetry_capture: Path | None = None,
    telemetry_failure: bool = False,
    catalog_backed: bool = False,
    workflow_graph: WorkflowGraph | None = None,
    proof_policy_override: ProofPolicy | None = None,
    execution_policy_digest: str | None = None,
) -> FastAPI:
    recorder = _recorder(telemetry_capture, telemetry_failure)
    catalog_store = MemoryObjectStore()
    catalog = PostgresCatalog(
        runtime_dsn,
        FileSchemas(),
        catalog_store,
        key_reference="kms:test:catalog",
        telemetry=recorder,
    )
    resolver = CatalogComponentResolver(catalog) if catalog_backed else None
    selected_policy = proof_policy_override or proof_policy()
    proof_store = PostgresProof(
        runtime_dsn,
        policies=() if catalog_backed else (selected_policy,),
        policy_pins=PostgresWorkflowPolicyPins(),
        policy_resolver=resolver,
        telemetry=recorder,
    )
    record = PostgresRecord(runtime_dsn, standby_dsn=standby_dsn, telemetry=recorder)
    work = Work(record, writer=PostgresWork(runtime_dsn), telemetry=recorder)
    workflow = _workflow(
        runtime_dsn,
        proof_store,
        resolver,
        recorder,
        catalog_backed=catalog_backed,
        workflow_graph=workflow_graph,
        proof_policy_override=proof_policy_override,
        selected_policy=selected_policy,
        execution_policy_digest=execution_policy_digest,
    )
    return create_app(
        record,
        proof=Proof(writer=proof_store),
        workflow=workflow,
        work=work,
        requests=Requests(PostgresRequests(runtime_dsn), telemetry=recorder),
        catalog=catalog if catalog_backed else None,
        projections=(
            Projections(PostgresProjections(projection_dsn)) if projection_dsn is not None else None
        ),
        attention=Attention(PostgresAttention(runtime_dsn)),
        board_context=BoardContextFacts(PostgresBoardContextFacts(runtime_dsn)),
        inbox=(Inbox(PostgresInbox(runtime_dsn)) if projection_dsn is not None else None),
        knowledge=_knowledge(runtime_dsn),
        telemetry=recorder,
    )


def _workflow(
    runtime_dsn: str,
    proof_store: PostgresProof,
    resolver: CatalogComponentResolver | None,
    recorder: TelemetryRecorder,
    *,
    catalog_backed: bool,
    workflow_graph: WorkflowGraph | None,
    proof_policy_override: ProofPolicy | None,
    selected_policy: ProofPolicy,
    execution_policy_digest: str | None,
) -> Workflow:
    workflow_store = PostgresWorkflow(
        runtime_dsn,
        proof_gate=proof_store,
        readiness_gate=PostgresWork(runtime_dsn),
        telemetry=recorder,
    )
    graph_payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    graph = workflow_graph or WorkflowGraph.from_mapping(graph_payload)
    policy_digests = _selected_policy_digests(
        graph, proof_policy_override, selected_policy, execution_policy_digest
    )
    return Workflow(
        () if catalog_backed else (graph,),
        writer=workflow_store,
        policy_digests={} if catalog_backed else policy_digests,
        resolver=resolver,
    )


def _selected_policy_digests(
    graph: WorkflowGraph,
    override: ProofPolicy | None,
    selected: ProofPolicy,
    execution_policy_digest: str | None,
) -> dict[str, str]:
    if override is None:
        return _policy_digests()
    if execution_policy_digest is None:
        raise ValueError("proof policy override requires an execution policy digest")
    if graph.execution_policy_ref is None:
        raise ValueError("proof policy override requires an execution policy reference")
    return {
        graph.execution_policy_ref: execution_policy_digest,
        selected.gate_policy_ref: selected.gate_policy_digest,
        selected.evidence_policy_ref: selected.evidence_policy_digest,
    }


def _knowledge(runtime_dsn: str) -> Knowledge:
    return Knowledge(
        PostgresKnowledge(
            runtime_dsn,
            source=StaticFileKnowledgeSource(bundled_static_root()),
        )
    )


def _recorder(capture: Path | None, failure: int) -> TelemetryRecorder:
    exporter = _exporter(capture, fail=bool(failure)) if capture is not None or failure else None
    return TelemetryRecorder(exporter)


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
