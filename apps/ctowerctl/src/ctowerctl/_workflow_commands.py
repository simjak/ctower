"""Local installed-Workflow discovery and exact default selection."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

from ctowerctl._output import ExitCode

__all__: tuple[str, ...] = ()

_SOURCE_ROOT = Path(__file__).parents[4]
_ACTIVE_STATUSES = frozenset({"staged", "published"})
_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")
_WORKFLOW_FIELDS = {
    "schema",
    "status",
    "key",
    "revision",
    "initial_stage",
    "input_contract",
    "terminal_contract",
    "policy_refs",
    "stages",
    "transitions",
    "failure_routes",
    "note",
}


class _OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class WorkflowRevision(_OutputModel):
    workflow_ref: str
    workflow_digest: str
    execution_policy_ref: str
    execution_policy_digest: str
    gate_policy_ref: str
    gate_policy_digest: str
    evidence_policy_ref: str
    evidence_policy_digest: str


class WorkflowRevisions(_OutputModel):
    revisions: tuple[WorkflowRevision, ...]


@dataclass(frozen=True, slots=True)
class WorkflowStartPins:
    workflow_ref: str
    workflow_digest: str
    execution_policy_ref: str
    execution_policy_digest: str
    gate_policy_ref: str
    gate_policy_digest: str
    evidence_policy_ref: str
    evidence_policy_digest: str

    def response_payload(self) -> dict[str, str]:
        return {
            "workflow_ref": self.workflow_ref,
            "workflow_digest": self.workflow_digest,
            "execution_policy_ref": self.execution_policy_ref,
            "execution_policy_digest": self.execution_policy_digest,
            "gate_policy_ref": self.gate_policy_ref,
            "gate_policy_digest": self.gate_policy_digest,
            "evidence_policy_ref": self.evidence_policy_ref,
            "evidence_policy_digest": self.evidence_policy_digest,
        }


@dataclass(frozen=True, slots=True)
class _Component:
    payload: Mapping[str, object]
    content: bytes

    @property
    def reference(self) -> str:
        reference = f"{_string(self.payload, 'key')}@{_integer(self.payload, 'revision')}"
        if _REFERENCE.fullmatch(reference) is None:
            raise ValueError("installed component reference is invalid")
        return reference

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.content).hexdigest()


def execute_local() -> tuple[BaseModel, ExitCode]:
    """List exact executable revisions from the installed pack tree."""

    revisions = tuple(WorkflowRevision(**item.response_payload()) for item in installed_pins())
    return WorkflowRevisions(revisions=revisions), ExitCode.SUCCESS


def default_pins() -> WorkflowStartPins:
    """Return the sole installed executable revision or require an explicit choice."""

    revisions = installed_pins()
    if len(revisions) != 1:
        raise ValueError("usage: explicit Workflow pins required")
    return revisions[0]


def default_criteria() -> tuple[Mapping[str, object], ...]:
    """Return exact criteria from the sole installed executable gate policy."""

    raw = _array(_default_gate_policy().payload, "criteria")
    return tuple(_mapping(item, "gate policy criterion") for item in raw)


def default_criterion_key() -> str:
    """Return the sole installed criterion key or require an explicit choice."""

    criteria = default_criteria()
    if len(criteria) != 1:
        raise ValueError("usage: explicit criterion key required")
    return _string(criteria[0], "key")


def installed_pins() -> tuple[WorkflowStartPins, ...]:
    """Return generated exact pins without a hand-maintained component list."""

    pack_root = _pack_root()
    workflows = _components(pack_root / "workflows", "ctower.workflow/v1")
    execution = _index(
        _components(pack_root / "policies" / "execution", "ctower.execution-policy/v1")
    )
    gates = _index(_components(pack_root / "policies" / "gates", "ctower.gate-policy/v1"))
    evidence = _index(_components(pack_root / "policies" / "evidence", "ctower.evidence-policy/v1"))
    pins = tuple(_pins(item, execution, gates, evidence) for item in workflows)
    if len({item.workflow_ref for item in pins}) != len(pins):
        raise ValueError("installed Workflow references must be unique")
    return tuple(sorted(pins, key=lambda item: item.workflow_ref))


def _default_gate_policy() -> _Component:
    pins = default_pins()
    gates = _index(_components(_pack_root() / "policies" / "gates", "ctower.gate-policy/v1"))
    policy = _required(gates, pins.gate_policy_ref, "gate")
    if policy.digest != pins.gate_policy_digest:
        raise ValueError("installed Workflow gate policy digest is inconsistent")
    return policy


def _pack_root() -> Path:
    installed = Path(sys.prefix).parent / "packs"
    return installed if installed.is_dir() else _SOURCE_ROOT / "packs"


def _pins(
    workflow: _Component,
    execution: Mapping[str, _Component],
    gates: Mapping[str, _Component],
    evidence: Mapping[str, _Component],
) -> WorkflowStartPins:
    workflow_ref = workflow.reference
    policy_refs = _mapping(workflow.payload.get("policy_refs"), "workflow policy refs")
    execution_policy = _required(execution, _string(policy_refs, "execution"), "execution")
    gate_policy = _required(gates, _string(policy_refs, "gates"), "gate")
    evidence_policy = _required(
        evidence,
        _string(gate_policy.payload, "evidence_policy_ref"),
        "evidence",
    )
    if (
        _string(execution_policy.payload, "workflow_ref") != workflow_ref
        or _string(gate_policy.payload, "workflow_ref") != workflow_ref
    ):
        raise ValueError("installed policies do not match their Workflow")
    return WorkflowStartPins(
        workflow_ref,
        _workflow_digest(workflow.payload),
        execution_policy.reference,
        execution_policy.digest,
        gate_policy.reference,
        gate_policy.digest,
        evidence_policy.reference,
        evidence_policy.digest,
    )


def _workflow_digest(payload: Mapping[str, object]) -> str:
    if set(payload) != _WORKFLOW_FIELDS:
        raise ValueError("installed Workflow fields do not match the authored contract")
    reference = f"{_string(payload, 'key')}@{_integer(payload, 'revision')}"
    if _REFERENCE.fullmatch(reference) is None:
        raise ValueError("installed Workflow reference is invalid")
    policy_refs = _mapping(payload.get("policy_refs"), "workflow policy refs")
    stages = tuple(_mapping(item, "workflow stage") for item in _array(payload, "stages"))
    transitions = tuple(
        _mapping(item, "workflow transition") for item in _array(payload, "transitions")
    )
    canonical = {
        "initial_stage": _string(payload, "initial_stage"),
        "policy_refs": {
            "execution": _string(policy_refs, "execution"),
            "gates": _string(policy_refs, "gates"),
        },
        "reference": reference,
        "stages": [
            {
                "activity_class": _string(stage, "activity_class"),
                "key": _string(stage, "key"),
            }
            for stage in stages
        ],
        "transitions": [
            {
                "from": _string(transition, "from"),
                "predicate_ref": _string(transition, "predicate_ref"),
                "to": _string(transition, "to"),
            }
            for transition in transitions
        ],
    }
    encoded = json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _components(root: Path, schema: str) -> tuple[_Component, ...]:
    found: list[_Component] = []
    for path in sorted(root.rglob("*.yaml")):
        content = path.read_bytes()
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("installed pack must be UTF-8 JSON") from error
        if not isinstance(payload, Mapping):
            raise TypeError("installed pack must contain an object")
        if payload.get("schema") == schema and payload.get("status") in _ACTIVE_STATUSES:
            found.append(_Component(cast(Mapping[str, object], payload), content))
    return tuple(found)


def _index(components: tuple[_Component, ...]) -> dict[str, _Component]:
    indexed = {component.reference: component for component in components}
    if len(indexed) != len(components):
        raise ValueError("installed component references must be unique")
    return indexed


def _required(components: Mapping[str, _Component], reference: str, kind: str) -> _Component:
    if reference not in components:
        raise ValueError(f"installed Workflow {kind} policy is unavailable")
    return components[reference]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _array(payload: Mapping[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise TypeError(f"installed Workflow {key} must be an array")
    return value


def _string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"installed component {key} must be a string")
    return value


def _integer(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TypeError(f"installed component {key} must be a positive integer")
    return value
