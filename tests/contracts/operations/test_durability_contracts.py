"""Authored durability-policy, acknowledgement, and health contracts."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]
OPERATIONS = ROOT / "contracts/operations"


def test_durability_contracts_are_strict_draft_2020_12_schemas() -> None:
    names = {
        "durability-policy.schema.json",
        "durability-ack.schema.json",
        "health.schema.json",
    }

    assert names <= {path.name for path in OPERATIONS.glob("*.schema.json")}
    for name in names:
        schema = json.loads((OPERATIONS / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False


def test_policy_has_one_development_only_ack_mode_and_global_cursor() -> None:
    policy = json.loads((OPERATIONS / "durability-policy.schema.json").read_text(encoding="utf-8"))
    acknowledgement = json.loads(
        (OPERATIONS / "durability-ack.schema.json").read_text(encoding="utf-8")
    )

    assert policy["properties"]["mode"]["enum"] == [
        "pending_only",
        "development_offhost_ack",
        "cutover_rpo0",
    ]
    assert policy["properties"]["synchronous_commit"]["const"] == "remote_apply"
    assert policy["properties"]["standby_count"]["const"] == 1
    assert "acceptance_position" in acknowledgement["required"]
    assert acknowledgement["properties"]["command_root"]["pattern"] == ("^sha256:[0-9a-f]{64}$")


def test_http_contract_declares_pending_and_accepted_mutation_outcomes() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    paths = document["paths"]
    expected_read_only_posts = {"planCompanyBundle", "validateCompanyBundle"}
    read_only_posts: set[str] = set()

    assert schemas["DurabilityState"]["enum"] == ["durability_pending", "accepted"]
    for path in paths.values():
        for method, operation in path.items():
            operation_id = operation["operationId"]
            responses = operation["responses"]
            if operation_id in expected_read_only_posts:
                assert method == "post"
                assert operation["x-ctower-mutation"] is False
                assert operation["x-ctower-spool"] == "forbidden"
                assert "200" in responses
                assert "202" not in responses
                read_only_posts.add(operation_id)
            if operation["x-ctower-mutation"] is True:
                assert "202" in responses, operation_id
                assert "Retry-After" in responses["202"]["headers"], operation_id

    assert read_only_posts == expected_read_only_posts
