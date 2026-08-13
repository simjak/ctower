"""Strict HTTP composition for Request-maintenance proposal facts and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from ctower_api._catalog_routes import BundleCatalog
from ctower_api._http_support import (
    UnscopedAuthentication,
    authenticate,
    encoded,
    problem_response,
    telemetry_context,
    uuid_value,
    validation_problem,
)
from ctower_api._mutation_response import mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    RequestMaintenanceProposalAppendRequest,
    RequestMaintenanceProposalAppendResult,
    RequestMaintenanceProposalConfirmRequest,
    RequestMaintenanceProposalDecisionResult,
    RequestMaintenanceProposalList,
    RequestMaintenanceProposalRejectRequest,
    RequestMaintenanceReview,
    RequestProposalProofEvidence,
    RequestProposalRecordEventEvidence,
)
from ctower_kernel.access import Access
from ctower_kernel.catalog import CatalogProblem, CompanyBundleExport
from ctower_kernel.catalog.interface import CompanyBundleResource, ComponentKind
from ctower_kernel.projections.request_proposals import (
    ProposalReviewInput,
    derive_request_maintenance_review,
)
from ctower_kernel.record import Actor, PrincipalKind, Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.request_proposals import (
    ProofEvidencePointer,
    RecordEventEvidencePointer,
    RequestMaintenanceProposalAppend,
    RequestMaintenanceProposalConfirm,
    RequestMaintenanceProposalReject,
    RequestProposals,
)
from ctower_kernel.work.request_proposals import (
    RequestMaintenanceProposalAppendResult as SemanticAppendResult,
)
from ctower_kernel.work.request_proposals import (
    RequestMaintenanceProposalDecisionResult as SemanticDecisionResult,
)
from ctower_kernel.work.requests import RequestList, RequestRow, Requests

__all__: tuple[str, ...] = ()
_BODY_LIMIT = 128 * 1024
type _MutationOutcome = SemanticAppendResult | SemanticDecisionResult | RecordProblem


@dataclass(frozen=True, slots=True)
class _ParsedMutation:
    actor: Actor
    command_id: UUID
    payload: BaseModel
    telemetry: TelemetryContext


class _RequestProposalRoutes:
    def __init__(
        self,
        access: Access,
        record: Record,
        proposals: RequestProposals,
        requests: Requests,
        catalog: BundleCatalog | None,
        recorder: TelemetryRecorder,
    ) -> None:
        self._access = access
        self._record = record
        self._proposals = proposals
        self._requests = requests
        self._catalog = catalog
        self._recorder = recorder

    async def append(self, request: Request) -> JSONResponse:
        parsed = await self._mutation(request, RequestMaintenanceProposalAppendRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        payload = parsed.payload
        if not isinstance(payload, RequestMaintenanceProposalAppendRequest):
            raise TypeError("proposal append parser returned the wrong boundary")
        outcome = self._proposals.append(
            parsed.actor,
            RequestMaintenanceProposalAppend(
                client_command_id=parsed.command_id,
                project_key=payload.project_key,
                kind=payload.kind.value,
                basis=payload.basis,
                target_request_id=payload.target_request_id,
                target_expected_version=payload.target_expected_version,
                target_text=payload.target_text,
                source_record_position=payload.source_record_position,
                evidence=tuple(_evidence(item) for item in payload.evidence),
                related_request_id=payload.related_request_id,
                related_expected_version=payload.related_expected_version,
                related_text=payload.related_text,
                ambiguity_reason=(
                    None if payload.ambiguity_reason is None else payload.ambiguity_reason.value
                ),
            ),
            telemetry=parsed.telemetry,
        )
        return self._response(parsed, outcome, RequestMaintenanceProposalAppendResult, 201)

    async def list(
        self,
        request: Request,
        proposal_id: str | None = None,
        project_key: str | None = None,
        kind: str | None = None,
        state: str | None = None,
    ) -> JSONResponse:
        authenticated = self._authenticated(request)
        if isinstance(authenticated, JSONResponse):
            return authenticated
        actor, telemetry = authenticated
        try:
            parsed_id = None if proposal_id is None else uuid_value(proposal_id)
        except ValueError:
            return problem_response(validation_problem())
        outcome = self._proposals.list(
            actor,
            proposal_id=parsed_id,
            project_key=project_key,
            kind=kind,
            state=state,
            telemetry=telemetry,
        )
        if isinstance(outcome, RecordProblem):
            return problem_response(outcome)
        return _boundary_response(RequestMaintenanceProposalList, outcome.response_payload())

    async def review(self, request: Request) -> JSONResponse:
        authenticated = self._authenticated(request)
        if isinstance(authenticated, JSONResponse):
            return authenticated
        actor, telemetry = authenticated
        if actor.kind is not PrincipalKind.OPERATOR:
            return problem_response(_operator_problem())
        proposals = self._proposals.list(actor, telemetry=telemetry)
        if isinstance(proposals, RecordProblem):
            return problem_response(proposals)
        requests = self._requests.list(actor, telemetry=telemetry)
        request_rows, request_watermark, unanswered = _request_reading(requests)
        relevance, catalog_unanswered = _goal_relevance(self._catalog, actor)
        inputs: list[ProposalReviewInput] = []
        unreadable_targets: set[str] = set()
        for row in proposals.rows:
            if row.state != "OPEN":
                continue
            target = request_rows.get(row.target_request_id)
            if target is None or target.unknown_reason is not None:
                unreadable_targets.add(f"request-state-unreadable:{row.target_request_id}")
                continue
            if target.state == "DONE":
                continue
            inputs.append(
                ProposalReviewInput(
                    request_id=row.target_request_id,
                    proposal_id=row.proposal_id,
                    goal_relevance=relevance.get(row.project_key, "unknown"),
                    operator_decision_required=_operator_required(target),
                    created_at=target.created_at,
                )
            )
        review = derive_request_maintenance_review(
            inputs,
            watermark=max(proposals.watermark, request_watermark),
            unanswered_sources=tuple(
                sorted(
                    set(unanswered)
                    | set(catalog_unanswered)
                    | unreadable_targets
                    | {f"proposal-project:{key}" for key in proposals.unanswered_projects}
                )
            ),
        )
        return _boundary_response(RequestMaintenanceReview, review.response_payload())

    async def confirm(self, request: Request, proposal_id: str) -> JSONResponse:
        parsed = await self._mutation(request, RequestMaintenanceProposalConfirmRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        try:
            identity = uuid_value(proposal_id)
        except ValueError:
            return problem_response(validation_problem())
        payload = parsed.payload
        if not isinstance(payload, RequestMaintenanceProposalConfirmRequest):
            raise TypeError("proposal confirm parser returned the wrong boundary")
        outcome = self._proposals.confirm(
            parsed.actor,
            RequestMaintenanceProposalConfirm(
                parsed.command_id, identity, payload.expected_proposal_version
            ),
            telemetry=parsed.telemetry,
        )
        return self._response(parsed, outcome, RequestMaintenanceProposalDecisionResult, 200)

    async def reject(self, request: Request, proposal_id: str) -> JSONResponse:
        parsed = await self._mutation(request, RequestMaintenanceProposalRejectRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        try:
            identity = uuid_value(proposal_id)
        except ValueError:
            return problem_response(validation_problem())
        payload = parsed.payload
        if not isinstance(payload, RequestMaintenanceProposalRejectRequest):
            raise TypeError("proposal reject parser returned the wrong boundary")
        outcome = self._proposals.reject(
            parsed.actor,
            RequestMaintenanceProposalReject(
                parsed.command_id, identity, payload.expected_proposal_version, payload.reason
            ),
            telemetry=parsed.telemetry,
        )
        return self._response(parsed, outcome, RequestMaintenanceProposalDecisionResult, 200)

    async def _mutation(
        self, request: Request, boundary: type[BaseModel]
    ) -> _ParsedMutation | JSONResponse:
        actor = authenticate(
            self._access,
            self._recorder,
            request,
            required_scope=CredentialScope.TRANSITION,
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
            payload = boundary.model_validate_json(await _bounded_body(request))
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        self._recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        return _ParsedMutation(actor, command_id, payload, telemetry)

    def _authenticated(self, request: Request) -> tuple[Actor, TelemetryContext] | JSONResponse:
        actor = authenticate(
            self._access,
            self._recorder,
            request,
            required_scope=UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id), actor_id=str(actor.principal_id)
            )
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        return actor, telemetry

    def _response(
        self,
        parsed: _ParsedMutation,
        outcome: _MutationOutcome,
        boundary: type[BaseModel],
        accepted_status: int,
    ) -> JSONResponse:
        return mutation_response(
            self._record,
            outcome,
            tenant_id=parsed.actor.tenant_id,
            principal_id=parsed.actor.principal_id,
            command_id=parsed.command_id,
            telemetry=parsed.telemetry,
            boundary_model=boundary,
            accepted_status=accepted_status,
        )


def _evidence(
    item: RequestProposalRecordEventEvidence | RequestProposalProofEvidence,
) -> RecordEventEvidencePointer | ProofEvidencePointer:
    if isinstance(item, RequestProposalRecordEventEvidence):
        return RecordEventEvidencePointer(item.event_id, item.event_kind, item.event_digest)
    return ProofEvidencePointer(
        item.ticket_id, item.proof_id, item.evidence_id, item.artifact_digest
    )


def _request_reading(
    outcome: RequestList | RecordProblem,
) -> tuple[dict[UUID, RequestRow], int, tuple[str, ...]]:
    if isinstance(outcome, RecordProblem):
        return {}, 0, (f"requests:{outcome.code}",)
    return (
        {row.request_id: row for row in outcome.rows},
        outcome.watermark,
        tuple(f"request-project:{key}" for key in outcome.unanswered_projects),
    )


def _operator_required(row: RequestRow | None) -> bool:
    return (
        row is not None and row.decision_brief is not None and row.decision_brief.status == "open"
    )


def _goal_relevance(
    catalog: BundleCatalog | None, actor: Actor
) -> tuple[dict[str, str], tuple[str, ...]]:
    if catalog is None:
        return {}, ("catalog:not-composed",)
    outcome = catalog.export(actor)
    if isinstance(outcome, CatalogProblem):
        return {}, (f"catalog:{outcome.code}",)
    return _bundle_goal_relevance(outcome)


def _bundle_goal_relevance(
    export: CompanyBundleExport,
) -> tuple[dict[str, str], tuple[str, ...]]:
    goals = tuple(
        item
        for item in export.bundle.resources
        if item.component.kind is ComponentKind.GOAL and item.component.scope.project is None
    )
    if len(goals) != 1:
        return {}, ("catalog:active-goal-ambiguous",)
    goal_ref = f"{goals[0].component.key}@{goals[0].component.revision}"
    relevance: dict[str, str] = {}
    invalid = False
    for item in export.bundle.resources:
        if item.component.kind is not ComponentKind.PROJECT:
            continue
        entry = _project_goal_entry(item, goal_ref)
        if entry is None:
            invalid = True
            continue
        key, state = entry
        if key in relevance:
            relevance.pop(key, None)
            invalid = True
            continue
        relevance[key] = state
    return relevance, (("catalog:project-goal-unreadable",) if invalid else ())


def _project_goal_entry(item: CompanyBundleResource, goal_ref: str) -> tuple[str, str] | None:
    key = item.payload.get("key")
    refs = item.payload.get("goal_refs")
    if (
        not isinstance(key, str)
        or not isinstance(refs, list)
        or not all(isinstance(ref, str) for ref in refs)
    ):
        return None
    return key, "relevant" if goal_ref in refs else "not-relevant"


def _boundary_response(boundary: type[BaseModel], payload: dict[str, object]) -> JSONResponse:
    parsed = boundary.model_validate_json(encoded(payload))
    return JSONResponse(content=parsed.model_dump(mode="json", by_alias=True))


async def _bounded_body(request: Request) -> bytes:
    body = await request.body()
    if len(body) > _BODY_LIMIT:
        raise ValueError("proposal request body exceeds bounded envelope")
    return body


def _operator_problem() -> RecordProblem:
    return RecordProblem(
        code="auth-role-denied",
        detail="Request-maintenance review is available only to the operator.",
        status=403,
        title="Operator role required",
    )


def install_request_proposal_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    proposals: RequestProposals,
    requests: Requests,
    catalog: BundleCatalog | None,
    recorder: TelemetryRecorder,
) -> None:
    routes = _RequestProposalRoutes(access, record, proposals, requests, catalog, recorder)
    app.add_api_route("/v1/request-maintenance/proposals", routes.append, methods=["POST"])
    app.add_api_route("/v1/request-maintenance/proposals", routes.list, methods=["GET"])
    app.add_api_route("/v1/request-maintenance/review", routes.review, methods=["GET"])
    app.add_api_route(
        "/v1/request-maintenance/proposals/{proposal_id}/confirm",
        routes.confirm,
        methods=["POST"],
    )
    app.add_api_route(
        "/v1/request-maintenance/proposals/{proposal_id}/reject",
        routes.reject,
        methods=["POST"],
    )
