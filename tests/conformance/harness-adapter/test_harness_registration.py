"""AC-HAD-01 — what may register, and what may publish.

Registration is where the survey decides the per-layer role and where `never both` is
enforced. Publication is stricter and separate: with one real binding the public Seam does
not publish, and it says so by name rather than by staying quiet.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from harness_subjects import (
    fake_document,
    hermes_document,
    registration_route,
    registered_registry,
    subjects,
)

from ctower_runner_sdk.conformance import ConformanceSubject
from ctower_runner_sdk.refusals import SEAM_MINTED, SPEC_OWNED, Refusal
from ctower_runner_sdk.registry import REQUIRED_REAL_BINDINGS, HarnessRegistry
from ctower_runner_sdk.spec import HarnessSpec
from ctower_runner_sdk.survey import SURVEY_QUESTIONS, derive_roles

__all__: tuple[str, ...] = ()

_VECTORS = Path(__file__).resolve().parents[3] / "contracts/runner/harness-spec-vectors.json"


def _vectors() -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    payload = json.loads(_VECTORS.read_text(encoding="utf-8"))
    return payload["base"], payload["vectors"]


def _document(base: Mapping[str, Any], vector: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild the accepted document, then apply exactly this vector's one difference."""

    document: dict[str, Any] = json.loads(json.dumps(base))
    document.update(vector.get("override", {}))
    for path in vector.get("remove", []):
        section, _, field = path.partition(".")
        document[section].pop(field)
    return document


@pytest.mark.parametrize("vector", _vectors()[1], ids=lambda item: str(item["name"]))
def test_every_authored_vector_registers_or_refuses_exactly_as_declared(
    vector: Mapping[str, Any],
) -> None:
    base, _ = _vectors()
    outcome = HarnessRegistry().register(
        _document(base, vector), "real", route=registration_route(dict(base))
    )

    if vector["outcome"] == "registered":
        assert isinstance(outcome, HarnessSpec), outcome
        assert outcome.layers.to_mapping() == vector["roles"]
        return
    assert isinstance(outcome, Refusal), outcome
    assert outcome.name == vector["refusal"]


def test_the_role_table_is_derived_from_surveys_and_not_from_harness_names() -> None:
    rows = registered_registry().role_table()

    assert [row.harness_key for row in rows] == ["fault-injection-fake", "hermes"]
    for row in rows:
        expected = {
            "pool": "configure" if row.native_pool else "provide",
            "fallback": "configure" if row.native_fallback else "provide",
        }
        assert row.roles.to_mapping() == expected, row.to_mapping()


def test_the_survey_has_no_unanswered_question_in_either_binding() -> None:
    for document in (hermes_document(), fake_document()):
        survey = document["survey"]
        assert isinstance(survey, dict)
        assert tuple(sorted(survey)) == tuple(sorted(SURVEY_QUESTIONS))


def test_one_real_binding_does_not_publish_the_seam() -> None:
    registry = HarnessRegistry()
    registry.register(hermes_document(), "real", route=registration_route(hermes_document()))
    registry.register(
        fake_document(), "fault_injection_fake", route=registration_route(fake_document())
    )

    refusal = registry.publication()

    assert isinstance(refusal, Refusal)
    assert refusal.name == "harness-seam-unpublished"
    assert len(registry.real_bindings()) < REQUIRED_REAL_BINDINGS
    assert str(REQUIRED_REAL_BINDINGS) in refusal.action


def test_a_duplicate_declaration_is_rejected_at_registration_not_at_runtime() -> None:
    registry = HarnessRegistry()
    registry.register(hermes_document(), "real", route=registration_route(hermes_document()))

    again = registry.register(
        hermes_document(), "real", route=registration_route(hermes_document())
    )

    assert isinstance(again, Refusal)
    assert again.name == "harness-spec-incompatible"


def test_an_unknown_harness_value_is_refused_and_echoed_byte_for_byte() -> None:
    observed = "Hermes-Fork_2 (unregistered)"

    refusal = registered_registry().resolve(observed)

    assert isinstance(refusal, Refusal)
    assert refusal.name == "harness-spec-unknown"
    assert dict(refusal.detail)["harness_ref"] == observed


def test_every_refusal_the_seam_mints_is_new_and_every_reused_name_is_spec_owned() -> None:
    assert not SEAM_MINTED & SPEC_OWNED
    assert all(name.count(" ") == 0 and name == name.lower() for name in SEAM_MINTED)


@pytest.mark.parametrize("subject", subjects(), ids=lambda item: item.name)
def test_every_subject_declares_the_role_its_own_survey_implies(
    subject: ConformanceSubject,
) -> None:
    spec = subject.binding.spec

    assert derive_roles(spec.survey) == spec.layers
