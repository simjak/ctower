"""Authenticated HTTP adapters for harness credential-pool limits (T4).

The write verb is the seam's `writeback` in its first real use: an adapter records what it
observed about the credential pool it runs on, under its own seat credential, and the
request schema is the projection allowlist — a closed object whose fields cannot name a
token, key, or any adjacent secret value.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

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
from ctower_client.models import PoolLimitsView as HttpPoolLimitsView
from ctower_client.models import PoolObservationRequest, PoolObservedEntry
from ctower_client.models import PoolObservationResult as HttpPoolObservationResult
from ctower_kernel.access import Access
from ctower_kernel.pools import PoolObservationCommand, Pools
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.record.pool_events import PoolObservationEntryPayload

__all__: tuple[str, ...] = ()


def install_pool_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    pools: Pools,
    recorder: TelemetryRecorder,
) -> None:
    """Install the seat-credentialed observation write and the authenticated limits read."""

    _install_observation_route(app, access, record, pools, recorder)
    _install_limits_route(app, access, pools, recorder)


def _install_observation_route(
    app: FastAPI,
    access: Access,
    record: Record,
    pools: Pools,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/pools/observations", status_code=202)
    async def record_pool_observation(request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request, required_scope=CredentialScope.CAPTURE)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            payload = PoolObservationRequest.model_validate_json(await request.body())
            command = PoolObservationCommand(
                client_command_id=command_id,
                harness_key=payload.harness_key,
                profile_key=payload.profile_key,
                observed_at=payload.observed_at,
                entries=tuple(_entry(index, item) for index, item in enumerate(payload.entries)),
            )
        except (ValidationError, TypeError, ValueError):
            return problem_response(validation_problem())
        telemetry = telemetry_context(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = pools.record_observation(actor, command)
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpPoolObservationResult,
            accepted_status=202,
        )


def _install_limits_route(
    app: FastAPI,
    access: Access,
    pools: Pools,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/pools")
    def read_pool_limits(request: Request, *, profile_key: str | None = None) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        outcome = pools.read_limits(actor, profile_key)
        if isinstance(outcome, RecordProblem):
            return problem_response(outcome)
        boundary = HttpPoolLimitsView.model_validate_json(encoded(outcome.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))


def _entry(index: int, item: PoolObservedEntry) -> PoolObservationEntryPayload:
    """Project one wire entry into the record-tier allowlist, field by named field.

    Named-field projection is the point: copying the object would be the failure this
    allowlist exists to prevent, and there is no field here a credential value can enter.
    """

    return PoolObservationEntryPayload(
        entry_ordinal=index,
        provider_key=item.provider_key,
        subscription_identity=item.subscription_identity,
        entry_label=item.entry_label,
        registration_state=item.registration_state,
        auth_state=item.auth_state,
        quota_state=item.quota_state,
        quota_reset_at=item.quota_reset_at,
        reach_state=item.reach_state,
        request_count=item.request_count,
        last_status_observed=item.last_status_observed,
        secret_fingerprint=item.secret_fingerprint,
    )
