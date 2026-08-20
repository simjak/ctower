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
_MATRIX_SHA256 = "b1fa4c398d4c16d724d87b1bd037170a4e8a0858b7aeeb2ec9d6a8f0e86eb56b"
_MATRIX_REVISION = 2
_MATRIX_PAIR_COUNT = 45
Violation = tuple[str, str, str, str, str, str]
ReferentialViolation = tuple[str, str, str, str, str, str]
EvidenceViolation = tuple[str, str, str, str]
_QWEN_PROBE_TARGETS = ("gateway_endpoint", "direct_cli_endpoint", "representative_endpoint")
_QWEN_CREDIT_CLAIMS = ("published_directional", "unpublished")


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
    pairs = cast(list[str], matrix["pairs"])
    rules = cast(dict[str, dict[str, Any]], matrix["rules"])
    default_rules = cast(list[str], matrix["default_rules"])
    pair_rule_overrides = cast(dict[str, list[str]], matrix["pair_rule_overrides"])
    cases: list[Violation] = []
    for pair in pairs:
        left, right = pair.split("|")
        for rule_id in [*default_rules, *pair_rule_overrides.get(pair, [])]:
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


def _derived_referential_violation_set() -> tuple[ReferentialViolation, ...]:
    """Derive cross-field mismatches from every matrix referential rule."""
    matrix = _matrix()
    domains = cast(dict[str, list[str]], matrix["domains"])
    context = cast(dict[str, dict[str, Any]], matrix["candidate_context"])
    cases: list[ReferentialViolation] = []
    for relation in cast(list[dict[str, Any]], matrix["referential_consistency"]):
        anchor = cast(str, relation["anchor"])
        dependent = cast(str, relation["dependent"])
        allowed_by_anchor = cast(dict[str, list[str]], relation["allowed"])
        if anchor == "effective_route":
            for candidate, candidate_context in context.items():
                route = cast(str, candidate_context["effective_route"])
                cases.extend(
                    (
                        candidate,
                        anchor,
                        route,
                        dependent,
                        dependent_value,
                        relation["id"],
                    )
                    for dependent_value in domains[dependent]
                    if dependent_value not in allowed_by_anchor[route]
                )
            continue
        for candidate in _CANDIDATES:
            for anchor_value in domains[anchor]:
                if anchor_value in {"unknown", "model_route"}:
                    continue
                cases.extend(
                    (
                        candidate,
                        anchor,
                        anchor_value,
                        dependent,
                        dependent_value,
                        relation["id"],
                    )
                    for dependent_value in domains[dependent]
                    if dependent_value not in allowed_by_anchor[anchor_value]
                )
    return tuple(cases)


def _derived_evidence_violation_set() -> tuple[EvidenceViolation, ...]:
    """Derive verified-claim/evidence mismatches from the support table."""
    matrix = _matrix()
    domains = cast(dict[str, list[str]], matrix["domains"])
    support = cast(dict[str, dict[str, Any]], matrix["evidence_type_support"])
    source_types = {
        source["id"]: source["evidence_type"]
        for source in cast(list[dict[str, str]], _document()["sources"])
    }
    cases: list[EvidenceViolation] = []
    for candidate in _CANDIDATES:
        answers = _candidates(_document())[candidate]["answers"]
        for question in _QUESTIONS:
            for answer_value in domains[question]:
                if answer_value in {"unknown", "model_route"}:
                    continue
                support_entry = support[question][answer_value]
                if isinstance(support_entry, dict):
                    supported_types = {
                        evidence_type
                        for evidence_types in cast(dict[str, list[str]], support_entry).values()
                        for evidence_type in evidence_types
                    }
                else:
                    supported_types = set(cast(list[str], support_entry))
                supported_ids = {
                    source_id
                    for source_id, evidence_type in source_types.items()
                    if evidence_type in supported_types
                }
                if any(
                    source_id not in supported_ids for source_id in answers[question]["evidence"]
                ):
                    cases.append((candidate, question, answer_value, "evidence-type-support"))
    return tuple(cases)


_REFERENTIAL_VIOLATION_CASES = _derived_referential_violation_set()
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
    assert matrix["revision"] == _MATRIX_REVISION
    assert len(matrix["pairs"]) == _MATRIX_PAIR_COUNT
    assert {frozenset(pair.split("|")) for pair in matrix["pairs"]} == {
        frozenset((left, right))
        for index, left in enumerate(_QUESTIONS)
        for right in _QUESTIONS[index + 1 :]
    }
    expected_rule_ids = [
        rule_id
        for pair in matrix["pairs"]
        for rule_id in [*matrix["default_rules"], *matrix["pair_rule_overrides"].get(pair, [])]
        if rule_id != "model-route-coherence"
        for _ in matrix["rules"][rule_id]["forbidden"]
    ]
    schema = _schema()
    schema_rules = schema["$defs"]["answers"]["allOf"]
    assert [
        rule["x-ctower-matrix-rule-id"]
        for rule in schema_rules
        if "x-ctower-matrix-rule-id" in rule
    ] == expected_rule_ids
    assert {
        rule["x-ctower-referential-rule-id"]
        for rule in schema_rules
        if "x-ctower-referential-rule-id" in rule
    } == {
        relation["id"]
        for relation in matrix["referential_consistency"]
        if relation["anchor"] != "effective_route"
    }
    assert schema["x-ctower-matrix-default-rules"] == ["model-route-coherence"]
    context_rules = [
        rule
        for rule in schema["$defs"]["candidate"]["allOf"][0]["then"]["allOf"]
        if "x-ctower-matrix-context-rule" in rule
    ]
    route_rules = [
        rule
        for branch in schema["$defs"]["candidate"]["allOf"]
        for rule in branch["then"].get("allOf", [])
        if "x-ctower-referential-rule-id" in rule
    ]
    assert {rule["x-ctower-referential-rule-id"] for rule in route_rules} == {
        relation["id"]
        for relation in matrix["referential_consistency"]
        if relation["anchor"] == "effective_route"
    }
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
    assert document["revision"] == _MATRIX_REVISION
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


def test_route_referential_consistency_refuses_gateway_probe_for_qwen_cli() -> None:
    document = copy.deepcopy(_document())
    _set_token(document, "qwen-code", "probe_target", "gateway_endpoint")

    assert _errors(document), "qwen-cli cannot claim a gateway representative probe"


def test_verified_credit_claim_requires_candidate_supporting_evidence() -> None:
    document = copy.deepcopy(_document())
    _set_token(document, "qwen-code", "credit_weights", "published_directional")

    assert _errors(document), "Qwen has no cited evidence type for published directional weights"


@settings(max_examples=3, derandomize=True, deadline=None)
@given(st.sampled_from(_QWEN_PROBE_TARGETS))
def test_referential_consistency_search_rejects_nonmatching_qwen_probe(
    probe_target: str,
) -> None:
    document = copy.deepcopy(_document())
    _set_token(document, "qwen-code", "probe_target", probe_target)

    assert bool(_errors(document)) is (probe_target != "direct_cli_endpoint")


@settings(max_examples=2, derandomize=True, deadline=None)
@given(st.sampled_from(_QWEN_CREDIT_CLAIMS))
def test_evidence_support_search_rejects_unsupported_verified_credit_claim(
    credit_claim: str,
) -> None:
    document = copy.deepcopy(_document())
    _set_token(document, "qwen-code", "credit_weights", credit_claim)

    assert bool(_errors(document)) is (credit_claim == "published_directional")


@settings(max_examples=256, derandomize=True, deadline=None)
@given(st.sampled_from(_REFERENTIAL_VIOLATION_CASES))
def test_derived_referential_violations_are_refused(case: ReferentialViolation) -> None:
    candidate, anchor, anchor_value, dependent, dependent_value, rule_id = case
    document = copy.deepcopy(_document())
    if anchor != "effective_route":
        _set_token(document, candidate, anchor, anchor_value)
    _set_token(document, candidate, dependent, dependent_value)

    assert _errors(document), f"derived referential violation accepted: {rule_id} {case}"


@settings(max_examples=256, derandomize=True, deadline=None)
@given(st.sampled_from(_EVIDENCE_VIOLATION_CASES))
def test_derived_evidence_support_violations_are_refused(case: EvidenceViolation) -> None:
    candidate, question, answer_value, rule_id = case
    document = copy.deepcopy(_document())
    _set_token(document, candidate, question, answer_value)

    assert _errors(document), f"derived evidence violation accepted: {rule_id} {case}"


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


def test_every_derived_referential_violation_is_refused() -> None:
    for case in _REFERENTIAL_VIOLATION_CASES:
        candidate, anchor, anchor_value, dependent, dependent_value, rule_id = case
        document = copy.deepcopy(_document())
        if anchor != "effective_route":
            _set_token(document, candidate, anchor, anchor_value)
        _set_token(document, candidate, dependent, dependent_value)
        assert _errors(document), f"derived referential violation accepted: {rule_id} {case}"


def test_every_derived_evidence_support_violation_is_refused() -> None:
    for case in _EVIDENCE_VIOLATION_CASES:
        candidate, question, answer_value, rule_id = case
        document = copy.deepcopy(_document())
        _set_token(document, candidate, question, answer_value)
        assert _errors(document), f"derived evidence violation accepted: {rule_id} {case}"
