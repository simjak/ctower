"""Authored boundaries for the Phase-1 Request authority candidate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()

_REQUEST_OPERATIONS = {
    "assignRequestOwner",
    "captureRequest",
    "evaluateRequestClosure",
    "listRequests",
    "mergeResemblingRequest",
    "prioritizeRequest",
    "relateRequestTicket",
    "setRequestBlocker",
    "triageRequest",
}


def test_request_http_surface_is_strict_generated_and_phase_one_only() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    operations = {
        cast(str, operation["operationId"]): operation
        for path in cast(dict[str, dict[str, object]], document["paths"]).values()
        for method, operation in path.items()
        if method in {"get", "post"} and isinstance(operation, dict)
    }

    assert operations.keys() >= _REQUEST_OPERATIONS
    assert operations["captureRequest"]["x-ctower-cli"] == "request capture"
    assert operations["captureRequest"]["x-ctower-spool"] == "allowed"
    assert operations["listRequests"]["x-ctower-spool"] == "forbidden"
    assert operations["listRequests"]["x-ctower-mutation"] is False
    assert operations["mergeResemblingRequest"]["x-ctower-cli"] == "request same"
    assert not any("slack" in name.casefold() for name in operations)
    assert not any("importrequest" in name.casefold() for name in operations)


def test_request_storage_has_one_allocator_and_append_only_semantic_facts() -> None:
    migration = (ROOT / "packages/ctower-kernel/migrations/0059_request_authority.sql").read_text(
        encoding="utf-8"
    )

    assert migration.count("CREATE TABLE request_number_allocators") == 1
    assert "UNIQUE (tenant_id, request_number)" in migration
    assert "UNIQUE (tenant_id, source_kind, source_ref)" in migration
    assert "CREATE TABLE request_ticket_holders" in migration
    assert "PRIMARY KEY (tenant_id, ticket_id)" in migration
    assert "CREATE TRIGGER request_ticket_relation_holder_projection" in migration
    for table in (
        "request_owner_facts",
        "request_priority_facts",
        "request_triage_facts",
        "request_ticket_relation_facts",
        "request_blocker_facts",
        "request_closure_evaluations",
        "request_attention_facts",
        "request_import_manifests",
        "request_native_capture_fences",
    ):
        assert f"CREATE TRIGGER {table}_immutable" in migration
    resemblance = (
        ROOT / "packages/ctower-kernel/migrations/0064_request_resemblance.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TRIGGER request_resemblance_links_immutable" in resemblance
    assert "CREATE TRIGGER request_merge_facts_immutable" in resemblance
    assert "GRANT UPDATE (last_number, advanced_at) ON request_number_allocators" in migration
    assert "GRANT UPDATE (version) ON requests" in migration
