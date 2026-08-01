"""Deep Access Module for trust-root authentication and authorization."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from uuid import UUID

from ctower_kernel.record import (
    Actor,
    BootstrapCommand,
    BootstrapReceipt,
    PrincipalKind,
    Record,
    RecordProblem,
)
from ctower_kernel.record.credentials import (
    CredentialScope,
    SeatCredentialIssue,
    SeatCredentialReceipt,
    SeatCredentialRevocation,
)
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__ = ["Access", "credential_scope_refusal", "digest_capability"]


class Access:
    """Authenticate bootstrap transport authority before invoking Record."""

    def __init__(
        self,
        record: Record,
        *,
        importer_resolver: Callable[[bytes, UUID, UUID, str, datetime], Actor | None] | None = None,
        importer_credential_resolver: Callable[[bytes, datetime], Actor | None] | None = None,
        fence_observer_resolver: Callable[[bytes, datetime], Actor | None] | None = None,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._record = record
        self._importer_resolver = importer_resolver
        self._importer_credential_resolver = importer_credential_resolver
        self._fence_observer_resolver = fence_observer_resolver
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    def bootstrap_first_tenant(
        self,
        command: BootstrapCommand,
        *,
        capability: str,
        origin: str,
        telemetry: TelemetryContext,
    ) -> BootstrapReceipt | RecordProblem:
        """Refuse non-loopback origins and pass only digests into Record."""

        if not _is_loopback(origin):
            return RecordProblem(
                code="bootstrap-origin",
                detail="The first-tenant route accepts only its configured local origin.",
                status=403,
                title="Bootstrap origin refused",
                command_id=command.client_command_id,
            )
        request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        outcome = self._record.bootstrap_first_tenant(
            command,
            capability_digest=digest_capability(capability),
            request_digest=request_digest,
            origin=origin,
            now=self._clock(),
            telemetry=telemetry,
        )
        self._telemetry.emit(
            "access.bootstrap_first_tenant",
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )
        return outcome

    def authorize_bootstrap(self, capability: str | None, *, origin: str) -> RecordProblem | None:
        """Authorize raw origin and capability before transport payload validation."""

        if not _is_loopback(origin):
            return RecordProblem(
                code="bootstrap-origin",
                detail="The first-tenant route accepts only its configured local origin.",
                status=403,
                title="Bootstrap origin refused",
            )
        if capability is None:
            return _unauthorized()
        return self._record.authorize_bootstrap(
            digest_capability(capability), origin=origin, now=self._clock()
        )

    def authenticate(self, authorization: str | None) -> Actor | RecordProblem:
        """Resolve one opaque bearer credential without retaining plaintext."""

        prefix = "Bearer "
        if authorization is None or not authorization.startswith(prefix):
            return _unauthorized()
        credential = authorization.removeprefix(prefix)
        if not credential or credential.strip() != credential:
            return _unauthorized()
        actor = self._record.actor_for_credential(hashlib.sha256(credential.encode()).digest())
        return actor if actor is not None else _unauthorized()

    def authorize_scope(
        self,
        actor: Actor,
        scope: CredentialScope,
        *,
        command_id: UUID | None = None,
    ) -> RecordProblem | None:
        """Require a named mutation scope only for an issued seat bearer."""

        return credential_scope_refusal(actor, scope, command_id=command_id)

    def issue_seat_credential(
        self,
        actor: Actor,
        command: SeatCredentialIssue,
        *,
        telemetry: TelemetryContext,
    ) -> SeatCredentialReceipt | RecordProblem:
        """Allow only the tenant operator to append a secret-free issuance."""

        if actor.kind is not PrincipalKind.OPERATOR:
            return RecordProblem(
                code="credential-issuance-refused",
                detail="Seat credential issuance requires operator authority.",
                status=403,
                title="Seat credential issuance refused",
                command_id=command.client_command_id,
            )
        request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        outcome = self._record.seat_credentials.issue(
            actor,
            command,
            request_digest=request_digest,
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit("access.issue_seat_credential", telemetry, outcome)
        return outcome

    def revoke_seat_credential(
        self,
        actor: Actor,
        command: SeatCredentialRevocation,
        *,
        telemetry: TelemetryContext,
    ) -> SeatCredentialReceipt | RecordProblem:
        """Allow only the tenant operator to append one revocation."""

        if actor.kind is not PrincipalKind.OPERATOR:
            return RecordProblem(
                code="credential-revocation-refused",
                detail="Seat credential revocation requires operator authority.",
                status=403,
                title="Seat credential revocation refused",
                command_id=command.client_command_id,
            )
        request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        outcome = self._record.seat_credentials.revoke(
            actor,
            command,
            request_digest=request_digest,
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit("access.revoke_seat_credential", telemetry, outcome)
        return outcome

    def authenticate_importer(
        self,
        authorization: str | None,
        *,
        run_id: UUID,
        cutover_id: UUID,
        project_key: str,
    ) -> Actor | RecordProblem:
        """Resolve one bearer only when its immutable import scope matches exactly."""

        credential = _bearer(authorization)
        if credential is None or self._importer_resolver is None:
            return _unauthorized()
        actor = self._importer_resolver(
            hashlib.sha256(credential.encode()).digest(),
            run_id,
            cutover_id,
            project_key,
            self._clock(),
        )
        return actor if actor is not None else _unauthorized()

    def authenticate_importer_credential(
        self,
        authorization: str | None,
    ) -> Actor | RecordProblem:
        """Authenticate the bounded importer bearer before parsing its scope DTO."""

        credential = _bearer(authorization)
        if credential is None or self._importer_credential_resolver is None:
            return _unauthorized()
        actor = self._importer_credential_resolver(
            hashlib.sha256(credential.encode()).digest(),
            self._clock(),
        )
        return actor if actor is not None else _unauthorized()

    def authenticate_fence_observer(
        self,
        authorization: str | None,
    ) -> Actor | RecordProblem:
        """Resolve only a separately bound, active fence-observer bearer."""

        credential = _bearer(authorization)
        if credential is None or self._fence_observer_resolver is None:
            return _unauthorized()
        actor = self._fence_observer_resolver(
            hashlib.sha256(credential.encode()).digest(),
            self._clock(),
        )
        return actor if actor is not None else _unauthorized()

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: SeatCredentialReceipt | RecordProblem,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )


def digest_capability(capability: str) -> bytes:
    """Reduce plaintext bootstrap authority to its one-way Record representation."""

    return hashlib.sha256(capability.encode()).digest()


def _is_loopback(origin: str) -> bool:
    try:
        return ipaddress.ip_address(origin).is_loopback
    except ValueError:
        return False


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    """Encode the string-only bootstrap contract in RFC 8785 canonical order."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def credential_scope_refusal(
    actor: Actor,
    scope: CredentialScope,
    *,
    command_id: UUID | None = None,
) -> RecordProblem | None:
    """Return the stable refusal for a seat bearer missing one named scope."""

    if actor.seat_credential_id is None or scope in actor.credential_scopes:
        return None
    return RecordProblem(
        code="credential-scope-denied",
        detail=f"The project-seat credential does not grant the {scope.value} scope.",
        status=403,
        title="Credential scope denied",
        command_id=command_id,
    )


def _unauthorized() -> RecordProblem:
    return RecordProblem(
        code="unauthorized",
        detail="A valid tenant credential is required.",
        status=401,
        title="Authentication refused",
    )


def _bearer(authorization: str | None) -> str | None:
    prefix = "Bearer "
    if authorization is None or not authorization.startswith(prefix):
        return None
    credential = authorization.removeprefix(prefix)
    return credential if credential and credential.strip() == credential else None
