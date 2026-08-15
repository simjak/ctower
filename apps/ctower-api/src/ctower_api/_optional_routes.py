"""Optional HTTP route composition for the control API."""

from __future__ import annotations

from fastapi import FastAPI

from ctower_api._attention_finding_routes import install_attention_finding_routes
from ctower_api._board_context_routes import install_board_context_routes
from ctower_api._board_routes import install_board_routes
from ctower_api._catalog_routes import BundleCatalog, install_catalog_routes
from ctower_api._estate_import_routes import install_estate_import_routes
from ctower_api._health_routes import install_health_routes
from ctower_api._inbox_routes import install_inbox_routes
from ctower_api._knowledge_routes import install_knowledge_routes
from ctower_api._proof_workflow_routes import install_proof_workflow_routes
from ctower_api.estate_import_port import EstateImportPort
from ctower_api.telemetry import TelemetryRecorder
from ctower_kernel.access import Access
from ctower_kernel.attention import Attention
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.inbox import Inbox
from ctower_kernel.knowledge import Knowledge
from ctower_kernel.projections import Projections
from ctower_kernel.proof import Proof
from ctower_kernel.record import Record
from ctower_kernel.workflow import Workflow


def install_optional_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    *,
    proof: Proof | None,
    workflow: Workflow | None,
    projections: Projections | None,
    attention: Attention | None,
    board_context: BoardContextFacts | None,
    inbox: Inbox | None,
    knowledge: Knowledge | None,
    estate_imports: EstateImportPort | None,
    catalog: BundleCatalog | None,
    recorder: TelemetryRecorder,
) -> None:
    _install_primary_routes(
        app,
        access,
        record,
        proof=proof,
        workflow=workflow,
        board_context=board_context,
        attention=attention,
        catalog=catalog,
        recorder=recorder,
    )
    _install_projection_routes(
        app,
        access,
        record,
        projections=projections,
        attention=attention,
        inbox=inbox,
        knowledge=knowledge,
        estate_imports=estate_imports,
        recorder=recorder,
    )


def _install_primary_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    *,
    proof: Proof | None,
    workflow: Workflow | None,
    board_context: BoardContextFacts | None,
    attention: Attention | None,
    catalog: BundleCatalog | None,
    recorder: TelemetryRecorder,
) -> None:
    if catalog is not None:
        install_catalog_routes(app, access, record, catalog, recorder)
    if proof is not None and workflow is not None:
        install_proof_workflow_routes(app, access, record, proof, workflow, recorder)
    if board_context is not None:
        install_board_context_routes(app, access, record, board_context, recorder)
    if attention is not None:
        install_attention_finding_routes(app, access, record, attention, recorder)


def _install_projection_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    *,
    projections: Projections | None,
    attention: Attention | None,
    inbox: Inbox | None,
    knowledge: Knowledge | None,
    estate_imports: EstateImportPort | None,
    recorder: TelemetryRecorder,
) -> None:
    if projections is not None:
        install_board_routes(app, access, projections, recorder)
        install_health_routes(app, access, record, projections, recorder, attention)
    if inbox is not None and projections is not None:
        install_inbox_routes(app, access, record, inbox, projections, recorder)
    if knowledge is not None:
        install_knowledge_routes(app, access, record, knowledge, recorder)
    if estate_imports is not None:
        install_estate_import_routes(app, access, record, estate_imports, recorder)
