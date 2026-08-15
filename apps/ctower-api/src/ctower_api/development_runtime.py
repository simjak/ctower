"""Same-artifact API and worker composition for the approved E2 shadow runtime."""

from __future__ import annotations

import hashlib
import json
import signal
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import uvicorn
from ctower_contracts import CATALOG

from ctower_api._development_catalog_store import development_catalog_store
from ctower_api._routine_loop import load_routine_revisions
from ctower_api.control_worker import build_worker
from ctower_api.development_config import DevelopmentConfig, load_config, load_state
from ctower_api.development_finalizer import (
    DevelopmentFinalizerProgress,
    load_finalizer_progress,
    write_finalizer_progress,
)
from ctower_api.development_secrets import development_dsn, load_secret
from ctower_api.interface import OidcRuntimeConfig, create_app
from ctower_api.synthetic_handler import SyntheticFourStageHandler, SyntheticPolicyPins
from ctower_client import CtowerClient
from ctower_kernel.access.oidc import OidcProvider
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
from ctower_kernel.proof import Proof, ProofPolicy
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record import DurabilityFinalizationBatch
from ctower_api.estate_imports import PostgresEstateImports
from ctower_kernel.record.postgres import PostgresDurabilityFinalizer, PostgresRecord
from ctower_kernel.runtime import FixedOperations, Routine, RoutineRevision
from ctower_kernel.runtime.postgres import PostgresRuntime
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork
from ctower_kernel.work.request_cutover import PostgresRequestCutover, RequestCutover
from ctower_kernel.work.requests import PostgresRequests, Requests
from ctower_kernel.work.rulings import PostgresRulings, Rulings
from ctower_kernel.workflow import Workflow, WorkflowGraph
from ctower_kernel.workflow.postgres import PostgresWorkflow, PostgresWorkflowPolicyPins

__all__ = ["api_main", "worker_main"]

_SOURCE_ROOT = Path(__file__).parents[4]
_WORKFLOW = "workflows/ctower.trust-spine-four-stage/v1.yaml"
_EXECUTION = "policies/execution/trust-spine-four-stage-v1.yaml"
_GATE = "policies/gates/trust-spine-four-stage-v1.yaml"
_EVIDENCE = "policies/evidence/trust-spine-four-stage-v1.yaml"


@dataclass(slots=True)
class _DevelopmentFinalizerProgressRecorder:
    sequence: int

    @classmethod
    def from_persisted_state(cls) -> _DevelopmentFinalizerProgressRecorder:
        try:
            sequence = load_finalizer_progress().sequence
        except (OSError, ValueError):
            sequence = 0
        return cls(sequence)

    def completed(self, batch: DurabilityFinalizationBatch) -> None:
        self.sequence += 1
        write_finalizer_progress(
            DevelopmentFinalizerProgress(
                schema="ctower.development-finalizer-progress/v1",
                sequence=self.sequence,
                observed_at=datetime.now(UTC),
                scan_status="completed",
                attempted=batch.attempted,
                accepted=batch.accepted,
                pending=batch.pending,
                refused=batch.refused,
                quarantined=batch.quarantined,
                detail_code=None,
            )
        )

    def failed(self) -> None:
        self.sequence += 1
        write_finalizer_progress(
            DevelopmentFinalizerProgress(
                schema="ctower.development-finalizer-progress/v1",
                sequence=self.sequence,
                observed_at=datetime.now(UTC),
                scan_status="failed",
                attempted=0,
                accepted=0,
                pending=0,
                refused=0,
                quarantined=0,
                detail_code="finalizer-exception",
            )
        )


def api_main() -> None:
    """Serve the explicitly shadow-labeled local API."""

    config = load_config()
    runtime_dsn = development_dsn(config, "ctower_runtime")
    standby_dsn = development_dsn(config, "postgres", standby=True)
    projection_dsn = development_dsn(config, "ctower_projection_runtime")
    packs = _pack_root()
    record = PostgresRecord(runtime_dsn, standby_dsn=standby_dsn)
    proof_store = PostgresProof(
        runtime_dsn,
        policies=(_proof_policy(packs),),
        policy_pins=PostgresWorkflowPolicyPins(),
    )
    workflow_store = PostgresWorkflow(
        runtime_dsn,
        proof_gate=proof_store,
        readiness_gate=PostgresWork(runtime_dsn),
    )
    runtime_store = PostgresRuntime(runtime_dsn)
    revisions = load_routine_revisions(packs)
    uvicorn.run(
        create_app(
            record,
            proof=Proof(writer=proof_store),
            workflow=Workflow(
                (_workflow_graph(packs),),
                writer=workflow_store,
                policy_digests=_policy_digests(packs),
            ),
            work=Work(record, writer=PostgresWork(runtime_dsn)),
            requests=Requests(PostgresRequests(runtime_dsn)),
            rulings=Rulings(PostgresRulings(runtime_dsn)),
            request_cutover=RequestCutover(PostgresRequestCutover(runtime_dsn)),
            catalog=PostgresCatalog(
                runtime_dsn,
                CATALOG,
                development_catalog_store(),
                key_reference="vault:development-catalog-key",
            ),
            projections=Projections(PostgresProjections(projection_dsn)),
            attention=Attention(PostgresAttention(runtime_dsn)),
            board_context=BoardContextFacts(PostgresBoardContextFacts(runtime_dsn)),
            inbox=Inbox(PostgresInbox(runtime_dsn)),
            knowledge=Knowledge(
                PostgresKnowledge(
                    runtime_dsn,
                    source=StaticFileKnowledgeSource(bundled_static_root()),
                )
            ),
            estate_imports=PostgresEstateImports(
                runtime_dsn,
                trusted_keys={},
                parity_signer=None,
            ),
            synthetic_runtime=FixedOperations(runtime_store),
            synthetic_revision=_synthetic_revision(revisions),
            dream_dispatch_runtime=runtime_store,
            beat_dispatch_runtime=runtime_store,
            oidc=OidcRuntimeConfig(
                providers=_enabled_oidc_providers(config),
                login_attempt_signing_key=_login_attempt_signing_key(config),
                gate_enforcing=config.login_gate_enforcing,
            ),
        ),
        host=config.api_host,
        port=config.api_port,
        log_level="info",
        access_log=False,
    )


def worker_main() -> None:
    """Run scheduler, projection, synthetic, and ordinary durability loops."""

    config = load_config()
    state = load_state()
    runtime_dsn = development_dsn(config, "ctower_runtime")
    standby_dsn = development_dsn(config, "postgres", standby=True)
    projection_dsn = development_dsn(config, "ctower_projection_runtime")
    base_url = f"http://{config.api_host}:{config.api_port}"
    packs = _pack_root()
    runtime_store = PostgresRuntime(runtime_dsn)
    runtime = Routine(runtime_store)
    projections = Projections(PostgresProjections(projection_dsn))
    pins = SyntheticPolicyPins(
        workflow_digest=_workflow_graph(packs).digest,
        execution_policy_digest=_digest(packs / _EXECUTION),
        gate_policy_digest=_digest(packs / _GATE),
        evidence_policy_digest=_digest(packs / _EVIDENCE),
    )
    with (
        CtowerClient(base_url, credential=load_secret(config.commander_secret_ref)) as author,
        CtowerClient(base_url, credential=load_secret(config.operator_secret_ref)) as reviewer,
    ):
        worker = build_worker(
            runtime,
            projections,
            pack_root=packs,
            fixed_operations=FixedOperations(runtime_store),
            synthetic_handler=SyntheticFourStageHandler(
                author,
                reviewer,
                state.commander_id,
                pins,
            ),
            durability_finalizer=PostgresDurabilityFinalizer(
                runtime_dsn,
                standby_dsn=standby_dsn,
            ),
            durability_progress=_DevelopmentFinalizerProgressRecorder.from_persisted_state(),
        )
        stop = Event()
        signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
        signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
        worker.run(stop)


def _pack_root() -> Path:
    installed = Path(sys.prefix).parent / "packs"
    return installed if installed.is_dir() else _SOURCE_ROOT / "packs"


def _proof_policy(packs: Path) -> ProofPolicy:
    return ProofPolicy.from_bytes(
        (packs / _GATE).read_bytes(),
        (packs / _EVIDENCE).read_bytes(),
    )


def _workflow_graph(packs: Path) -> WorkflowGraph:
    payload = json.loads((packs / _WORKFLOW).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("authored Workflow pack must be an object")
    return WorkflowGraph.from_mapping(payload)


def _policy_digests(packs: Path) -> dict[str, str]:
    return {
        "ctower.trust-spine-four-stage.execution@1": _digest(packs / _EXECUTION),
        "ctower.trust-spine-four-stage.gates@1": _digest(packs / _GATE),
        "ctower.trust-spine-four-stage.evidence@1": _digest(packs / _EVIDENCE),
    }


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _enabled_oidc_providers(config: DevelopmentConfig) -> dict[str, OidcProvider]:
    return {
        provider.provider_key: OidcProvider(
            provider_key=provider.provider_key,
            issuer=provider.issuer,
            client_id=provider.client_id,
            client_secret=load_secret(provider.client_secret_ref),
            redirect_uri=provider.redirect_uri,
        )
        for provider in config.oidc_providers
        if provider.enabled
    }


def _login_attempt_signing_key(config: DevelopmentConfig) -> bytes | None:
    if config.login_attempt_signing_secret_ref is None:
        return None
    return load_secret(config.login_attempt_signing_secret_ref).encode("utf-8")


def _synthetic_revision(revisions: tuple[RoutineRevision, ...]) -> RoutineRevision:
    matches = tuple(
        revision
        for revision in revisions
        if revision.routine_ref == "ctower.i1.synthetic-four-stage@1"
    )
    if len(matches) != 1:
        raise ValueError("the exact synthetic Routine revision is unavailable")
    return matches[0]
