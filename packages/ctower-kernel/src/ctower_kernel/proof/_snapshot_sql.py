"""Rebuild immutable Proof snapshots from append-only facts."""

from __future__ import annotations

from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.proof import (
    Criterion,
    Evidence,
    Proof,
    ProofPolicy,
    ProofSnapshot,
    Verdict,
    VerdictDecision,
)

__all__: tuple[str, ...] = ()


def proof_is_current(
    connection: psycopg.Connection[dict[str, object]],
    evaluator: Proof,
    policy: ProofPolicy,
    tenant_id: UUID,
    ticket_id: UUID,
) -> bool:
    """Evaluate current proof inside an existing Workflow transaction."""

    bundle = connection.execute(
        """
        SELECT proof_id, version, candidate_digest, candidate_author_id
        FROM proof_bundles WHERE tenant_id = %s AND ticket_id = %s
        FOR UPDATE
        """,
        (tenant_id, ticket_id),
    ).fetchone()
    return bundle is not None and evaluator.is_satisfied(
        load_snapshot(connection, bundle, tenant_id), policy=policy
    )


def load_snapshot(
    connection: psycopg.Connection[dict[str, object]],
    bundle: dict[str, object] | None,
    tenant_id: UUID,
) -> ProofSnapshot:
    """Load one proof bundle without weakening its tenant predicate."""

    if bundle is None:
        return ProofSnapshot.empty()
    proof_id = cast(UUID, bundle["proof_id"])
    criteria = connection.execute(
        """
        SELECT criterion_key, description, candidate_dependent, requires_verdict
        FROM proof_criteria WHERE tenant_id = %s AND proof_id = %s ORDER BY criterion_key
        """,
        (tenant_id, proof_id),
    ).fetchall()
    evidence = connection.execute(
        """
        SELECT evidence_id, criterion_key, candidate_digest, artifact_digest, producer_id
        FROM proof_evidence WHERE tenant_id = %s AND proof_id = %s ORDER BY recorded_at, evidence_id
        """,
        (tenant_id, proof_id),
    ).fetchall()
    verdicts = connection.execute(
        """
        SELECT verdict_id, criterion_key, candidate_digest, reviewer_id, decision
        FROM proof_verdicts WHERE tenant_id = %s AND proof_id = %s ORDER BY proof_sequence
        """,
        (tenant_id, proof_id),
    ).fetchall()
    invalidations = connection.execute(
        """
        SELECT target_kind, target_id FROM proof_invalidations
        WHERE tenant_id = %s AND proof_id = %s
        """,
        (tenant_id, proof_id),
    ).fetchall()
    return _snapshot(bundle, criteria, evidence, verdicts, invalidations)


def _snapshot(
    bundle: dict[str, object],
    criteria_rows: list[dict[str, object]],
    evidence_rows: list[dict[str, object]],
    verdict_rows: list[dict[str, object]],
    invalidation_rows: list[dict[str, object]],
) -> ProofSnapshot:
    return ProofSnapshot(
        criteria=tuple(
            Criterion(
                key=str(row["criterion_key"]),
                description=str(row["description"]),
                candidate_dependent=bool(row["candidate_dependent"]),
                requires_verdict=bool(row["requires_verdict"]),
            )
            for row in criteria_rows
        ),
        candidate_digest=_digest_text(bundle["candidate_digest"]),
        candidate_author_id=cast(UUID, bundle["candidate_author_id"]),
        evidence=tuple(_evidence(row) for row in evidence_rows),
        verdicts=tuple(_verdict(row) for row in verdict_rows),
        invalidated_evidence_ids=frozenset(
            cast(UUID, row["target_id"])
            for row in invalidation_rows
            if row["target_kind"] == "evidence"
        ),
        invalidated_verdict_ids=frozenset(
            cast(UUID, row["target_id"])
            for row in invalidation_rows
            if row["target_kind"] == "verdict"
        ),
    )


def _evidence(row: dict[str, object]) -> Evidence:
    return Evidence(
        evidence_id=cast(UUID, row["evidence_id"]),
        criterion_key=str(row["criterion_key"]),
        candidate_digest=_digest_text(row["candidate_digest"]),
        artifact_digest=_digest_text(row["artifact_digest"]),
        producer_id=cast(UUID, row["producer_id"]),
    )


def _verdict(row: dict[str, object]) -> Verdict:
    return Verdict(
        verdict_id=cast(UUID, row["verdict_id"]),
        criterion_key=str(row["criterion_key"]),
        candidate_digest=_digest_text(row["candidate_digest"]),
        reviewer_id=cast(UUID, row["reviewer_id"]),
        decision=VerdictDecision(str(row["decision"])),
    )


def _digest_text(value: object) -> str:
    return "sha256:" + bytes(cast(bytes, value)).hex()
