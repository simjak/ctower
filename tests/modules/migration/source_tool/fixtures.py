from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    canonical_digest,
    sha256_digest,
)
from tools.migration.ctower_project.ctower_project_source.signing import (
    ArtifactSigner,
    ArtifactVerifier,
)

__all__: tuple[str, ...] = ()

REVIEW = {
    "reviewer_principal_id": "2f463d7a-f7d5-4d6b-b7f9-8ed92448e825",
    "reviewed_at": "2026-07-25T15:45:00Z",
    "decision": "approved",
}
CUTOVER_ID = UUID("a9583597-17cf-4522-bb17-eb21952b4f87")
RUN_ID = UUID("8a3ed01e-e9dd-4575-b0bc-bb6a252aa41c")
COMMANDER_ID = UUID("059454c6-22b5-41a8-9730-6905e8d4fadb")
UUID_NAMESPACE = UUID("3059177a-82c8-50e1-92f0-89f765fe654f")
THREE_SNAPSHOT_ITEM_COUNT = 71
CHECKPOINT_DISPOSITION_START = 60
DISPOSITIONS = (
    *("created_ticket" for _ in range(40)),
    *("alias_linked_existing" for _ in range(20)),
    *("project_checkpoint_definition" for _ in range(14)),
    *("decision_link" for _ in range(5)),
    "external_effect_link",
    "artifact_linked_not_proof",
    *("provenance_only" for _ in range(3)),
    "exact_duplicate",
    "excluded_out_of_scope",
)
FORBIDDEN = [
    "non_ctower_scope",
    "bulk_crew_log",
    "raw_session_or_transcript",
    "prompt_or_model_context",
    "secret_or_authentication_value",
    "pii_or_client_data",
    "accounting_payment_tax_invoice",
    "production_approval_effect_or_incident",
    "large_binary",
    "irreplaceable_or_expensive_sole_copy",
    "derived_board_markdown",
    "unreferenced_coordination",
    "pass_or_done_prose_as_proof",
    "browser_session_or_csrf",
    "yaml_as_live_work_truth",
]


@dataclass(frozen=True)
class SyntheticFixture:
    root: Path
    selection: dict[str, Any]
    target_inventory: dict[str, Any]
    signer: ArtifactSigner
    verifier: ArtifactVerifier
    public_key_path: Path
    public_key: Ed25519PublicKey
    request_ids: list[str]
    stable_ids: list[str]
    checkpoint_keys: list[str]

    def alias_map(
        self,
        equality: dict[str, Any],
        *,
        existing_ticket_id: UUID | None = None,
    ) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        for index, source_id in enumerate(self.request_ids):
            identity = _identity("mission-control:request", source_id)
            disposition, target = _disposition(
                index,
                self.checkpoint_keys,
                existing_ticket_id=existing_ticket_id,
            )
            entries.append(
                {
                    "identity": identity,
                    "disposition": disposition,
                    "planned_target_ref": target,
                    "reason_code": f"reviewed_mapping_{index:02d}",
                }
            )
        artifact: dict[str, Any] = {
            "schema": "ctower.ctower-project-alias-map/v2",
            "alias_map_id": str(uuid5(UUID_NAMESPACE, "alias-map")),
            "cutover_id": str(CUTOVER_ID),
            "selection_digest": self.selection["manifest_digest"],
            "export_equality_digest": equality["report_digest"],
            "created_at": REVIEW["reviewed_at"],
            "stable_aliases": [
                {
                    "stable_item_id": stable_id,
                    "target_ticket_id": str(
                        existing_ticket_id or uuid5(UUID_NAMESPACE, f"stable-target:{stable_id}")
                    ),
                }
                for stable_id in self.stable_ids
            ],
            "entries": entries,
            "attention_required": 0,
            "review": REVIEW,
        }
        return self.signer.seal(artifact, "map_digest")


def make_fixture(root: Path) -> SyntheticFixture:
    vectors_path = (
        Path(__file__).resolve().parents[4] / "contracts/domain/migration/migration-vectors.json"
    )
    vectors = json.loads(vectors_path.read_text(encoding="utf-8"))["sealed_source"]
    request_ids = list(vectors["mission_control_request_ids"])
    stable_ids = list(vectors["stable_ticket_ids"])
    checkpoint_keys = list(vectors["checkpoint_keys"])
    private = Ed25519PrivateKey.generate()
    signer = ArtifactSigner("signing-key-ref:test/reviewer", 1, private)
    public = private.public_key()
    public_path = root / "reviewer.pub"
    public_path.write_bytes(
        public.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    rows = _source_rows(request_ids, stable_ids, checkpoint_keys)
    inventories = _write_sources(root, rows)
    selection = _selection(
        signer,
        request_ids,
        stable_ids,
        checkpoint_keys,
        inventories,
    )
    target = _target_inventory()
    (root / "selection.json").write_bytes(canonical_bytes(selection))
    (root / "target.json").write_bytes(canonical_bytes(target))
    return SyntheticFixture(
        root,
        selection,
        target,
        signer,
        ArtifactVerifier(public),
        public_path,
        public,
        request_ids,
        stable_ids,
        checkpoint_keys,
    )


def _write_sources(root: Path, rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    inventories: list[dict[str, Any]] = []
    source_specs: tuple[tuple[str, str, list[dict[str, Any]], bool], ...] = (
        ("mission_control_requests", "requests.jsonl", rows["requests"], False),
        ("mission_control_tasks", "tasks.jsonl", rows["tasks"], True),
        ("mission_control_project", "project.jsonl", rows["project"], False),
        ("mission_control_decisions", "decisions.jsonl", [], True),
        ("mission_control_coordination", "coordination.jsonl", [], True),
        ("git_ctower", "git.jsonl", [], True),
        ("github_ctower", "github.jsonl", [], True),
    )
    for key, path, source_rows, expected_zero in source_specs:
        data = b"".join(canonical_bytes(row) + b"\n" for row in source_rows)
        (root / path).write_bytes(data)
        selected = [row for row in source_rows if row["review_decision"] == "included"]
        logical = {
            (
                row["identity"]["namespace"],
                row["identity"]["immutable_source_id"],
                row["identity"]["source_version"],
            )
            for row in selected
        }
        inventories.append(
            _inventory(
                key,
                path,
                data,
                len(source_rows),
                len(logical),
                len(selected),
                expected_zero=expected_zero,
            )
        )
    inventories.append(_target_source_inventory())
    return inventories


def _source_rows(
    request_ids: list[str], stable_ids: list[str], checkpoints: list[str]
) -> dict[str, list[dict[str, Any]]]:
    request_rows: list[dict[str, Any]] = []
    for index, source_id in enumerate(request_ids):
        copies = 3 if index < THREE_SNAPSHOT_ITEM_COUNT else 2
        request_rows.extend(
            _record(
                "mission-control:request",
                source_id,
                title=f"Reviewed migration request {source_id}",
            )
            for _ in range(copies)
        )
    tasks = [
        _record(
            "mission-control:request",
            source_id,
            decision="excluded",
            title=None,
        )
        for source_id in ("R546", "R669+")
    ]
    project = [
        *[_record("stable-backlog", source_id, title=None) for source_id in stable_ids],
        *[_record("catalog:ctower:checkpoint", source_id, title=None) for source_id in checkpoints],
    ]
    return {"requests": request_rows, "tasks": tasks, "project": project}


def _record(
    namespace: str,
    source_id: str,
    *,
    decision: str = "included",
    title: str | None,
) -> dict[str, Any]:
    return {
        "schema": "ctower.synthetic-migration-source/v1",
        "identity": _identity(namespace, source_id),
        "candidate": True,
        "review_decision": decision,
        "data_classes": ["migration_provenance"],
        "title": title,
        "operation_hint": None,
    }


def _identity(namespace: str, source_id: str) -> dict[str, str]:
    return {
        "namespace": namespace,
        "immutable_source_id": source_id,
        "source_version": "reviewed-v1",
        "source_digest": sha256_digest(f"{namespace}:{source_id}".encode()),
    }


def _inventory(
    key: str,
    path: str,
    data: bytes,
    rows: int,
    logical: int,
    physical: int,
    *,
    expected_zero: bool,
) -> dict[str, Any]:
    authority = (
        "external_native_authority"
        if key in {"git_ctower", "github_ctower"}
        else "migration_provenance"
    )
    return {
        "source_key": key,
        "authority_class": authority,
        "path": path,
        "whole_source_digest": sha256_digest(data),
        "whole_source_bytes": len(data),
        "whole_source_rows": rows,
        "selected_logical_items": logical,
        "selected_physical_items": physical,
        "expected_zero": expected_zero,
        "watermark": f"bytes:{len(data)}",
    }


def _target_source_inventory() -> dict[str, Any]:
    return {
        "source_key": "ctower_target",
        "authority_class": "target_inventory",
        "path": None,
        "whole_source_digest": sha256_digest(b""),
        "whole_source_bytes": 0,
        "whole_source_rows": 0,
        "selected_logical_items": 0,
        "selected_physical_items": 0,
        "expected_zero": True,
        "watermark": "record:0/projection:0",
    }


def _selection(
    signer: ArtifactSigner,
    requests: list[str],
    stable: list[str],
    checkpoints: list[str],
    inventories: list[dict[str, Any]],
) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema": "ctower.ctower-project-source-selection/v1",
        "selection_id": str(uuid5(UUID_NAMESPACE, "selection")),
        "revision": 1,
        "cutover_scope": {
            "tenant_key": "ctower",
            "company_key": "ctower",
            "project_key": "ctower",
            "repository": "github.com/simjak/ctower",
        },
        "canonicalization": "RFC8785",
        "created_at": REVIEW["reviewed_at"],
        "stable_item_ids": stable,
        "checkpoint_keys": checkpoints,
        "selected_request_ids": requests,
        "selected_task_ids": [],
        "explicit_exclusions": [
            {"source_id": "R546", "reason_code": "reviewed_false_positive"},
            {"source_id": "R669+", "reason_code": "outside_signed_baseline"},
        ],
        "source_inventories": inventories,
        "forbidden_classes": FORBIDDEN,
        "review": REVIEW,
    }
    return signer.seal(artifact, "manifest_digest")


def _target_inventory() -> dict[str, Any]:
    digest = sha256_digest(b"synthetic-target")
    target: dict[str, Any] = {
        "tenant_key": "ctower",
        "company_key": "ctower",
        "project_key": "ctower",
        "catalog_revision_digest": digest,
        "record_position": 0,
        "projection_watermark": 0,
        "schema_digest": sha256_digest(b"schema"),
        "build_digest": sha256_digest(b"build"),
        "client_digest": sha256_digest(b"client"),
        "operation_registry_digest": sha256_digest(b"operations"),
        "explicit_zero_sources": [
            "root_supervisor",
            "effect_provider",
            "runtime_provider",
        ],
    }
    target["inventory_digest"] = canonical_digest(target)
    return target


def _disposition(
    index: int,
    checkpoints: list[str],
    *,
    existing_ticket_id: UUID | None,
) -> tuple[str, str | None]:
    disposition = DISPOSITIONS[index]
    target: str | None
    match disposition:
        case "created_ticket":
            target = "new_ticket"
        case "alias_linked_existing" | "provenance_only" | "exact_duplicate":
            target = (
                f"ticket:{existing_ticket_id}"
                if existing_ticket_id is not None
                else _ticket_target(index)
            )
        case "project_checkpoint_definition":
            target = f"checkpoint:{checkpoints[index - CHECKPOINT_DISPOSITION_START]}"
        case "decision_link":
            target = f"decision:D{index}"
        case "external_effect_link":
            target = f"external-effect:effect-{index}"
        case "artifact_linked_not_proof":
            target = f"artifact:artifact-{index}"
        case _:
            target = None
    return disposition, target


def _ticket_target(index: int) -> str:
    ticket_id = uuid5(UUID_NAMESPACE, f"ticket:{index}")
    return f"ticket:{ticket_id}"
