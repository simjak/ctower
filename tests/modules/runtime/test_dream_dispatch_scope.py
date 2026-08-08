"""Fail-closed checks for authored dream-dispatch scope facts."""

from __future__ import annotations

from dataclasses import replace

import pytest

from ctower_kernel.runtime import DreamDispatchSpec


def test_invalid_dream_scope_and_execution_facts_fail_closed() -> None:
    spec = DreamDispatchSpec(
        scope_kind="project",
        project_key="ctower",
        skill_path="skills/dreamer/SKILL.md",
        primary_model_ref="gpt-5.6-sol",
        primary_reasoning_effort="max",
        fallback_model_ref="qwen3.8-max",
        fallback_reasoning_effort="max",
        minimum_model_tier="hard",
        excluded_model_families=("claude",),
    )

    with pytest.raises(ValueError, match="scope and project identity"):
        replace(spec, scope_kind="fleet")
    with pytest.raises(ValueError, match="authored dreamer skill"):
        replace(spec, skill_path="skills/other/SKILL.md")
    with pytest.raises(ValueError, match="model requirement"):
        replace(spec, minimum_model_tier="soft")
