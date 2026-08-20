"""CT-I1-044 — later-wave survey completeness and refusal proof."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA = _ROOT / "contracts/runner/later-wave-harness-survey.schema.json"
_SURVEY = _ROOT / "contracts/runner/later-wave-harness-survey.json"
_QUESTIONS = (
    "native_pool",
    "native_fallback",
    "config_surface",
    "identity_proof",
    "reset_window_semantics",
    "rotation_cache_semantics",
    "subagent_credential_inheritance",
    "egress_topology",
    "probe_target",
    "credit_weights",
)
_CANDIDATES = ("openclaw", "qwen-code", "zcode", "deepseek")


def _document() -> dict[str, Any]:
    assert _SURVEY.is_file(), f"missing authored survey: {_SURVEY}"
    return cast(dict[str, Any], json.loads(_SURVEY.read_text(encoding="utf-8")))


def _schema() -> dict[str, Any]:
    assert _SCHEMA.is_file(), f"missing survey schema: {_SCHEMA}"
    return cast(dict[str, Any], json.loads(_SCHEMA.read_text(encoding="utf-8")))


def _candidates(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        candidate["key"]: candidate
        for candidate in cast(list[dict[str, Any]], document["candidates"])
    }


def _errors(document: dict[str, Any]) -> list[str]:
    errors = sorted(
        Draft202012Validator(_schema()).iter_errors(document), key=lambda error: error.json_path
    )
    return [f"{error.json_path}: {error.message}" for error in errors]


def test_authored_survey_is_strict_and_revision_pinned() -> None:
    document = _document()
    errors = _errors(document)

    assert not errors
    assert document["schema"] == "ctower.later-wave-harness-survey/v1"
    assert document["revision"] == 1
    assert tuple(candidate["key"] for candidate in document["candidates"]) == _CANDIDATES


def test_each_candidate_answers_all_ten_questions_with_explicit_state() -> None:
    candidates = _candidates(_document())

    assert tuple(candidates) == _CANDIDATES
    for candidate in candidates.values():
        answers = candidate["answers"]
        assert tuple(answers) == _QUESTIONS
        for question in _QUESTIONS:
            answer = answers[question]
            assert answer["state"] in {"verified", "not_applicable", "unverified"}
            if answer["state"] == "unverified":
                assert answer["value"] is None
                assert answer["evidence"]


def test_unresolved_harness_roles_refuse_registration_instead_of_guessing_never_both() -> None:
    candidates = _candidates(_document())

    for key in ("openclaw", "qwen-code", "zcode"):
        candidate = candidates[key]
        assert candidate["role_disposition"] == "undecidable"
        assert candidate["registration"]["status"] == "refused"
        assert candidate["capability_declaration"]["liveness"] == "unknown"


def test_deepseek_is_a_model_route_with_zero_adapter_work() -> None:
    deepseek = _candidates(_document())["deepseek"]

    assert deepseek["classification"] == "model"
    assert deepseek["effective_route"] == "hermes-profile"
    assert deepseek["role_disposition"] == "not_applicable"
    assert deepseek["registration"]["status"] == "not_applicable"
    assert deepseek["adapter_work"] == "zero"
    assert deepseek["capability_declaration"]["liveness"] == "inherited:hermes.gateway_log"


def _temporal_paradox(document: dict[str, Any]) -> None:
    document["observed_at"] = "1970-01-01T00:00:00Z"


def _weekly_plan_with_absence_only_evidence(document: dict[str, Any]) -> None:
    _candidates(document)["qwen-code"]["answers"]["reset_window_semantics"]["evidence"] = [
        "local-command-absence"
    ]


def _config_surface_with_absence_only_evidence(document: dict[str, Any]) -> None:
    _candidates(document)["qwen-code"]["answers"]["config_surface"]["evidence"] = [
        "local-command-absence"
    ]


def _refused_registration_with_active_reason(document: dict[str, Any]) -> None:
    _candidates(document)["openclaw"]["registration"]["reason"] = "registered and active"


def _unknown_liveness_with_positive_reason(document: dict[str, Any]) -> None:
    _candidates(document)["qwen-code"]["capability_declaration"]["reason"] = (
        "Serving was observed and the candidate is healthy."
    )


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            _temporal_paradox,
            id="judge-temporal-paradox-observed-before-source",
        ),
        pytest.param(
            _weekly_plan_with_absence_only_evidence,
            id="judge-verified-weekly-plan-with-absence-only-evidence",
        ),
        pytest.param(
            _config_surface_with_absence_only_evidence,
            id="own-verified-config-with-absence-only-evidence",
        ),
        pytest.param(
            _refused_registration_with_active_reason,
            id="own-refused-registration-with-active-reason",
        ),
        pytest.param(
            _unknown_liveness_with_positive_reason,
            id="own-unknown-liveness-with-positive-reason",
        ),
    ],
)
def test_semantically_impossible_surveys_are_refused(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    document = copy.deepcopy(_document())
    mutation(document)

    assert _errors(document), "semantically impossible survey was accepted"
