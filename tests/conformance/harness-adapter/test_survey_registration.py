"""CT-I1-044 — later-wave survey completeness and refusal proof."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

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


def _candidates() -> dict[str, dict[str, Any]]:
    return {
        candidate["key"]: candidate
        for candidate in cast(list[dict[str, Any]], _document()["candidates"])
    }


def test_authored_survey_is_strict_and_revision_pinned() -> None:
    document = _document()
    errors = sorted(
        Draft202012Validator(_schema()).iter_errors(document), key=lambda error: error.json_path
    )

    assert not [f"{error.json_path}: {error.message}" for error in errors]
    assert document["schema"] == "ctower.later-wave-harness-survey/v1"
    assert document["revision"] == 1
    assert tuple(candidate["key"] for candidate in document["candidates"]) == _CANDIDATES


def test_each_candidate_answers_all_ten_questions_with_explicit_state() -> None:
    candidates = _candidates()

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
    candidates = _candidates()

    for key in ("openclaw", "qwen-code", "zcode"):
        candidate = candidates[key]
        assert candidate["role_disposition"] == "undecidable"
        assert candidate["registration"]["status"] == "refused"
        assert candidate["capability_declaration"]["liveness"] == "unknown"


def test_deepseek_is_a_model_route_with_zero_adapter_work() -> None:
    deepseek = _candidates()["deepseek"]

    assert deepseek["classification"] == "model"
    assert deepseek["effective_route"] == "hermes-profile"
    assert deepseek["role_disposition"] == "not_applicable"
    assert deepseek["registration"]["status"] == "not_applicable"
    assert deepseek["adapter_work"] == "zero"
    assert deepseek["capability_declaration"]["liveness"] == "inherited:hermes.gateway_log"
