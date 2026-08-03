"""Verdict-tier visibility: a degraded signature is flagged, never silently accepted."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.landing_boundary import (
    ChangeIdentity,
    LandingBoundaryError,
    LandingBoundaryReport,
    RecordSnapshot,
    evaluate_landing_boundary,
    load_verdict_tier_policy,
)
from tools.landing_boundary.report import FactStatus, FindingReason

from . import support

__all__: tuple[str, ...] = ()

_REVIEW_SLOT = "round-manifest"
_FLASH_MODEL = "deepseek/deepseek-v4-flash-0731"


def _report(answer: dict[str, Any]) -> LandingBoundaryReport:
    return evaluate_landing_boundary(
        RecordSnapshot.model_validate_json(json.dumps(answer)),
        ChangeIdentity(**support.CHANGE),
        load_verdict_tier_policy(),
    )


def _signed_by(model: str, *, verdict_id: str = "verdict-security") -> LandingBoundaryReport:
    return _report(
        support.replace_verdict(
            support.record_answer(),
            support.REVIEW_STAGE,
            _REVIEW_SLOT,
            verdict_id,
            signing_model=model,
        )
    )


@pytest.mark.parametrize("model", [_FLASH_MODEL, "glm-5.2", "some-unlisted-model"])
def test_a_security_verdict_signed_below_policy_tier_is_flagged(model: str) -> None:
    report = _signed_by(model)

    assert report.verdict == "refused"
    assert report.refusals == ("flagged-risk-derived-review-verdict-tier",)
    fact = next(fact for fact in report.facts if fact.stage_key == support.REVIEW_STAGE)
    assert fact.status is FactStatus.FLAGGED
    assert FindingReason.VERDICT_TIER_BELOW_POLICY in {finding.reason for finding in fact.findings}


def test_the_flag_names_the_model_that_actually_signed() -> None:
    report = _signed_by(_FLASH_MODEL)
    fact = next(fact for fact in report.facts if fact.stage_key == support.REVIEW_STAGE)

    assert any(
        finding.detail is not None and _FLASH_MODEL in finding.detail for finding in fact.findings
    )


def test_a_security_verdict_signed_at_policy_tier_is_accepted() -> None:
    assert _signed_by("claude-fable-5").verdict == "pass"


def test_an_ordinary_verdict_below_policy_tier_is_not_flagged() -> None:
    report = _signed_by(_FLASH_MODEL, verdict_id="verdict-correctness")

    assert report.verdict == "pass"


def test_a_release_gating_verdict_below_policy_tier_is_flagged() -> None:
    report = _report(
        support.replace_verdict(
            support.record_answer(),
            "release-preflight",
            "manifest",
            "verdict-release",
            signing_model="glm-5.2",
        )
    )

    assert report.refusals == ("flagged-release-preflight-verdict-tier",)


def test_a_missing_fact_outranks_a_tier_flag_on_the_same_stage() -> None:
    answer = support.replace_verdict(
        support.record_answer(),
        support.REVIEW_STAGE,
        _REVIEW_SLOT,
        "verdict-security",
        signing_model=_FLASH_MODEL,
    )
    report = _report(
        support.replace_slot(answer, support.REVIEW_STAGE, _REVIEW_SLOT, state="unknown")
    )

    assert report.refusals == ("missing-risk-derived-review-evidence",)


def test_the_authored_policy_ranks_the_live_routing_chain() -> None:
    policy = load_verdict_tier_policy()

    assert policy.is_below_floor("security", _FLASH_MODEL) is True
    assert policy.is_below_floor("security", "claude-opus-5") is False
    assert policy.is_below_floor("ordinary", _FLASH_MODEL) is False


@pytest.mark.parametrize(
    "body",
    [
        'schema = "ctower.verdict-tier-policy/v2"\nrevision = 1\ntier = []\nclass_floor = []\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\ntier = []\nclass_floor = []\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 0\n'
        '[[tier]]\nkey = "policy"\nrank = 1\nmodels = []\nclass_floor = []\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\nclass_floor = []\n'
        '[[tier]]\nkey = "a"\nrank = 1\nmodels = ["m"]\n'
        '[[tier]]\nkey = "a"\nrank = 2\nmodels = ["n"]\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\nclass_floor = []\n'
        '[[tier]]\nkey = "a"\nrank = 1\nmodels = ["m"]\n'
        '[[tier]]\nkey = "b"\nrank = 1\nmodels = ["n"]\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\nclass_floor = []\n'
        '[[tier]]\nkey = "a"\nrank = 1\nmodels = ["m"]\n'
        '[[tier]]\nkey = "b"\nrank = 2\nmodels = ["m"]\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\n'
        '[[tier]]\nkey = "a"\nrank = 1\nmodels = ["m"]\n'
        '[[class_floor]]\nverdict_class = "security"\nminimum_tier = "absent"\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\n'
        '[[tier]]\nkey = "a"\nrank = 1\nmodels = ["m"]\n'
        '[[class_floor]]\nverdict_class = "security"\nminimum_tier = "a"\n'
        '[[class_floor]]\nverdict_class = "security"\nminimum_tier = "a"\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\ntier = []\n'
        "class_floor = []\nextra = 1\n",
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\nclass_floor = []\n'
        '[[tier]]\nkey = "a"\nrank = 1\nmodels = ["m"]\nextra = 1\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\n'
        '[[tier]]\nkey = "a"\nrank = 1\nmodels = ["m"]\n'
        '[[class_floor]]\nverdict_class = "security"\nminimum_tier = "a"\nextra = 1\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\n'
        'tier = "not-an-array"\nclass_floor = []\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\nclass_floor = []\n'
        '[[tier]]\nkey = ""\nrank = 1\nmodels = ["m"]\n',
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\nclass_floor = []\n'
        '[[tier]]\nkey = "a"\nrank = true\nmodels = ["m"]\n',
    ],
)
def test_a_malformed_tier_policy_fails_closed(tmp_path: Path, body: str) -> None:
    path = tmp_path / "policy.toml"
    path.write_text(body, encoding="utf-8")

    with pytest.raises(LandingBoundaryError):
        load_verdict_tier_policy(path)


def test_an_absent_tier_policy_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(LandingBoundaryError, match="unreadable"):
        load_verdict_tier_policy(tmp_path / "absent.toml")


def test_a_malformed_tier_table_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "policy.toml"
    path.write_text(
        'schema = "ctower.verdict-tier-policy/v1"\nrevision = 1\nclass_floor = []\n'
        '[[tier]]\nkey = "a"\nrank = 1\nmodels = "not-a-list"\n',
        encoding="utf-8",
    )

    with pytest.raises(LandingBoundaryError, match=r"tier\.models"):
        load_verdict_tier_policy(path)
