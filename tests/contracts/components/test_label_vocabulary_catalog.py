"""Label vocabularies are versioned configured data, never a product roster."""

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
SCHEMA_PATH = ROOT / "contracts/components/label-vocabulary.schema.json"
VECTOR_PATH = ROOT / "contracts/components/label-vocabulary-vectors.json"
PRODUCT_ROOTS = (ROOT / "packages", ROOT / "apps")


def test_label_vocabulary_mutation_changes_surface_without_product_code_edit() -> None:
    """AC-TM-07: add/remove/rename/reorder all come only from fixture data."""

    validator = _validator()
    revisions = cast(
        list[dict[str, object]],
        json.loads(VECTOR_PATH.read_text(encoding="utf-8"))["label_vocabulary_revisions"],
    )
    rendered: list[tuple[tuple[str, str], ...]] = []
    for revision in revisions:
        payload = {
            "schema": "ctower.label-vocabulary/v1",
            "key": revision["catalog_key"],
            "display_name": f"Configured labels revision {revision['revision']}",
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
    assert dict(before).get("security") != dict(after).get("security"), (
        "configured rename must alter the surface"
    )
    assert tuple(key for key in after_keys if key in before_keys) != tuple(
        key for key in before_keys if key in after_keys
    ), "configured reorder must alter the surface"


def test_product_code_has_no_configured_label_key_branch() -> None:
    """Named RED gate: any configured label-key literal in product code fails."""

    vectors = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    revisions = cast(list[dict[str, object]], vectors["label_vocabulary_revisions"])
    configured_keys = {
        str(member["key"])
        for revision in revisions
        for member in cast(list[dict[str, object]], revision["members"])
    }
    hits: list[str] = []
    for root in PRODUCT_ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            hits.extend(
                f"{path.relative_to(ROOT)}:{node.lineno}:{node.value!s}"
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and node.value in configured_keys
            )
    assert hits == [], "configured label keys reached product code: " + ", ".join(hits)


def test_label_vocabulary_rejects_duplicate_keys_even_when_labels_differ() -> None:
    validator = _validator()
    payload = {
        "schema": "ctower.label-vocabulary/v1",
        "key": "board.ticket-labels",
        "display_name": "Ticket labels",
        "members": [
            {"key": "security", "label": "First label"},
            {"key": "security", "label": "Second label"},
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
