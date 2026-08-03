"""Record answers used as check inputs, built so a fixture cannot drift from its digest.

The stage and slot keys below belong to these fixtures, never to the check.  A fixture
may rename every one of them and the check keeps working, which is exactly what
``test_boundary.py`` and ``test_derivation.py`` prove.
"""

from __future__ import annotations

import json
from itertools import pairwise
from typing import Any

from ctower_kernel.workflow import WorkflowGraph

__all__ = [
    "CANDIDATE",
    "CHANGE",
    "DOCS_STAGE",
    "LANDING_STAGE",
    "REVIEW_STAGE",
    "SOFTWARE_FACTORY_STAGES",
    "SUPERSEDED_CANDIDATE",
    "graph_payload",
    "record_answer",
    "replace_slot",
    "replace_verdict",
]

CANDIDATE = "sha256:" + "1a" * 32
SUPERSEDED_CANDIDATE = "sha256:" + "2b" * 32
CHANGE = {
    "repository": "simjak/ctower",
    "pull_request_reference": "199",
    "head_revision": "4f" * 20,
}
SOFTWARE_FACTORY_STAGES = (
    "intake",
    "think",
    "plan",
    "design",
    "implement",
    "local-verification-qa",
    "risk-derived-review",
    "documentation",
    "release-preflight",
    "merge",
    "staging-deploy",
    "staging-qa",
    "production-deploy",
    "production-smoke-live-qa",
    "retro",
    "resolve-close",
)
REVIEW_STAGE = "risk-derived-review"
DOCS_STAGE = "documentation"
LANDING_STAGE = "merge"
_PREFLIGHT_STAGE = "release-preflight"


def graph_payload(
    stage_keys: tuple[str, ...] = SOFTWARE_FACTORY_STAGES,
    *,
    workflow_key: str = "engineering.software-factory",
) -> dict[str, Any]:
    """Author one linear pinned-graph payload over the given stage keys."""

    return {
        "schema": "ctower.workflow/v1",
        "status": "published",
        "key": workflow_key,
        "revision": 1,
        "initial_stage": stage_keys[0],
        "input_contract": "software-change-ticket-v1",
        "terminal_contract": "verified-release-and-retro-v1",
        "policy_refs": {
            "execution": f"{workflow_key}.execution@1",
            "gates": f"{workflow_key}.gates@1",
        },
        "stages": [{"key": stage, "activity_class": "work"} for stage in stage_keys],
        "transitions": [
            {"from": source, "to": destination, "predicate_ref": "entry.ready@1"}
            for source, destination in pairwise(stage_keys)
        ],
        "failure_routes": [],
        "note": "Fixture graph for landing-boundary derivation tests.",
    }


def record_answer(
    *,
    stage_keys: tuple[str, ...] = SOFTWARE_FACTORY_STAGES,
    landing_boundary_stage: str | None = LANDING_STAGE,
    graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the record's complete, compliant answer for the fixture change."""

    payload = graph_payload(stage_keys) if graph is None else graph
    return {
        "schema": "ctower.landing-boundary-record/v1",
        "availability": "available",
        "change": dict(CHANGE),
        "binding": {
            "ticket_id": "019fc3dc-3f9c-71fb-8191-f2e0853b8c69",
            "project_key": "ctower",
            "candidate_digest": CANDIDATE,
        },
        "workflow": {
            "graph": payload,
            "graph_digest": WorkflowGraph.from_mapping(payload).digest,
            "landing_boundary_stage": landing_boundary_stage,
        },
        "stages": [_stage(stage) for stage in stage_keys],
    }


def replace_slot(
    answer: dict[str, Any], stage_key: str, slot_key: str, **changes: object
) -> dict[str, Any]:
    """Return a copy of one record answer with a single slot's facts changed."""

    updated = _copy(answer)
    for slot in _slots(updated, stage_key, slot_key):
        slot.update(changes)
    return updated


def replace_verdict(
    answer: dict[str, Any], stage_key: str, slot_key: str, verdict_id: str, **changes: object
) -> dict[str, Any]:
    """Return a copy of one record answer with a single bound verdict changed."""

    updated = _copy(answer)
    for slot in _slots(updated, stage_key, slot_key):
        for verdict in slot["verdicts"]:
            if verdict["verdict_id"] == verdict_id:
                verdict.update(changes)
    return updated


def _copy(answer: dict[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = json.loads(json.dumps(answer))
    return copied


def _slots(answer: dict[str, Any], stage_key: str, slot_key: str) -> list[dict[str, Any]]:
    return [
        slot
        for stage in answer["stages"]
        if stage["stage_key"] == stage_key
        for slot in stage["required_slots"]
        if slot["slot_key"] == slot_key
    ]


def _stage(stage_key: str) -> dict[str, Any]:
    return {
        "stage_key": stage_key,
        "resolution": "resolved",
        "required_slots": [_slot(stage_key, slot_key) for slot_key in _slot_keys(stage_key)],
    }


def _slot_keys(stage_key: str) -> tuple[str, ...]:
    if stage_key == REVIEW_STAGE:
        return ("round-manifest",)
    if stage_key == DOCS_STAGE:
        return ("revision", "truth-check")
    if stage_key == _PREFLIGHT_STAGE:
        return ("manifest", "release-notes")
    return ("artifact",)


def _slot(stage_key: str, slot_key: str) -> dict[str, Any]:
    return {
        "slot_key": slot_key,
        "state": "filled",
        "validity": "current",
        "bound_candidate_digest": CANDIDATE,
        "self_reported": False,
        "verdicts": list(_verdicts(stage_key, slot_key)),
    }


def _verdicts(stage_key: str, slot_key: str) -> tuple[dict[str, Any], ...]:
    if stage_key == REVIEW_STAGE:
        return (
            _verdict("verdict-correctness", "ordinary", "review-seat", "glm-5.2"),
            _verdict("verdict-security", "security", "cso-seat", "claude-opus-5"),
        )
    if stage_key == _PREFLIGHT_STAGE and slot_key == "manifest":
        return (_verdict("verdict-release", "release-gating", "release-seat", "gpt-5.5"),)
    return ()


def _verdict(
    verdict_id: str, verdict_class: str, signer_principal: str, signing_model: str
) -> dict[str, Any]:
    return {
        "verdict_id": verdict_id,
        "verdict_class": verdict_class,
        "disposition": "signed-off",
        "signer_principal": signer_principal,
        "signing_model": signing_model,
        "self_reported": False,
    }
