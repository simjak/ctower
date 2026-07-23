"""Postgres implementation behind the Proof Interface."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import psycopg

from ctower_kernel.proof import Proof, ProofActor, ProofMutation, ProofReceipt, RecordEvidence
from ctower_kernel.proof._object_sql import (
    inline_objects,
    load_object,
    mark_erased,
    record_backfill,
)
from ctower_kernel.proof._postgres_sql import mutate_proof
from ctower_kernel.proof._snapshot_sql import proof_is_current
from ctower_kernel.proof.objects import (
    ObjectIntegrityError,
    ProofObjectStore,
    StoredObject,
    verify_digest,
)
from ctower_kernel.record import RecordProblem
from ctower_kernel.record.transaction import authority_connection, recover_ambiguous_commit
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__ = ["PostgresProof"]


class PostgresProof:
    """Own Proof SQL and expose only mutation and current-proof capabilities."""

    def __init__(
        self,
        dsn: str,
        *,
        object_store: ProofObjectStore | None = None,
        object_key_reference: str | None = None,
        telemetry: Telemetry | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._dsn = dsn
        self._object_store = object_store
        self._object_key_reference = object_key_reference
        self._telemetry = telemetry or NoopTelemetry()
        self._clock = clock or (lambda: datetime.now(UTC))
        if (object_store is None) is not (object_key_reference is None):
            raise ValueError("object store and key reference must be configured together")

    def mutate_proof(
        self,
        evaluator: Proof,
        actor: ProofActor,
        mutation: ProofMutation,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> ProofReceipt | RecordProblem:
        """Atomically persist one accepted Proof decision."""

        object_receipt = self._prepare_object(actor, mutation)
        outcome = recover_ambiguous_commit(
            lambda: mutate_proof(
                self._dsn,
                evaluator,
                actor,
                mutation,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
                object_receipt=object_receipt,
            )
        )
        self._telemetry.emit(
            "proof.mutate",
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )
        return outcome

    def read_object(self, tenant_id: UUID, artifact_digest: str) -> bytes:
        """Dual-read inline or externally encrypted bytes and always verify digest."""

        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            row = load_object(connection, tenant_id, artifact_digest)
        if row is None:
            raise ObjectIntegrityError("proof object is missing")
        if row.state == "erased":
            raise ObjectIntegrityError("proof object is durably erased")
        if row.receipt is not None:
            if self._object_store is None:
                raise ObjectIntegrityError("external object access is unavailable")
            return self._object_store.read_verified(tenant_id, row.receipt)
        if row.content is None:
            raise ObjectIntegrityError("inline object bytes are missing")
        verify_digest(row.content, artifact_digest)
        return row.content

    def backfill_objects(self, tenant_id: UUID, *, clear_inline: bool = False) -> int:
        """Upload legacy inline bytes and record before/after digest receipts."""

        store, key_reference = self._configured_store()
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            candidates = inline_objects(connection, tenant_id)
        for artifact_digest, content, producer_id, recorded_at in candidates:
            verify_digest(content, artifact_digest)
            receipt = store.put_verified(
                tenant_id,
                artifact_digest,
                content,
                key_reference=key_reference,
            )
            with authority_connection(self._dsn) as connection:
                connection.execute("SET ROLE ctower_svc")
                record_backfill(
                    connection,
                    tenant_id,
                    producer_id,
                    content,
                    receipt,
                    recorded_at=recorded_at,
                    clear_inline=clear_inline,
                )
        return len(candidates)

    def erase_object(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        *,
        tombstone_id: UUID,
        authority_ref: str,
        reason: str,
    ) -> None:
        """Erase exact external bytes/key, then append the durable tombstone."""

        store, _key_reference = self._configured_store()
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            row = load_object(connection, tenant_id, artifact_digest)
        if row is None or row.receipt is None or row.state != "external_verified":
            raise ObjectIntegrityError("only one verified external object can be erased")
        store.read_verified(tenant_id, row.receipt)
        store.erase(tenant_id, row.receipt)
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            mark_erased(
                connection,
                tenant_id,
                artifact_digest,
                row.receipt,
                tombstone_id=tombstone_id,
                authority_ref=authority_ref,
                reason=reason,
                erased_at=self._clock(),
            )

    def is_current(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> bool:
        """Evaluate current proof inside a caller-owned atomic transaction."""

        return proof_is_current(connection, Proof(), tenant_id, ticket_id)

    def _prepare_object(
        self,
        actor: ProofActor,
        mutation: ProofMutation,
    ) -> StoredObject | None:
        if not isinstance(mutation.command, RecordEvidence):
            return None
        command = mutation.command
        try:
            verify_digest(command.content, command.artifact_digest)
        except ObjectIntegrityError:
            return None
        if self._object_store is None:
            return None
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            reserved = connection.execute(
                """
                SELECT request_sha256 FROM command_results
                WHERE tenant_id = %s AND principal_id = %s AND client_command_id = %s
                """,
                (actor.tenant_id, actor.principal_id, mutation.client_command_id),
            ).fetchone()
            if reserved is not None:
                return None
            existing = load_object(connection, actor.tenant_id, command.artifact_digest)
        if existing is not None and existing.receipt is not None:
            recovered = self._object_store.read_verified(actor.tenant_id, existing.receipt)
            if recovered != command.content:
                raise ObjectIntegrityError("existing object bytes differ from evidence content")
            return existing.receipt
        _store, key_reference = self._configured_store()
        return self._object_store.put_verified(
            actor.tenant_id,
            command.artifact_digest,
            command.content,
            key_reference=key_reference,
        )

    def _configured_store(self) -> tuple[ProofObjectStore, str]:
        if self._object_store is None or self._object_key_reference is None:
            raise ObjectIntegrityError("encrypted object storage is not configured")
        return self._object_store, self._object_key_reference
