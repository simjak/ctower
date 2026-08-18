from __future__ import annotations

import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]


def test_http_principals_match_the_executable_capability_matrix() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    vectors = json.loads(
        (ROOT / "contracts/domain/migration/migration-vectors.json").read_text(encoding="utf-8")
    )
    matrix = cast(dict[str, list[str]], vectors["capability_matrix"])
    actual: dict[str, set[str]] = {
        "operator": set(),
        "migration_importer": set(),
        "fence_observer": set(),
    }
    for path in cast(dict[str, dict[str, object]], document["paths"]).values():
        for method, raw in path.items():
            if method not in {"get", "post"}:
                continue
            operation = cast(dict[str, object], raw)
            principal = operation.get("x-ctower-principal")
            if isinstance(principal, str) and principal in actual:
                operation_id = cast(str, operation["operationId"])
                suffix = ":refusal_only" if operation.get("x-ctower-refusal-only") else ""
                actual[principal].add(operation_id + suffix)
    for principal, operations in actual.items():
        assert operations == set(matrix[principal])
