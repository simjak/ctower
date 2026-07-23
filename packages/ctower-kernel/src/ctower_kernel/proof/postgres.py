"""Postgres implementation behind the Proof Interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg

from ctower_kernel.proof import Proof, ProofActor, ProofMutation, ProofPolicy, ProofReceipt
from ctower_kernel.proof._postgres_sql import ProofPolicyPins, mutate_proof
from ctower_kernel.proof._snapshot_sql import proof_is_current
from ctower_kernel.record import RecordProblem
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__ = ["PostgresProof"]


class PostgresProof:
    """Own Proof SQL and expose only mutation and current-proof capabilities."""

    def __init__(
        self,
        dsn: str,
        *,
        policies: tuple[ProofPolicy, ...] = (),
        policy_pins: ProofPolicyPins | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._dsn = dsn
        self._policies = policies
        self._policy_pins = policy_pins or _UnavailableProofPolicyPins()
        self._telemetry = telemetry or NoopTelemetry()

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

        outcome = recover_ambiguous_commit(
            lambda: mutate_proof(
                self._dsn,
                evaluator,
                self._policies,
                self._policy_pins,
                actor,
                mutation,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )
        self._telemetry.emit(
            "proof.mutate",
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )
        return outcome

    def is_current(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> bool:
        """Evaluate current proof inside a caller-owned atomic transaction."""

        pin = self._policy_pins.proof_policy_pin(connection, tenant_id, ticket_id)
        policy = next((item for item in self._policies if item.pin == pin), None)
        return policy is not None and proof_is_current(
            connection, Proof(), policy, tenant_id, ticket_id
        )


class _UnavailableProofPolicyPins:
    def proof_policy_pin(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> tuple[str, str, str, str, str] | None:
        del connection, tenant_id, ticket_id
        return None
