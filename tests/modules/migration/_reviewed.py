"""Synthetic complete reviewed graph for real migration-boundary tests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectImportRunCreateRequest,
)
from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    canonical_digest,
)
from tools.migration.ctower_project.ctower_project_source.exporter import (
    FrozenExport,
    compare_exports,
    freeze_export,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import (
    ImportPlan,
    build_import_plan,
    seal_import_plan,
)
from tools.migration.ctower_project.ctower_project_source.source import ReadOnlySourceRoot

from .source_tool.fixtures import REVIEW, SyntheticFixture, make_fixture

_REGISTRY_NAMESPACE = UUID("f2b29119-060f-5fa2-8a64-18edbb73a111")
__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewedSource:
    fixture: SyntheticFixture
    first: FrozenExport
    second: FrozenExport
    equality: dict[str, Any]
    cutover_id: UUID
    importer_credential: str
    observer_credential: str

    @property
    def trusted_keys(self) -> dict[tuple[str, int], Ed25519PublicKey]:
        return {("signing-key-ref:test/reviewer", 1): self.fixture.public_key}

    def create_request(self, now: datetime) -> CtowerProjectImportRunCreateRequest:
        target = self.fixture.target_inventory
        signature = self.fixture.selection["signature"]
        return CtowerProjectImportRunCreateRequest(
            cutover_id=self.cutover_id,
            tenant_key="ctower",
            project_key="ctower",
            source_selection_digest=self.fixture.selection["manifest_digest"],
            source_selection_artifact=canonical_bytes(self.fixture.selection).decode(),
            build_digest=target["build_digest"],
            client_digest=target["client_digest"],
            schema_digest=target["schema_digest"],
            operation_registry_digest=target["operation_registry_digest"],
            reviewer_key_ref=signature["key_ref"],
            reviewer_key_version=signature["key_version"],
            reviewer_public_key_digest=signature["public_key_digest"],
            importer_credential_digest=_credential_digest(self.importer_credential),
            importer_expires_at=now + timedelta(hours=1),
        )

    def export_request(self, run_id: UUID) -> CtowerProjectExportEqualityBindRequest:
        return CtowerProjectExportEqualityBindRequest(
            run_id=run_id,
            cutover_id=self.cutover_id,
            selection_digest=self.fixture.selection["manifest_digest"],
            inventory_a_digest=self.first.manifest["target_inventory"]["inventory_digest"],
            inventory_b_digest=self.second.manifest["target_inventory"]["inventory_digest"],
            export_digest=self.first.manifest["artifact_digest"],
            equality_report_digest=self.equality["report_digest"],
            reviewer_key_ref=self.equality["signature"]["key_ref"],
            reviewer_key_version=self.equality["signature"]["key_version"],
            reviewer_public_key_digest=self.equality["signature"]["public_key_digest"],
            result="equal",
            export_a_artifact=canonical_bytes(self.first.manifest).decode(),
            export_b_artifact=canonical_bytes(self.second.manifest).decode(),
            export_equality_artifact=canonical_bytes(self.equality).decode(),
        )

    def plan_request(
        self,
        run_id: UUID,
        existing_ticket_id: UUID,
        commander_custodian_id: UUID,
        now: datetime,
    ) -> tuple[CtowerProjectAliasPlanBindRequest, ImportPlan]:
        alias = self.fixture.alias_map(
            self.equality,
            existing_ticket_id=existing_ticket_id,
        )
        plan = build_import_plan(
            self.first,
            self.equality,
            alias,
            run_id=run_id,
            cutover_id=self.cutover_id,
            commander_custodian_id=commander_custodian_id,
            verifier=self.fixture.verifier,
        )
        signed_plan = seal_import_plan(
            plan,
            self.first,
            review=REVIEW,
            signer=self.fixture.signer,
        )
        registry = _registry(self, run_id)
        request = CtowerProjectAliasPlanBindRequest(
            run_id=run_id,
            cutover_id=self.cutover_id,
            export_equality_digest=self.equality["report_digest"],
            alias_map_digest=alias["map_digest"],
            reviewer_key_ref=alias["signature"]["key_ref"],
            reviewer_key_version=alias["signature"]["key_version"],
            reviewer_public_key_digest=alias["signature"]["public_key_digest"],
            attention_required=0,
            alias_map_artifact=canonical_bytes(alias).decode(),
            import_plan_artifact=canonical_bytes(signed_plan).decode(),
            fence_registry_artifact=canonical_bytes(registry).decode(),
            fence_observer_credential_digest=_credential_digest(self.observer_credential),
            fence_observer_expires_at=now + timedelta(hours=1),
        )
        return request, plan


def reviewed_source(root: Path, cutover_id: UUID) -> ReviewedSource:
    fixture = make_fixture(root)
    source = ReadOnlySourceRoot(fixture.root)
    first = freeze_export(
        fixture.selection,
        source,
        fixture.target_inventory,
        cutover_id=cutover_id,
        export_stage="export_a",
        verifier=fixture.verifier,
    )
    second = freeze_export(
        fixture.selection,
        source,
        fixture.target_inventory,
        cutover_id=cutover_id,
        export_stage="export_b",
        verifier=fixture.verifier,
    )
    equality = compare_exports(first, second, review=REVIEW, signer=fixture.signer)
    return ReviewedSource(
        fixture,
        first,
        second,
        equality,
        cutover_id,
        "synthetic-importer-credential",
        "synthetic-fence-observer",
    )


def _registry(source: ReviewedSource, run_id: UUID) -> dict[str, Any]:
    digest = source.fixture.target_inventory["operation_registry_digest"]
    clients = [
        {
            "client_id": f"synthetic-client-{index}",
            "path": f"clients/client-{index}",
            "executable_digest": digest,
            "scope_behavior": "observe_only",
        }
        for index in range(3)
    ]
    artifact: dict[str, Any] = {
        "schema": "ctower.ctower-project-fence-registry/v2",
        "registry_id": str(uuid5(_REGISTRY_NAMESPACE, f"{run_id}:registry")),
        "revision": 1,
        "previous_revision_digest": None,
        "cutover_id": str(source.cutover_id),
        "source_selection_digest": source.fixture.selection["manifest_digest"],
        "tenant_key": "ctower",
        "project_key": "ctower",
        "mode": "synthetic_dormant",
        "selected_request_ids": source.fixture.request_ids,
        "selected_task_ids": [],
        "direct_writers": clients,
        "indirect_clients": [
            {
                "client_id": "synthetic-indirect",
                "path": "clients/indirect",
                "executable_digest": digest,
                "scope_behavior": "observe_only",
            }
        ],
        "source_pointer": {
            "path": "requests.jsonl",
            "device": 1,
            "inode": 1,
            "last_complete_offset": 0,
            "scoped_rows_digest": digest,
        },
        "source_pointer_digest": canonical_digest(
            {
                "path": "requests.jsonl",
                "device": 1,
                "inode": 1,
                "last_complete_offset": 0,
                "scoped_rows_digest": digest,
            }
        ),
        "monitor_interval_seconds": 30,
        "max_observation_age_seconds": 90,
        "max_future_clock_skew_seconds": 5,
        "operation_registry_digest": digest,
        "created_at": REVIEW["reviewed_at"],
        "review": REVIEW,
    }
    return source.fixture.signer.seal(artifact, "registry_digest")


def _credential_digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"
