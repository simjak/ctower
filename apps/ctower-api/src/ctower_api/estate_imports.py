"""Application-owned PostgreSQL estate-import orchestration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import psycopg
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ctower_api.estate_import_company import append_company_record
from ctower_api.estate_import_contracts import (
    EstateImportBatchResult,
    _company_import_command,
    _CompanyImportPlan,
    _EstateImportPlan,
    _EstateParitySigner,
    _InboxImportPlan,
    _knowledge_import_command,
    _KnowledgeImportPlan,
    _required_text,
    _ruling_import_command,
    _RulingImportPlan,
    verify_estate_manifest,
)
from ctower_api.estate_import_inbox import (
    apply_inbox_plan,
    prepare_inbox_batch,
)
from ctower_api.estate_import_support import (
    _digest_request,
    _estate_batch_event,
    _estate_problem,
    _estate_replay,
    _generic_parity,
    _inbox_batch_header,
    _inbox_parity,
    _operator_refusal,
    _validate_generic_batch_digest,
)
from ctower_kernel.inbox import PostgresInbox
from ctower_kernel.knowledge import PostgresKnowledge
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.artifacts import ArtifactError
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    recover_ambiguous_commit,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.rulings import PostgresRulings

__all__ = ("PostgresEstateImports", "verify_estate_manifest")


class PostgresEstateImports:
    """Operator-only PostgreSQL adapter for all estate-import tiers."""

    def __init__(
        self,
        dsn: str,
        trusted_keys: Mapping[tuple[str, int], Ed25519PublicKey],
        *,
        parity_signer: _EstateParitySigner | None,
        inbox: PostgresInbox | None = None,
        knowledge: PostgresKnowledge | None = None,
        rulings: PostgresRulings | None = None,
    ) -> None:
        self._dsn = dsn
        self._trusted_keys = trusted_keys
        self._parity_signer = parity_signer
        self._inbox = inbox or PostgresInbox(dsn)
        self._knowledge = knowledge or PostgresKnowledge(dsn)
        self._rulings = rulings or PostgresRulings(dsn)

    def import_batch(
        self,
        actor: Actor,
        *,
        tier: str,
        batch_index: int,
        command_id: UUID,
        manifest: Mapping[str, object],
        rows: Sequence[Mapping[str, object]],
        now: datetime,
        telemetry: TelemetryContext,
    ) -> EstateImportBatchResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: self._apply_batch(
                actor,
                tier=tier,
                batch_index=batch_index,
                command_id=command_id,
                manifest=manifest,
                rows=rows,
                now=now,
                telemetry=telemetry,
            )
        )

    def _apply_batch(
        self,
        actor: Actor,
        *,
        tier: str,
        batch_index: int,
        command_id: UUID,
        manifest: Mapping[str, object],
        rows: Sequence[Mapping[str, object]],
        now: datetime,
        telemetry: TelemetryContext,
    ) -> EstateImportBatchResult | RecordProblem:
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            refusal = _operator_refusal(connection, actor, command_id)
            if refusal is not None:
                return refusal
            prepared = self._prepare_import(
                connection,
                actor,
                tier=tier,
                batch_index=batch_index,
                command_id=command_id,
                manifest=manifest,
                rows=rows,
            )
            if isinstance(prepared, RecordProblem):
                return prepared
            manifest_digest, plans = prepared
            return self._commit_inbox_batch(
                connection,
                actor,
                tier=tier,
                batch_index=batch_index,
                command_id=command_id,
                manifest_digest=manifest_digest,
                rows=rows,
                plans=plans,
                now=now,
                telemetry=telemetry,
            )

    def _prepare_import(
        self,
        connection: psycopg.Connection[dict[str, object]],
        actor: Actor,
        *,
        tier: str,
        batch_index: int,
        command_id: UUID,
        manifest: Mapping[str, object],
        rows: Sequence[Mapping[str, object]],
    ) -> tuple[str, tuple[_EstateImportPlan, ...]] | RecordProblem:
        try:
            artifact, manifest_digest = self._verified_manifest(manifest, tier)
            prepared = self._prepare_tier(
                connection,
                actor,
                tier=tier,
                artifact=artifact,
                batch_index=batch_index,
                rows=rows,
                command_id=command_id,
            )
        except (ArtifactError, KeyError, TypeError, ValueError) as error:
            return _estate_problem(command_id, "estate-import-invalid", str(error))
        if isinstance(prepared, RecordProblem):
            return prepared
        return manifest_digest, prepared

    def _prepare_tier(
        self,
        connection: psycopg.Connection[dict[str, object]],
        actor: Actor,
        *,
        tier: str,
        artifact: Mapping[str, object],
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
        command_id: UUID,
    ) -> tuple[_EstateImportPlan, ...] | RecordProblem:
        if tier == "inbox_history":
            return prepare_inbox_batch(connection, actor, artifact, batch_index, rows, command_id)
        if tier == "agreed_decisions":
            return self._prepare_ruling_batch(actor, artifact, batch_index, rows, command_id)
        if tier == "knowledge_documents":
            return self._prepare_knowledge_batch(artifact, batch_index, rows, command_id, actor)
        if tier == "company_records":
            return self._prepare_company_batch(artifact, batch_index, rows, command_id, actor)
        return _estate_problem(
            command_id,
            "estate-import-invalid",
            "Estate import tier is outside the contract.",
        )

    def _prepare_ruling_batch(
        self,
        actor: Actor,
        artifact: Mapping[str, object],
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
        command_id: UUID,
    ) -> tuple[_RulingImportPlan, ...] | RecordProblem:
        header = _inbox_batch_header(artifact, batch_index, len(rows), command_id)
        project_key = artifact.get("project_key")
        if isinstance(header, RecordProblem) or not isinstance(project_key, str):
            problem = (
                header
                if isinstance(header, RecordProblem)
                else _estate_problem(
                    command_id,
                    "estate-import-project-required",
                    "Ruling imports require a project key in the signed manifest.",
                )
            )
            return problem
        plans: list[_RulingImportPlan] = []
        seen: set[str] = set()
        for row in rows:
            try:
                source_ref = _required_text(row, "source_ref")
                command = _ruling_import_command(actor, row, project_key=project_key)
            except (KeyError, TypeError, ValueError) as error:
                return _estate_problem(command_id, "estate-import-row-invalid", str(error))
            refusal = prohibited_data_refusal((command.verbatim, source_ref), command_id=command_id)
            if refusal is not None:
                return refusal
            if source_ref in seen:
                return _estate_problem(
                    command_id,
                    "estate-import-duplicate-source",
                    "A batch contains a duplicate source reference.",
                )
            seen.add(source_ref)
            plans.append(_RulingImportPlan(row, command))
        digest_problem = _validate_generic_batch_digest(
            header, "agreed_decisions", rows, command_id
        )
        if digest_problem is not None:
            return digest_problem
        return tuple(plans)

    def _prepare_knowledge_batch(
        self,
        artifact: Mapping[str, object],
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
        command_id: UUID,
        actor: Actor,
    ) -> tuple[_KnowledgeImportPlan, ...] | RecordProblem:
        header = _inbox_batch_header(artifact, batch_index, len(rows), command_id)
        if isinstance(header, RecordProblem):
            return header
        plans: list[_KnowledgeImportPlan] = []
        seen: set[str] = set()
        for row in rows:
            try:
                source_ref = _required_text(row, "source_ref")
                command = _knowledge_import_command(actor, row)
            except (KeyError, TypeError, ValueError) as error:
                return _estate_problem(command_id, "estate-import-row-invalid", str(error))
            refusal = prohibited_data_refusal(
                (command.title, command.body, source_ref), command_id=command_id
            )
            if refusal is not None:
                return refusal
            if source_ref in seen:
                return _estate_problem(
                    command_id,
                    "estate-import-duplicate-source",
                    "A batch contains a duplicate source reference.",
                )
            seen.add(source_ref)
            plans.append(_KnowledgeImportPlan(row, command))
        digest_problem = _validate_generic_batch_digest(
            header, "knowledge_documents", rows, command_id
        )
        if digest_problem is not None:
            return digest_problem
        return tuple(plans)

    def _prepare_company_batch(
        self,
        artifact: Mapping[str, object],
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
        command_id: UUID,
        actor: Actor,
    ) -> tuple[_CompanyImportPlan, ...] | RecordProblem:
        header = _inbox_batch_header(artifact, batch_index, len(rows), command_id)
        if isinstance(header, RecordProblem):
            return header
        plans: list[_CompanyImportPlan] = []
        seen: set[str] = set()
        for row in rows:
            try:
                source_ref = _required_text(row, "source_ref")
                command = _company_import_command(actor, row)
            except (KeyError, TypeError, ValueError) as error:
                return _estate_problem(command_id, "estate-import-row-invalid", str(error))
            if source_ref in seen:
                return _estate_problem(
                    command_id,
                    "estate-import-duplicate-source",
                    "A batch contains a duplicate source reference.",
                )
            seen.add(source_ref)
            plans.append(_CompanyImportPlan(row, command))
        digest_problem = _validate_generic_batch_digest(header, "company_records", rows, command_id)
        if digest_problem is not None:
            return digest_problem
        return tuple(plans)

    def _commit_inbox_batch(
        self,
        connection: psycopg.Connection[dict[str, object]],
        actor: Actor,
        *,
        tier: str,
        batch_index: int,
        command_id: UUID,
        manifest_digest: str,
        rows: Sequence[Mapping[str, object]],
        plans: Sequence[_EstateImportPlan],
        now: datetime,
        telemetry: TelemetryContext,
    ) -> EstateImportBatchResult | RecordProblem:
        transaction, request_digest, replay = self._reserve_batch(
            connection, actor, command_id, manifest_digest, batch_index, rows
        )
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _estate_replay(replay)
        signer = self._require_parity_signer(transaction, actor, command_id, request_digest, now)
        if isinstance(signer, RecordProblem):
            return signer
        imported = 0
        for plan in plans:
            if isinstance(plan, _InboxImportPlan) and plan.prohibited is not None:
                continue
            problem = self._apply_plan(
                actor,
                plan,
                command_id=command_id,
                now=now,
                telemetry=telemetry,
                connection=connection,
            )
            if problem is not None:
                return self._refuse_batch(
                    transaction, actor, command_id, request_digest, problem, now
                )
            imported += 1
        parity = self._parity_report(
            tier=tier,
            manifest_digest=manifest_digest,
            batch_index=batch_index,
            rows=rows,
            plans=plans,
            imported=imported,
            signer=signer,
        )
        return self._commit_result(
            transaction,
            actor,
            command_id,
            tier,
            batch_index,
            manifest_digest,
            plans,
            imported,
            parity,
            request_digest,
            now,
            telemetry,
        )

    def _require_parity_signer(
        self,
        transaction: RecordTransaction,
        actor: Actor,
        command_id: UUID,
        request_digest: bytes,
        now: datetime,
    ) -> _EstateParitySigner | RecordProblem:
        signer = self._parity_signer
        if signer is not None:
            return signer
        return self._refuse_batch(
            transaction,
            actor,
            command_id,
            request_digest,
            _estate_problem(
                command_id,
                "estate-import-parity-signer-unavailable",
                "Estate import parity requires an approved signing key.",
                status=503,
            ),
            now,
        )

    def _reserve_batch(
        self,
        connection: psycopg.Connection[dict[str, object]],
        actor: Actor,
        command_id: UUID,
        manifest_digest: str,
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
    ) -> tuple[RecordTransaction, bytes, dict[str, object] | RecordProblem | None]:
        request_digest = _digest_request(manifest_digest, batch_index, rows)
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command_id, request_digest)
        return transaction, request_digest, replay

    def _refuse_batch(
        self,
        transaction: RecordTransaction,
        actor: Actor,
        command_id: UUID,
        request_digest: bytes,
        problem: RecordProblem,
        now: datetime,
    ) -> RecordProblem:
        transaction.refuse(
            actor.tenant_id,
            actor.principal_id,
            command_id,
            request_digest,
            problem,
            now=now,
        )
        return problem

    def _parity_report(
        self,
        *,
        tier: str,
        manifest_digest: str,
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
        plans: Sequence[_EstateImportPlan],
        imported: int,
        signer: _EstateParitySigner,
    ) -> Mapping[str, object]:
        if tier == "inbox_history":
            return _inbox_parity(
                tier=tier,
                manifest_digest=manifest_digest,
                batch_index=batch_index,
                plans=cast(Sequence[_InboxImportPlan], plans),
                signer=signer,
            )
        return _generic_parity(
            tier=tier,
            manifest_digest=manifest_digest,
            batch_index=batch_index,
            rows=rows,
            imported_count=imported,
            signer=signer,
        )

    def _commit_result(
        self,
        transaction: RecordTransaction,
        actor: Actor,
        command_id: UUID,
        tier: str,
        batch_index: int,
        manifest_digest: str,
        plans: Sequence[_EstateImportPlan],
        imported: int,
        parity: Mapping[str, object],
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> EstateImportBatchResult:
        event = _estate_batch_event(
            actor,
            command_id,
            tier=tier,
            manifest_digest=manifest_digest,
            batch_index=batch_index,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        result = EstateImportBatchResult(
            command_id,
            (event.event_id,),
            tier,
            manifest_digest,
            len(plans),
            imported,
            parity,
        )
        transaction.commit_batch(
            (EventCommit(event, uuid7(now)),),
            response_body=result.response_payload(),
            status_code=201,
            telemetry=telemetry,
            now=now,
        )
        return result

    def _verified_manifest(
        self, manifest: Mapping[str, object], tier: str
    ) -> tuple[dict[str, Any], str]:
        signature = manifest.get("signature")
        if not isinstance(signature, Mapping):
            raise ArtifactError("signature-invalid")
        key_ref, key_version = signature.get("key_ref"), signature.get("key_version")
        if not isinstance(key_ref, str) or not isinstance(key_version, int):
            raise ArtifactError("signature-invalid")
        public_key = self._trusted_keys.get((key_ref, key_version))
        if public_key is None:
            raise ArtifactError("review-key-untrusted")
        text = rfc8785.dumps(cast(Any, manifest)).decode("utf-8")
        counts = manifest.get("counts")
        if not isinstance(counts, Mapping):
            raise ArtifactError("artifact-invalid")
        source_count = counts.get("source_rows")
        if not isinstance(source_count, int):
            raise ArtifactError("artifact-invalid")
        artifact = verify_estate_manifest(
            text,
            tier=tier,
            source_row_count=source_count,
            public_key=public_key,
        )
        digest = artifact.get("manifest_digest")
        if not isinstance(digest, str):
            raise ArtifactError("artifact-invalid")
        return artifact, digest

    def _apply_plan(
        self,
        actor: Actor,
        plan: _EstateImportPlan,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
        connection: psycopg.Connection[dict[str, object]],
    ) -> RecordProblem | None:
        if isinstance(plan, _InboxImportPlan):
            return apply_inbox_plan(
                self._inbox,
                connection,
                actor,
                plan,
                command_id=command_id,
                now=now,
                telemetry=telemetry,
            )
        if isinstance(plan, _RulingImportPlan):
            ruling_result = self._rulings.append(
                actor,
                plan.command,
                request_digest=_digest_request("ruling-import", 0, [plan.row]),
                now=now,
                telemetry=telemetry,
            )
            return ruling_result if isinstance(ruling_result, RecordProblem) else None
        if isinstance(plan, _KnowledgeImportPlan):
            knowledge_result = self._knowledge.register(
                actor,
                plan.command,
                request_digest=_digest_request("knowledge-import", 0, [plan.row]),
                now=now,
                telemetry=telemetry,
            )
            return knowledge_result if isinstance(knowledge_result, RecordProblem) else None
        company_result = append_company_record(
            self._dsn,
            actor,
            plan.command,
            request_digest=_digest_request("company-record-import", 0, [plan.row]),
            now=now,
            telemetry=telemetry,
        )
        return company_result if isinstance(company_result, RecordProblem) else None
