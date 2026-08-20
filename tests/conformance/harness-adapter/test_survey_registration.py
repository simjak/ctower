"""CT-I1-044 — later-wave survey completeness and derived refusal proof."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA = _ROOT / "contracts/runner/later-wave-harness-survey.schema.json"
_SURVEY = _ROOT / "contracts/runner/later-wave-harness-survey.json"
_MATRIX = _ROOT / "contracts/runner/later-wave-harness-survey.matrix.json"
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
_MATRIX_SHA256 = "a86bf1e65d65dc12fac8696d73cc1e370edb6a8a6421b42799d354aae3c63066"
_MATRIX_PAIR_COUNT = 45
Violation = tuple[str, str, str, str, str, str]


def _document() -> dict[str, Any]:
    assert _SURVEY.is_file(), f"missing authored survey: {_SURVEY}"
    return cast(dict[str, Any], json.loads(_SURVEY.read_text(encoding="utf-8")))


def _schema() -> dict[str, Any]:
    assert _SCHEMA.is_file(), f"missing survey schema: {_SCHEMA}"
    return cast(dict[str, Any], json.loads(_SCHEMA.read_text(encoding="utf-8")))


def _matrix() -> dict[str, Any]:
    assert _MATRIX.is_file(), f"missing dependency matrix: {_MATRIX}"
    return cast(dict[str, Any], json.loads(_MATRIX.read_text(encoding="utf-8")))


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


def _token_values(matrix: dict[str, Any], question: str) -> list[str]:
    return cast(dict[str, list[str]], matrix["domains"])[question]


def _derived_violation_set() -> tuple[Violation, ...]:
    """Derive cases from matrix rules; no hand-picked survey is the mechanism."""
    matrix = _matrix()
    pairs = cast(list[dict[str, Any]], matrix["pairs"])
    rules = cast(dict[str, dict[str, Any]], matrix["rules"])
    cases: list[Violation] = []
    for pair in pairs:
        left = cast(str, pair["left"])
        right = cast(str, pair["right"])
        for rule_id in cast(list[str], pair["rules"]):
            rule = rules[rule_id]
            if rule_id == "model-route-coherence":
                cases.extend(
                    ("qwen-code", left, "model_route", right, answer_value, rule_id)
                    for answer_value in _token_values(matrix, right)
                    if answer_value not in {"unknown", "model_route"}
                )
                cases.extend(
                    ("qwen-code", left, answer_value, right, "model_route", rule_id)
                    for answer_value in _token_values(matrix, left)
                    if answer_value not in {"unknown", "model_route"}
                )
            else:
                cases.extend(
                    ("qwen-code", left, values[0], right, values[1], rule_id)
                    for values in cast(list[list[str]], rule["forbidden"])
                )

    # Route context is also derived from the matrix, not copied from a judge example.
    context = cast(dict[str, dict[str, Any]], matrix["candidate_context"])["openclaw"]
    for forbidden in cast(list[dict[str, str]], context["forbidden"]):
        other = next(question for question in _QUESTIONS if question != forbidden["question"])
        cases.append(
            (
                "openclaw",
                forbidden["question"],
                forbidden["value"],
                other,
                "unknown",
                "candidate-context",
            )
        )
    return tuple(cases)


_VIOLATION_CASES = _derived_violation_set()


def _set_token(document: dict[str, Any], candidate: str, question: str, answer_value: str) -> None:
    answer = _candidates(document)[candidate]["answers"][question]
    if answer_value == "unknown":
        answer["state"] = "unverified"
        answer["value"] = None
    elif answer_value == "model_route":
        answer["state"] = "not_applicable"
        answer["value"] = "model"
    else:
        answer["state"] = "verified"
        answer["value"] = answer_value
    answer.pop("note", None)


def test_matrix_is_complete_and_revision_pinned() -> None:
    matrix = _matrix()
    assert tuple(matrix["question_order"]) == _QUESTIONS
    assert len(matrix["pairs"]) == _MATRIX_PAIR_COUNT
    assert {frozenset((pair["left"], pair["right"])) for pair in matrix["pairs"]} == {
        frozenset((left, right))
        for index, left in enumerate(_QUESTIONS)
        for right in _QUESTIONS[index + 1 :]
    }
    expected_rule_ids = [
        rule_id
        for pair in matrix["pairs"]
        for rule_id in pair["rules"]
        if rule_id != "model-route-coherence"
        for _ in matrix["rules"][rule_id]["forbidden"]
    ]
    schema = _schema()
    schema_rules = schema["$defs"]["candidate"]["properties"]["answers"]["allOf"]
    assert [rule["x-ctower-matrix-rule-id"] for rule in schema_rules] == expected_rule_ids
    assert schema["x-ctower-matrix-default-rules"] == ["model-route-coherence"]
    context_rules = schema["$defs"]["candidate"]["allOf"][0]["then"]["properties"]["answers"][
        "allOf"
    ]
    expected_context = [
        {"question": item["question"], "forbidden_value": item["value"]}
        for item in matrix["candidate_context"]["openclaw"]["forbidden"]
    ]
    assert [rule["x-ctower-matrix-context-rule"] for rule in context_rules] == expected_context
    raw = _MATRIX.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == _MATRIX_SHA256


def test_authored_survey_is_strict_and_revision_pinned() -> None:
    document = _document()
    errors = _errors(document)

    assert not errors
    assert document["schema"] == "ctower.later-wave-harness-survey/v1"
    assert document["revision"] == 1
    assert document["matrix"]["sha256"] == _MATRIX_SHA256
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
            assert "note" not in answer
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


@settings(max_examples=256, derandomize=True, deadline=None)
@given(st.sampled_from(_VIOLATION_CASES))
def test_derived_matrix_violation_set_is_refused(case: Violation) -> None:
    candidate, left, left_token, right, right_token, rule_id = case
    document = copy.deepcopy(_document())
    _set_token(document, candidate, left, left_token)
    _set_token(document, candidate, right, right_token)

    assert _errors(document), f"derived violation accepted: {rule_id} {case}"
