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
_MATRIX_SHA256 = "cc9f4f9fee632816a9d7825f87cbf8346fccdcc8d5e65dfb4d3f1b30a640cfa5"
_MATRIX_PAIR_COUNT = 45
Violation = tuple[str, str, str, str, str, str]
EvidenceViolation = tuple[str, str, str, str]


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
    """Derive pair and route cases from the matrix law, not judge examples."""
    matrix = _matrix()
    cases: list[Violation] = []
    for index, left in enumerate(_QUESTIONS):
        for right in _QUESTIONS[index + 1 :]:
            cases.extend(
                (
                    "qwen-code",
                    left,
                    "model_route",
                    right,
                    answer_value,
                    "model-route-coherence",
                )
                for answer_value in _token_values(matrix, right)
                if answer_value not in {"unknown", "model_route"}
            )
            cases.extend(
                (
                    "qwen-code",
                    left,
                    answer_value,
                    right,
                    "model_route",
                    "model-route-coherence",
                )
                for answer_value in _token_values(matrix, left)
                if answer_value not in {"unknown", "model_route"}
            )

    for rule in cast(list[dict[str, Any]], matrix["pair_rules"]):
        left, right = cast(list[str], rule["pair"])
        cases.extend(
            ("qwen-code", left, values[0], right, values[1], cast(str, rule["id"]))
            for values in cast(list[list[str]], rule["forbidden"])
        )

    for candidate, context in cast(dict[str, dict[str, Any]], matrix["candidate_context"]).items():
        for forbidden in cast(list[dict[str, str]], context.get("forbidden", [])):
            other = next(question for question in _QUESTIONS if question != forbidden["question"])
            cases.append(
                (
                    candidate,
                    forbidden["question"],
                    forbidden["value"],
                    other,
                    "unknown",
                    "candidate-context",
                )
            )
    return tuple(cases)


def _derived_evidence_violation_set() -> tuple[EvidenceViolation, ...]:
    return tuple(
        (
            cast(str, rule["candidate"]),
            cast(str, rule["question"]),
            cast(str, rule["value"]),
            cast(str, rule["id"]),
        )
        for rule in cast(list[dict[str, Any]], _matrix()["evidence_claim_support"])
    )


_VIOLATION_CASES = _derived_violation_set()
_EVIDENCE_VIOLATION_CASES = _derived_evidence_violation_set()


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
    question_pairs = {
        frozenset((left, right))
        for index, left in enumerate(_QUESTIONS)
        for right in _QUESTIONS[index + 1 :]
    }
    assert len(question_pairs) == _MATRIX_PAIR_COUNT
    assert {
        frozenset(rule["pair"]) for rule in cast(list[dict[str, Any]], matrix["pair_rules"])
    } <= question_pairs

    schema = _schema()
    answer_rules = schema["$defs"]["answers"]["allOf"]
    schema_rule_ids = [item["$ref"].rsplit("/", 1)[-1] for item in answer_rules]
    assert schema_rule_ids == [
        "model-route-coherence",
        *[rule["id"] for rule in matrix["pair_rules"]],
    ]
    for rule_id in schema_rule_ids:
        assert schema["$defs"][rule_id]["x-ctower-matrix-rule-id"] == rule_id

    expected_route_rules: list[dict[str, str]] = []
    for candidate, context in matrix["candidate_context"].items():
        expected_route_rules.extend(
            {
                "candidate": candidate,
                "effective_route": context["effective_route"],
                "question": forbidden["question"],
                "forbidden_value": forbidden["value"],
            }
            for forbidden in context.get("forbidden", [])
        )
    assert schema["x-ctower-route-rules"] == expected_route_rules
    assert schema["x-ctower-evidence-claim-rules"] == matrix["evidence_claim_support"]
    assert schema["x-ctower-matrix-default-rules"] == matrix["default_rules"]
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
    _assert_violation_refused(case)


def _assert_violation_refused(case: Violation) -> None:
    candidate, left, left_token, right, right_token, rule_id = case
    document = copy.deepcopy(_document())
    _set_token(document, candidate, left, left_token)
    _set_token(document, candidate, right, right_token)

    assert _errors(document), f"derived violation accepted: {rule_id} {case}"


def test_every_derived_matrix_violation_is_refused() -> None:
    for case in _VIOLATION_CASES:
        _assert_violation_refused(case)


def test_qwen_cli_route_rejects_a_gateway_probe_target() -> None:
    document = copy.deepcopy(_document())
    qwen = _candidates(document)["qwen-code"]
    qwen["answers"]["probe_target"] = {
        "state": "verified",
        "value": "gateway_endpoint",
        "evidence": ["qwen-docs-0215"],
    }

    assert _errors(document), "qwen-cli cannot claim a gateway representative probe"


def test_qwen_published_directional_weights_require_supporting_evidence() -> None:
    document = copy.deepcopy(_document())
    qwen = _candidates(document)["qwen-code"]
    qwen["answers"]["credit_weights"] = {
        "state": "verified",
        "value": "published_directional",
        "evidence": ["qwen-docs-0215", "ctower-weight-registry-d724"],
    }

    assert _errors(document), "published Qwen weights need Qwen-specific supporting evidence"


def test_r6_matrix_declares_route_and_evidence_support_laws() -> None:
    matrix = _matrix()
    assert {
        "question": "probe_target",
        "value": "gateway_endpoint",
    } in matrix["candidate_context"]["qwen-code"]["forbidden"]
    assert matrix["evidence_claim_support"] == [
        {
            "id": "qwen-published-directional-weights",
            "candidate": "qwen-code",
            "question": "credit_weights",
            "state": "verified",
            "value": "published_directional",
            "required_evidence": ["qwen-directional-weight-table"],
            "available": False,
        }
    ]


def _assert_evidence_violation_refused(case: EvidenceViolation) -> None:
    candidate, question, answer_value, rule_id = case
    document = copy.deepcopy(_document())
    answer = _candidates(document)[candidate]["answers"][question]
    answer["state"] = "verified"
    answer["value"] = answer_value
    answer.pop("note", None)

    assert _errors(document), f"derived evidence violation accepted: {rule_id} {case}"


@settings(max_examples=32, derandomize=True, deadline=None)
@given(st.sampled_from(_EVIDENCE_VIOLATION_CASES))
def test_derived_evidence_claim_violations_are_refused(case: EvidenceViolation) -> None:
    _assert_evidence_violation_refused(case)


def test_every_derived_evidence_claim_violation_is_refused() -> None:
    for case in _EVIDENCE_VIOLATION_CASES:
        _assert_evidence_violation_refused(case)
