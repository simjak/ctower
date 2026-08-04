"""Canonical Workflow Definition export shared by the S7 and S8 projections.

Canonical export preserves meaning and authored field order. Comments and byte
layout are not authoritative and are deliberately not reproduced.
"""

from __future__ import annotations

import io

from ruamel.yaml import YAML

from ctower_kernel.workflow._definition_model import (
    AssertionValue,
    EvidenceSlot,
    SkipSet,
    StageDefinition,
    TransitionDefinition,
    WorkflowDefinition,
)

__all__ = ["canonical_document", "canonical_yaml"]


def canonical_yaml(definition: WorkflowDefinition) -> str:
    """Render one revision as the canonical YAML 1.2 both projections save."""

    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    yaml.default_flow_style = False
    yaml.representer.sort_base_mapping_type_on_output = False
    buffer = io.StringIO()
    yaml.dump(canonical_document(definition), buffer)
    return buffer.getvalue()


def canonical_document(definition: WorkflowDefinition) -> dict[str, object]:
    """Return the canonical JSON-shaped document in authored field order."""

    spec: dict[str, object] = {}
    if definition.stage_groups:
        spec["stage_groups"] = list(definition.stage_groups)
    spec["stages"] = [_stage_document(stage) for stage in definition.stages]
    spec["transitions"] = [_transition_document(edge) for edge in definition.transitions]
    document: dict[str, object] = {
        "apiVersion": "ctower/v1",
        "kind": "Workflow",
        "metadata": {
            "name": definition.name,
            "company": definition.company,
            "revision": definition.revision,
            "signed_by": definition.signed_by,
        },
        "spec": spec,
    }
    if definition.overlays:
        document["overlays"] = {
            overlay.project: {
                stage: [_slot_document(slot) for slot in slots] for stage, slots in overlay.stages
            }
            for overlay in definition.overlays
        }
    return document


def _stage_document(stage: StageDefinition) -> dict[str, object]:
    payload: dict[str, object] = {"name": stage.name, "owner": stage.owner}
    if stage.group is not None:
        payload["group"] = stage.group
    payload["evidence"] = [_slot_document(slot) for slot in stage.evidence]
    if stage.signs is not None:
        payload["signs"] = stage.signs
    if stage.gate is not None:
        payload["gate"] = stage.gate
    if stage.skip is not None:
        payload["skip"] = _skip_document(stage.skip)
    if stage.failure_routes:
        payload["failure_routes"] = dict(stage.failure_routes)
    return payload


def _skip_document(skip: SkipSet) -> dict[str, object]:
    payload: dict[str, object] = {
        "predicate": skip.predicate,
        "evidence": [_slot_document(slot) for slot in skip.evidence],
    }
    if skip.signs is not None:
        payload["signs"] = skip.signs
    return payload


def _slot_document(slot: EvidenceSlot) -> dict[str, object]:
    payload: dict[str, object] = {"key": slot.key}
    for name, value in slot.assertions:
        payload[name] = _assertion_document(value)
    return payload


def _assertion_document(value: AssertionValue) -> object:
    return list(value) if isinstance(value, tuple) else value


def _transition_document(edge: TransitionDefinition) -> dict[str, object]:
    return {
        "from": edge.source,
        "to": edge.destination,
        "requires": list(edge.requires),
        "on_missing": "refuse",
    }
