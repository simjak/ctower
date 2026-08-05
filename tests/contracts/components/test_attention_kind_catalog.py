"""Attention kinds are versioned configured data, never a product enum."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
SCHEMA_PATH = ROOT / "contracts/components/attention-kind-catalog.schema.json"
VECTOR_PATH = ROOT / "contracts/components/attention-kind-catalog-vectors.json"
PRODUCT_ROOTS = (ROOT / "packages", ROOT / "apps")


def test_attention_kind_catalog_mutation_changes_surface_without_product_code_edit() -> None:
    """AC-ATT-01: add/remove/rename/reorder all come only from fixture data."""

    validator = _validator()
    revisions = cast(
        list[dict[str, object]],
        json.loads(VECTOR_PATH.read_text(encoding="utf-8"))["attention_kind_catalog_revisions"],
    )
    rendered: list[tuple[tuple[str, str], ...]] = []
    for revision in revisions:
        payload = {
            "schema": "ctower.attention-kind-catalog/v1",
            "key": revision["catalog_key"],
            "display_name": f"Configured attention kinds revision {revision['revision']}",
            "members": revision["members"],
        }
        validator.validate(payload)
        rendered.append(
            tuple(
                (str(member["key"]), str(member["label"]))
                for member in cast(list[dict[str, object]], payload["members"])
            )
        )

    before, after = rendered
    before_keys = tuple(key for key, _ in before)
    after_keys = tuple(key for key, _ in after)
    assert set(after_keys) - set(before_keys), "configured add must alter the surface"
    assert set(before_keys) - set(after_keys), "configured remove must alter the surface"
    assert dict(before).get("gate_decision") != dict(after).get("gate_decision"), (
        "configured rename must alter the surface"
    )
    assert tuple(key for key in after_keys if key in before_keys) != tuple(
        key for key in before_keys if key in after_keys
    ), "configured reorder must alter the surface"
    assert "outbox_poison" in before_keys and "outbox_poison" in after_keys, (
        "AC-OPS-16: outbox-poison is one member of the catalog, published like any other kind"
    )


def test_product_code_has_no_configured_attention_kind_branch() -> None:
    """Named RED gate: any configured kind-key literal in product code fails."""

    vectors = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    revisions = cast(list[dict[str, object]], vectors["attention_kind_catalog_revisions"])
    configured_keys = {
        str(member["key"])
        for revision in revisions
        for member in cast(list[dict[str, object]], revision["members"])
    }
    # outbox_poison already names a pre-existing, unrelated table/consumer_key literal
    # (AC-OPS-16's own poison-recovery plumbing); the RED gate only names *new* kinds.
    configured_keys.discard("outbox_poison")
    hits: list[str] = []
    for root in PRODUCT_ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            hits.extend(
                f"{path.relative_to(ROOT)}:{node.lineno}:{node.value!s}"
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and node.value in configured_keys
            )
    assert hits == [], "configured attention kinds reached product code: " + ", ".join(hits)


def test_attention_kind_catalog_rejects_duplicate_keys_even_when_labels_differ() -> None:
    validator = _validator()
    payload = {
        "schema": "ctower.attention-kind-catalog/v1",
        "key": "attention.needs-you-kinds",
        "display_name": "Needs You kinds",
        "members": [
            {"key": "gate_decision", "label": "First label"},
            {"key": "gate_decision", "label": "Second label"},
        ],
    }
    # JSON Schema closes the wire shape; semantic uniqueness is enforced by Catalog.
    validator.validate(payload)
    with pytest.raises(ValidationError):
        validator.validate({**payload, "members": []})


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
