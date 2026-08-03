"""Authored `ctower.workflow-definition/v1` source contract evidence.

The positive fixture is the operator-approved S8 Workflow YAML from the reviewed
`mockups/ctower-ui/workflow.html` screen, kept as the document rather than as bytes:
comments and layout are not authoritative, the declared members are.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from ruamel.yaml import YAML

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
FIXTURES = Path(__file__).parent / "fixtures"
_REFERENCED = (
    "contracts/components/versioned-component.schema.json",
    "contracts/company/company-bundle.schema.json",
)


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _yaml(path: Path) -> dict[str, Any]:
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    yaml.allow_duplicate_keys = False
    return cast(dict[str, Any], yaml.load(path.read_text(encoding="utf-8")))


def _validator() -> Draft202012Validator:
    schema = _load(ROOT / "contracts/workflow/workflow-definition.schema.json")
    registry = Registry()
    for relative in _REFERENCED:
        document = _load(ROOT / relative)
        registry = registry.with_resource(
            cast(str, document["$id"]), Resource.from_contents(document)
        )
    return Draft202012Validator(schema, registry=registry)


def _approved() -> dict[str, Any]:
    return _yaml(FIXTURES / "approved-s8-workflow.yaml")


def test_the_approved_s8_mockup_is_source_schema_valid() -> None:
    _validator().validate(_approved())


def test_a_complete_revision_is_source_schema_valid() -> None:
    _validator().validate(_yaml(FIXTURES / "complete-workflow-definition.yaml"))


def test_the_approved_fixture_keeps_the_reviewed_spelling() -> None:
    document = _approved()

    assert document["apiVersion"] == "ctower/v1"
    assert document["kind"] == "Workflow"
    assert document["metadata"]["name"] == "engineering.software-factory"
    assert [stage["name"] for stage in document["spec"]["stages"]] == [
        "intake",
        "build",
        "review",
        "qa",
    ]
    edge = document["spec"]["transitions"][0]
    assert (edge["from"], edge["to"], edge["on_missing"]) == ("build", "review", "refuse")
    assert list(document["overlays"]) == ["lastmachines", "bh-loop"]


def test_the_approved_fixture_declares_no_defaultable_member() -> None:
    document = _approved()

    assert "stage_groups" not in document["spec"]
    for stage in document["spec"]["stages"]:
        assert set(stage) == {"name", "owner", "evidence"}


def test_published_key_scalars_carry_the_authored_contracts_by_reference() -> None:
    schema = _load(ROOT / "contracts/workflow/workflow-definition.schema.json")
    definitions = schema["$defs"]

    assert definitions["publishedComponentKey"]["$ref"] == (
        "../components/versioned-component.schema.json#/properties/key"
    )
    assert definitions["publishedCompanyKey"]["$ref"] == (
        "../company/company-bundle.schema.json#/properties/company/properties/key"
    )
    assert "pattern" not in definitions["publishedComponentKey"]
    assert "pattern" not in definitions["publishedCompanyKey"]
    assert definitions["sourceKey"]["pattern"] == "^[a-z][a-z0-9._-]{0,127}$"


@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        (("metadata", "name"), "ab"),
        (("metadata", "name"), "my_workflow"),
        (("metadata", "company"), "jl"),
        (("metadata", "revision"), 0),
        (("apiVersion",), "ctower/v2"),
        (("kind",), "Pipeline"),
    ],
)
def test_a_key_or_literal_the_authored_contracts_refuse_is_refused(
    pointer: tuple[str, ...],
    value: object,
) -> None:
    document = _approved()
    target = document
    for step in pointer[:-1]:
        target = target[step]
    target[pointer[-1]] = value

    assert not _validator().is_valid(document)


def test_a_source_local_key_shorter_than_a_catalog_key_is_accepted() -> None:
    document = _approved()
    document["spec"]["stages"][3]["name"] = "qa"

    assert _validator().is_valid(document)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda doc: doc.update(extras=1), id="unknown-top-level-member"),
        pytest.param(
            lambda doc: doc["spec"]["stages"][0].update(rubber_stamp=True),
            id="unknown-stage-member",
        ),
        pytest.param(
            lambda doc: doc["spec"]["stages"][0]["evidence"][0].update(required=False),
            id="relaxed-required",
        ),
        pytest.param(
            lambda doc: doc["spec"]["stages"][3]["evidence"][0].update(widths=[1]),
            id="width-outside-the-declared-range",
        ),
        pytest.param(
            lambda doc: doc["spec"]["stages"][0].update(evidence=[]),
            id="empty-evidence-list",
        ),
        pytest.param(
            lambda doc: doc["spec"]["transitions"][0].update(on_missing="warn"),
            id="unsupported-on-missing",
        ),
        pytest.param(lambda doc: doc["spec"].pop("transitions"), id="missing-transitions"),
    ],
)
def test_structure_outside_the_closed_vocabulary_is_refused(
    mutate: Callable[[dict[str, Any]], object],
) -> None:
    document = _approved()
    mutate(document)

    assert not _validator().is_valid(document)
