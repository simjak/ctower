"""Strict read-only HTTP adapter for the native morning digest."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg import Error as PsycopgError
from pydantic import ValidationError

from ctower_api._http_support import (
    UnscopedAuthentication,
    authenticate,
    encoded,
    problem_response,
    telemetry_context,
    validation_problem,
)
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import MorningDigest as HttpMorningDigest
from ctower_kernel.access import Access
from ctower_kernel.projections.morning_digest import (
    DecisionBriefFact,
    DecisionChoiceFact,
    DigestRequestFact,
    DigestRulingFact,
    SourceReading,
    UnreachedScope,
    project_morning_digest,
)
from ctower_kernel.projections.request_proposals import ProposalSummaryInput
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.request_proposals import (
    RequestMaintenanceProposalList,
    RequestProposals,
)
from ctower_kernel.work.requests import RequestList, RequestRow, Requests
from ctower_kernel.work.rulings import RulingList, Rulings

__all__: tuple[str, ...] = ()

_VILNIUS = ZoneInfo("Europe/Vilnius")


class _MorningDigestRoutes:
    def __init__(
        self,
        access: Access,
        requests: Requests,
        rulings: Rulings,
        proposals: RequestProposals | None,
        recorder: TelemetryRecorder,
    ) -> None:
        self._access = access
        self._requests = requests
        self._rulings = rulings
        self._proposals = proposals
        self._recorder = recorder

    async def get(self, request: Request, date: str | None = None) -> JSONResponse:
        actor = authenticate(
            self._access,
            self._recorder,
            request,
            required_scope=UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        if actor.kind is not PrincipalKind.OPERATOR:
            return problem_response(
                RecordProblem(
                    code="auth-role-denied",
                    detail="The morning digest is available only to the operator.",
                    status=403,
                    title="Operator role required",
                )
            )
        try:
            observed_at = dt.datetime.now(dt.UTC)
            digest_date = _digest_date(date, observed_at)
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id), actor_id=str(actor.principal_id)
            )
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        digest = project_morning_digest(
            _request_source_reading(self._requests, actor, telemetry, observed_at),
            _ruling_source_reading(self._rulings, actor, telemetry, observed_at),
            _proposal_source_reading(self._proposals, actor, telemetry, observed_at),
            digest_date=digest_date,
            observed_at=observed_at,
        )
        boundary = HttpMorningDigest.model_validate_json(encoded(digest.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))


def _request_source_reading(
    requests: Requests,
    actor: Actor,
    telemetry: TelemetryContext,
    observed_at: dt.datetime,
) -> SourceReading[DigestRequestFact]:
    try:
        outcome = requests.list(actor, telemetry=telemetry)
    except PsycopgError:
        return SourceReading.unknown(
            UnreachedScope("requests", "request-source-unavailable"),
            observed_at=observed_at,
        )
    return _request_reading(outcome, observed_at)


def _ruling_source_reading(
    rulings: Rulings,
    actor: Actor,
    telemetry: TelemetryContext,
    observed_at: dt.datetime,
) -> SourceReading[DigestRulingFact]:
    try:
        outcome = rulings.list(actor, telemetry=telemetry)
    except PsycopgError:
        return SourceReading.unknown(
            UnreachedScope("rulings", "ruling-source-unavailable"),
            observed_at=observed_at,
        )
    return _ruling_reading(outcome, observed_at)


def _proposal_source_reading(
    proposals: RequestProposals | None,
    actor: Actor,
    telemetry: TelemetryContext,
    observed_at: dt.datetime,
) -> SourceReading[ProposalSummaryInput]:
    if proposals is None:
        return SourceReading.unknown(
            UnreachedScope("request-proposals", "proposal-source-not-composed"),
            observed_at=observed_at,
        )
    try:
        outcome = proposals.list(actor, telemetry=telemetry)
    except PsycopgError:
        return SourceReading.unknown(
            UnreachedScope("request-proposals", "proposal-source-unavailable"),
            observed_at=observed_at,
        )
    return _proposal_reading(outcome, observed_at)


def _request_reading(
    outcome: RequestList | RecordProblem, observed_at: dt.datetime
) -> SourceReading[DigestRequestFact]:
    if isinstance(outcome, RecordProblem):
        return SourceReading.unknown(
            UnreachedScope("requests", outcome.code), observed_at=observed_at
        )
    rows = tuple(
        DigestRequestFact(
            request_id=row.request_id,
            request_number=row.request_number,
            project_key=row.project_key,
            state=row.state,
            required_ticket_ids=row.required_ticket_ids,
            optional_ticket_ids=row.optional_ticket_ids,
            current_proof_count=row.proof_coverage,
            decision_brief=_decision_brief(row),
        )
        for row in outcome.rows
    )
    unreached = tuple(
        UnreachedScope(project, "request-project-unanswered")
        for project in outcome.unanswered_projects
    )
    if unreached:
        return SourceReading.partial(
            rows,
            watermark=outcome.watermark,
            observed_at=outcome.observed_at,
            unreached=unreached,
        )
    return SourceReading.complete(
        rows, watermark=outcome.watermark, observed_at=outcome.observed_at
    )


def _ruling_reading(
    outcome: RulingList | RecordProblem, observed_at: dt.datetime
) -> SourceReading[DigestRulingFact]:
    if isinstance(outcome, RecordProblem):
        return SourceReading.unknown(
            UnreachedScope("rulings", outcome.code), observed_at=observed_at
        )
    rows = tuple(
        DigestRulingFact(
            ruling_id=row.ruling_id,
            project_key=row.project_key,
            verbatim=row.verbatim,
            recorded_at=row.recorded_at,
            linked_request_id=row.request_id,
        )
        for row in outcome.rows
    )
    unreached = tuple(
        UnreachedScope(project, "ruling-project-unanswered")
        for project in outcome.unanswered_projects
    )
    if unreached:
        return SourceReading.partial(
            rows,
            watermark=outcome.watermark,
            observed_at=outcome.observed_at,
            unreached=unreached,
        )
    return SourceReading.complete(
        rows, watermark=outcome.watermark, observed_at=outcome.observed_at
    )


def _proposal_reading(
    outcome: RequestMaintenanceProposalList | RecordProblem,
    observed_at: dt.datetime,
) -> SourceReading[ProposalSummaryInput]:
    if isinstance(outcome, RecordProblem):
        return SourceReading.unknown(
            UnreachedScope("request-proposals", outcome.code), observed_at=observed_at
        )
    rows = tuple(ProposalSummaryInput(row.kind, row.state) for row in outcome.rows)
    unreached = tuple(
        UnreachedScope(project, "proposal-project-unanswered")
        for project in outcome.unanswered_projects
    )
    if unreached:
        return SourceReading.partial(
            rows,
            watermark=outcome.watermark,
            observed_at=outcome.observed_at,
            unreached=unreached,
        )
    return SourceReading.complete(
        rows, watermark=outcome.watermark, observed_at=outcome.observed_at
    )


def _decision_brief(row: RequestRow) -> DecisionBriefFact | None:
    brief = row.decision_brief
    if brief is None:
        return None
    return DecisionBriefFact(
        status=brief.status,
        what=brief.eli,
        origin=brief.origin_quote,
        choices=tuple(
            DecisionChoiceFact(choice.key, choice.outcome, choice.completeness)
            for choice in brief.choices
        ),
        recommendation=(f"{brief.recommendation.choice_key}. {brief.recommendation.reason}"),
        safe_default=f"{brief.safe_default.choice_key}. {brief.safe_default.reason}",
    )


def install_morning_digest_routes(
    app: FastAPI,
    access: Access,
    requests: Requests,
    rulings: Rulings,
    proposals: RequestProposals | None,
    recorder: TelemetryRecorder,
) -> None:
    routes = _MorningDigestRoutes(
        access,
        requests,
        rulings,
        proposals,
        recorder,
    )
    app.add_api_route("/v1/digests/morning", routes.get, methods=["GET"])


def _digest_date(value: str | None, observed_at: dt.datetime) -> dt.date:
    if value is None:
        return observed_at.astimezone(_VILNIUS).date()
    parsed = dt.date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("digest date must be an RFC 3339 full-date")
    return parsed
