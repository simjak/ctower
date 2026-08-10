"""Typed internal commands and evidence for the one-way Request cutover."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

__all__ = [
    "RequestBatchProof",
    "RequestCutoverComplete",
    "RequestCutoverImport",
    "RequestCutoverPrepare",
    "RequestCutoverResult",
    "RequestImportReconciliation",
]


@dataclass(frozen=True, slots=True)
class RequestCutoverPrepare:
    client_command_id: UUID
    manifest: str
    fence: str
    reviewer_public_key_pem: str

    def request_payload(self) -> dict[str, object]:
        return {
            "fence": self.fence,
            "manifest": self.manifest,
            "reviewer_public_key_pem": self.reviewer_public_key_pem,
        }


@dataclass(frozen=True, slots=True)
class RequestCutoverImport:
    client_command_id: UUID
    manifest_digest: str
    source_request_id: str
    content: str
    fence: str
    reviewer_public_key_pem: str

    def request_payload(self) -> dict[str, object]:
        return {
            "content": self.content,
            "fence": self.fence,
            "manifest_digest": self.manifest_digest,
            "reviewer_public_key_pem": self.reviewer_public_key_pem,
            "source_request_id": self.source_request_id,
        }


@dataclass(frozen=True, slots=True)
class RequestBatchProof:
    client_command_id: UUID
    proof: str
    reviewer_public_key_pem: str

    def request_payload(self) -> dict[str, object]:
        return {"proof": self.proof, "reviewer_public_key_pem": self.reviewer_public_key_pem}


@dataclass(frozen=True, slots=True)
class RequestCutoverComplete:
    client_command_id: UUID
    manifest_digest: str
    final_fence: str
    reviewer_public_key_pem: str

    def request_payload(self) -> dict[str, object]:
        return {
            "final_fence": self.final_fence,
            "manifest_digest": self.manifest_digest,
            "reviewer_public_key_pem": self.reviewer_public_key_pem,
        }


@dataclass(frozen=True, slots=True)
class RequestCutoverResult:
    command_id: UUID
    operation: str
    manifest_digest: str
    state: str
    imported_count: int
    target_watermark: int
    request_id: UUID | None = None
    request_number: int | None = None
    event_ids: tuple[UUID, ...] = ()

    def response_payload(self) -> dict[str, object]:
        return {
            "accepted_position": None,
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "imported_count": self.imported_count,
            "manifest_digest": self.manifest_digest,
            "operation": self.operation,
            "request_id": None if self.request_id is None else str(self.request_id),
            "request_number": self.request_number,
            "state": self.state,
            "target_watermark": self.target_watermark,
        }


@dataclass(frozen=True, slots=True)
class RequestImportReconciliation:
    manifest_digest: str
    batch_index: int
    source_count: int
    source_count_by_project: dict[str, int]
    batch_target_count: int
    batch_target_count_by_project: dict[str, int]
    cumulative_count: int
    cumulative_count_by_project: dict[str, int]
    target_count: int
    target_count_by_project: dict[str, int]
    target_watermark: int
    rows: tuple[dict[str, object], ...]
    sample_ids: tuple[str, ...]

    def response_payload(self) -> dict[str, object]:
        return {
            "batch_index": self.batch_index,
            "batch_target_count": self.batch_target_count,
            "batch_target_count_by_project": _project_count_items(
                self.batch_target_count_by_project
            ),
            "cumulative_count": self.cumulative_count,
            "cumulative_count_by_project": _project_count_items(self.cumulative_count_by_project),
            "manifest_digest": self.manifest_digest,
            "rows": list(self.rows),
            "sample_ids": list(self.sample_ids),
            "source_count": self.source_count,
            "source_count_by_project": _project_count_items(self.source_count_by_project),
            "target_count": self.target_count,
            "target_count_by_project": _project_count_items(self.target_count_by_project),
            "target_watermark": self.target_watermark,
        }


def _project_count_items(counts: dict[str, int]) -> list[dict[str, object]]:
    return [
        {"project_key": project_key, "count": count}
        for project_key, count in sorted(counts.items())
    ]
