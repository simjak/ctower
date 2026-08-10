"""One-way operator-authenticated Request import and reconciliation authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.artifacts import ArtifactError
from ctower_kernel.record.transaction import authority_connection, recover_ambiguous_commit
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext
from ctower_kernel.work._request_cutover_artifacts import (
    load_reviewer_key,
    validate_fence,
    validate_manifest,
    validate_manifest_key,
    verify_request_artifact,
)
from ctower_kernel.work._request_cutover_common_sql import (
    human_operator_refusal,
    load_manifest,
    target_authority_inventory,
)
from ctower_kernel.work._request_cutover_complete_sql import complete_cutover
from ctower_kernel.work._request_cutover_import_sql import import_request_row
from ctower_kernel.work._request_cutover_prepare_sql import prepare_cutover
from ctower_kernel.work._request_cutover_proof_sql import record_batch_proof
from ctower_kernel.work._request_cutover_reconcile_sql import reconcile_import_batch
from ctower_kernel.work._request_cutover_types import (
    RequestBatchProof,
    RequestCutoverComplete,
    RequestCutoverImport,
    RequestCutoverPrepare,
    RequestCutoverResult,
    RequestImportReconciliation,
)

__all__ = [
    "PostgresRequestCutover",
    "RequestBatchProof",
    "RequestCutover",
    "RequestCutoverComplete",
    "RequestCutoverImport",
    "RequestCutoverPrepare",
    "RequestCutoverResult",
    "RequestImportReconciliation",
]

_MANIFEST_SCHEMA = "ctower.request-import-manifest/v1"
_FENCE_SCHEMA = "ctower.request-source-fence/v1"
_PROOF_SCHEMA = "ctower.request-batch-proof/v1"


class _RequestCutoverStore(Protocol):
    def authority_inventory(self, actor: Actor) -> dict[str, object] | RecordProblem: ...

    def manifest(self, actor: Actor, digest: str) -> dict[str, Any] | RecordProblem: ...

    def prepare(
        self,
        actor: Actor,
        command: RequestCutoverPrepare,
        *,
        manifest: dict[str, Any],
        fence: dict[str, Any],
        public_key_digest: str,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCutoverResult | RecordProblem: ...

    def import_row(
        self,
        actor: Actor,
        command: RequestCutoverImport,
        *,
        manifest: dict[str, Any],
        fence: dict[str, Any],
        public_key_digest: str,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCutoverResult | RecordProblem: ...

    def reconcile(
        self, actor: Actor, manifest: dict[str, Any], *, digest: str, batch_index: int
    ) -> RequestImportReconciliation | RecordProblem: ...

    def record_proof(
        self,
        actor: Actor,
        command: RequestBatchProof,
        *,
        proof: dict[str, Any],
        reconciliation: RequestImportReconciliation,
        public_key_digest: str,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCutoverResult | RecordProblem: ...

    def complete(
        self,
        actor: Actor,
        command: RequestCutoverComplete,
        *,
        manifest: dict[str, Any],
        final_fence: dict[str, Any],
        public_key_digest: str,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCutoverResult | RecordProblem: ...


class RequestCutover:
    """Verify signed source evidence before any target authority write."""

    def __init__(
        self,
        store: _RequestCutoverStore,
        *,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    def authority_inventory(self, actor: Actor) -> dict[str, object] | RecordProblem:
        return self._store.authority_inventory(actor)

    def prepare(
        self, actor: Actor, command: RequestCutoverPrepare, *, telemetry: TelemetryContext
    ) -> RequestCutoverResult | RecordProblem:
        now = self._clock()
        try:
            key, key_digest = load_reviewer_key(command.reviewer_public_key_pem)
            fence, _ = verify_request_artifact(command.fence, _FENCE_SCHEMA, "fence_digest", key)
            manifest, _ = verify_request_artifact(
                command.manifest, _MANIFEST_SCHEMA, "manifest_digest", key
            )
            validate_manifest(manifest, fence, key_digest=key_digest)
            validate_fence(fence, manifest, now=now, phases={"freeze"})
        except (ArtifactError, TypeError, ValueError) as error:
            return _artifact_problem(command.client_command_id, error)
        outcome = self._store.prepare(
            actor,
            command,
            manifest=manifest,
            fence=fence,
            public_key_digest=key_digest,
            request_digest=_request_digest(command.request_payload()),
            now=now,
            telemetry=telemetry,
        )
        self._emit("work.request_cutover.prepare", telemetry, outcome)
        return outcome

    def import_row(
        self, actor: Actor, command: RequestCutoverImport, *, telemetry: TelemetryContext
    ) -> RequestCutoverResult | RecordProblem:
        now = self._clock()
        manifest = self._store.manifest(actor, command.manifest_digest)
        if isinstance(manifest, RecordProblem):
            return manifest
        try:
            key, key_digest = load_reviewer_key(command.reviewer_public_key_pem)
            validate_manifest_key(manifest, key_digest)
            fence, _ = verify_request_artifact(command.fence, _FENCE_SCHEMA, "fence_digest", key)
            validate_fence(fence, manifest, now=now, phases={"freeze", "batch"})
        except (ArtifactError, TypeError, ValueError) as error:
            return _artifact_problem(command.client_command_id, error)
        outcome = self._store.import_row(
            actor,
            command,
            manifest=manifest,
            fence=fence,
            public_key_digest=key_digest,
            request_digest=_request_digest(command.request_payload()),
            now=now,
            telemetry=telemetry,
        )
        self._emit("work.request_cutover.import", telemetry, outcome)
        return outcome

    def reconcile(
        self, actor: Actor, manifest_digest: str, batch_index: int
    ) -> RequestImportReconciliation | RecordProblem:
        manifest = self._store.manifest(actor, manifest_digest)
        if isinstance(manifest, RecordProblem):
            return manifest
        return self._store.reconcile(
            actor, manifest, digest=manifest_digest, batch_index=batch_index
        )

    def record_batch_proof(
        self, actor: Actor, command: RequestBatchProof, *, telemetry: TelemetryContext
    ) -> RequestCutoverResult | RecordProblem:
        now = self._clock()
        try:
            key, key_digest = load_reviewer_key(command.reviewer_public_key_pem)
            proof, _ = verify_request_artifact(command.proof, _PROOF_SCHEMA, "proof_digest", key)
        except (ArtifactError, TypeError, ValueError) as error:
            return _artifact_problem(command.client_command_id, error)
        manifest_digest = cast(str, proof["manifest_digest"])
        manifest = self._store.manifest(actor, manifest_digest)
        if isinstance(manifest, RecordProblem):
            return manifest
        try:
            validate_manifest_key(manifest, key_digest)
        except ValueError as error:
            return _artifact_problem(command.client_command_id, error)
        reconciliation = self._store.reconcile(
            actor,
            manifest,
            digest=manifest_digest,
            batch_index=cast(int, proof["batch_index"]),
        )
        if isinstance(reconciliation, RecordProblem):
            return reconciliation
        outcome = self._store.record_proof(
            actor,
            command,
            proof=proof,
            reconciliation=reconciliation,
            public_key_digest=key_digest,
            request_digest=_request_digest(command.request_payload()),
            now=now,
            telemetry=telemetry,
        )
        self._emit("work.request_cutover.reconcile", telemetry, outcome)
        return outcome

    def complete(
        self, actor: Actor, command: RequestCutoverComplete, *, telemetry: TelemetryContext
    ) -> RequestCutoverResult | RecordProblem:
        now = self._clock()
        manifest = self._store.manifest(actor, command.manifest_digest)
        if isinstance(manifest, RecordProblem):
            return manifest
        try:
            key, key_digest = load_reviewer_key(command.reviewer_public_key_pem)
            validate_manifest_key(manifest, key_digest)
            fence, _ = verify_request_artifact(
                command.final_fence, _FENCE_SCHEMA, "fence_digest", key
            )
            validate_fence(fence, manifest, now=now, phases={"final"})
        except (ArtifactError, TypeError, ValueError) as error:
            return _artifact_problem(command.client_command_id, error)
        outcome = self._store.complete(
            actor,
            command,
            manifest=manifest,
            final_fence=fence,
            public_key_digest=key_digest,
            request_digest=_request_digest(command.request_payload()),
            now=now,
            telemetry=telemetry,
        )
        self._emit("work.request_cutover.complete", telemetry, outcome)
        return outcome

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: RequestCutoverResult | RecordProblem,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else outcome.state,
        )


class PostgresRequestCutover:
    """Store Request cutover facts through the existing bounded Record transaction."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def authority_inventory(self, actor: Actor) -> dict[str, object] | RecordProblem:
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            problem = human_operator_refusal(connection, actor, UUID(int=0))
            return problem or target_authority_inventory(connection, actor.tenant_id)

    def manifest(self, actor: Actor, digest: str) -> dict[str, Any] | RecordProblem:
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            problem = human_operator_refusal(connection, actor, UUID(int=0))
            if problem is not None:
                return problem
            manifest = load_manifest(connection, actor, digest)
            if manifest is not None:
                return manifest
        return RecordProblem(
            code="request-import-forbidden",
            detail="The Request import operation is absent outside its exact prepared epoch.",
            status=404,
            title="Request import unavailable",
        )

    def prepare(
        self,
        actor: Actor,
        command: RequestCutoverPrepare,
        *,
        manifest: dict[str, Any],
        fence: dict[str, Any],
        public_key_digest: str,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCutoverResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: prepare_cutover(
                self._dsn,
                actor,
                command,
                manifest=manifest,
                fence=fence,
                public_key_digest=public_key_digest,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )

    def import_row(
        self,
        actor: Actor,
        command: RequestCutoverImport,
        *,
        manifest: dict[str, Any],
        fence: dict[str, Any],
        public_key_digest: str,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCutoverResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: import_request_row(
                self._dsn,
                actor,
                command,
                manifest=manifest,
                fence=fence,
                public_key_digest=public_key_digest,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )

    def reconcile(
        self, actor: Actor, manifest: dict[str, Any], *, digest: str, batch_index: int
    ) -> RequestImportReconciliation | RecordProblem:
        return reconcile_import_batch(
            self._dsn, actor, manifest, manifest_digest=digest, batch_index=batch_index
        )

    def record_proof(
        self,
        actor: Actor,
        command: RequestBatchProof,
        *,
        proof: dict[str, Any],
        reconciliation: RequestImportReconciliation,
        public_key_digest: str,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCutoverResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: record_batch_proof(
                self._dsn,
                actor,
                command,
                proof=proof,
                reconciliation=reconciliation,
                public_key_digest=public_key_digest,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )

    def complete(
        self,
        actor: Actor,
        command: RequestCutoverComplete,
        *,
        manifest: dict[str, Any],
        final_fence: dict[str, Any],
        public_key_digest: str,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RequestCutoverResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: complete_cutover(
                self._dsn,
                actor,
                command,
                manifest=manifest,
                final_fence=final_fence,
                public_key_digest=public_key_digest,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )


def _request_digest(payload: Mapping[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).digest()


def _artifact_problem(command_id: UUID, error: Exception) -> RecordProblem:
    signature = isinstance(error, ArtifactError) and "key" in str(error)
    return RecordProblem(
        code="migration-signature-invalid" if signature else "migration-digest-mismatch",
        detail=(
            "The Request cutover artifact is invalid or no longer bound to this operation: "
            f"{error}."
        ),
        status=409,
        title="Request cutover artifact refused",
        command_id=command_id,
    )
