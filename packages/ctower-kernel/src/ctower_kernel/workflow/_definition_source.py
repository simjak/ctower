"""Gate 1: strict source-schema decoding of one authored Workflow Definition.

The authored `ctower.workflow-definition/v1` contract decides the document shape,
the closed assertion vocabulary, and both published-key classes. This module never
restates those rules; it validates against that contract and then types the result.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from ctower_contracts import validator_for
from jsonschema.exceptions import ValidationError, best_match
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.events import AliasEvent, CollectionEndEvent, CollectionStartEvent

from ctower_kernel.workflow._definition_model import (
    AssertionValue,
    EvidenceSlot,
    ProjectOverlay,
    SkipSet,
    StageDefinition,
    TransitionDefinition,
    WorkflowDefinition,
    WorkflowDefinitionRefusedError,
)

__all__ = ["SOURCE_SCHEMA_ID", "load_definition"]

SOURCE_SCHEMA_ID = "https://ctower.local/contracts/workflow/workflow-definition.schema.json"

_MAX_SOURCE_BYTES = 256 * 1024
_MAX_SOURCE_NODES = 20_000
_MAX_SOURCE_DEPTH = 32
_DUPLICATE_KEY = re.compile(r'found duplicate key "(?P<key>[^"]*)"')
_QUOTED = re.compile(r"'([^']+)'")
_MERGE_KEY = "<<"


def load_definition(text: str) -> WorkflowDefinition:
    """Decode and type one source document, refusing by name at gate 1."""

    document = _decode(text)
    _validate(document)
    definition = _definition(document)
    _check_source_rules(definition)
    return definition


def _decode(text: str) -> Mapping[str, object]:
    if len(text.encode("utf-8")) > _MAX_SOURCE_BYTES:
        raise WorkflowDefinitionRefusedError("source.bounds", "document-bytes")
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    yaml.allow_duplicate_keys = False
    try:
        _inspect(yaml, text)
        value: object = yaml.load(text)
    except YAMLError as error:
        raise _yaml_refusal(error) from error
    if not isinstance(value, dict):
        raise WorkflowDefinitionRefusedError("source.shape", "document")
    return _json_mapping(cast(dict[object, object], value))


def _yaml_refusal(error: YAMLError) -> WorkflowDefinitionRefusedError:
    problem = str(getattr(error, "problem", "") or "")
    duplicate = _DUPLICATE_KEY.search(problem)
    if duplicate is not None:
        return WorkflowDefinitionRefusedError("source.duplicate-key", duplicate.group("key"))
    return WorkflowDefinitionRefusedError("source.undecodable", "document")


def _inspect(yaml: YAML, text: str) -> None:
    depth = 0
    for count, event in enumerate(yaml.parse(text), start=1):
        if count > _MAX_SOURCE_NODES:
            raise WorkflowDefinitionRefusedError("source.bounds", "document-nodes")
        _reject_unsafe(event)
        depth += _depth_delta(event)
        if depth > _MAX_SOURCE_DEPTH:
            raise WorkflowDefinitionRefusedError("source.bounds", "document-depth")


def _reject_unsafe(event: object) -> None:
    """Refuse every construct the decoder must never resolve on the author's behalf.

    A merge key is refused in the event stream because the constructor would otherwise
    flatten it before any mapping is visible. No authored member of this contract is
    spelled `<<`, so the scalar itself is the exact refusal.
    """

    if isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None:
        raise WorkflowDefinitionRefusedError("source.anchor", "alias-or-anchor")
    if getattr(event, "tag", None) is not None:
        raise WorkflowDefinitionRefusedError("source.tag", "custom-tag")
    if getattr(event, "value", None) == _MERGE_KEY:
        raise WorkflowDefinitionRefusedError("source.merge-key", _MERGE_KEY)


def _depth_delta(event: object) -> int:
    if isinstance(event, CollectionStartEvent):
        return 1
    if isinstance(event, CollectionEndEvent):
        return -1
    return 0


def _json_mapping(value: dict[object, object]) -> dict[str, object]:
    """Convert one decoded mapping, whose depth the event walk already bounded."""

    mapping: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise WorkflowDefinitionRefusedError("source.mapping-key", repr(key))
        mapping[key] = _json_value(item)
    return mapping


def _json_value(value: object) -> object:
    if isinstance(value, dict):
        return _json_mapping(cast(dict[object, object], value))
    if isinstance(value, list):
        return [_json_value(item) for item in cast(list[object], value)]
    if value is None or isinstance(value, str | bool | int | float):
        return value
    raise WorkflowDefinitionRefusedError("source.scalar", type(value).__name__)


def _validate(document: Mapping[str, object]) -> None:
    error = best_match(validator_for(SOURCE_SCHEMA_ID).iter_errors(document))
    if error is not None:
        raise WorkflowDefinitionRefusedError("source.schema", _offending_name(error))


def _offending_name(error: ValidationError) -> str:
    if error.validator != "additionalProperties":
        return error.json_path
    unexpected = ",".join(_QUOTED.findall(error.message))
    return f"{error.json_path}.{unexpected}" if unexpected else error.json_path


def _definition(document: Mapping[str, object]) -> WorkflowDefinition:
    metadata = _mapping(document["metadata"])
    spec = _mapping(document["spec"])
    return WorkflowDefinition(
        name=_text(metadata["name"]),
        company=_text(metadata["company"]),
        revision=_integer(metadata["revision"]),
        signed_by=_text(metadata["signed_by"]),
        stage_groups=tuple(_text(item) for item in _sequence(spec.get("stage_groups", []))),
        stages=tuple(_stage(_mapping(item)) for item in _sequence(spec["stages"])),
        transitions=tuple(_transition(_mapping(item)) for item in _sequence(spec["transitions"])),
        overlays=tuple(
            ProjectOverlay(
                project=project,
                stages=tuple(
                    (stage, _evidence(slots)) for stage, slots in _mapping(payload).items()
                ),
            )
            for project, payload in _mapping(document.get("overlays", {})).items()
        ),
    )


def _stage(payload: Mapping[str, object]) -> StageDefinition:
    skip = payload.get("skip")
    routes = _mapping(payload.get("failure_routes", {}))
    return StageDefinition(
        name=_text(payload["name"]),
        owner=_text(payload["owner"]),
        evidence=_evidence(payload["evidence"]),
        group=_optional(payload.get("group")),
        signs=_optional(payload.get("signs")),
        gate=_optional(payload.get("gate")),
        skip=None if skip is None else _skip(_mapping(skip)),
        failure_routes=tuple((reason, _text(target)) for reason, target in routes.items()),
    )


def _skip(payload: Mapping[str, object]) -> SkipSet:
    return SkipSet(
        predicate=_text(payload["predicate"]),
        evidence=_evidence(payload["evidence"]),
        signs=_optional(payload.get("signs")),
    )


def _transition(payload: Mapping[str, object]) -> TransitionDefinition:
    return TransitionDefinition(
        source=_text(payload["from"]),
        destination=_text(payload["to"]),
        requires=tuple(_text(item) for item in _sequence(payload["requires"])),
    )


def _evidence(value: object) -> tuple[EvidenceSlot, ...]:
    return tuple(_slot(_mapping(item)) for item in _sequence(value))


def _slot(payload: Mapping[str, object]) -> EvidenceSlot:
    return EvidenceSlot(
        key=_text(payload["key"]),
        assertions=tuple(
            (name, _assertion(item)) for name, item in payload.items() if name != "key"
        ),
    )


def _assertion(value: object) -> AssertionValue:
    if isinstance(value, list):
        return tuple(_integer(item) for item in cast(Sequence[object], value))
    return cast(str | bool, value)


def _check_source_rules(definition: WorkflowDefinition) -> None:
    _check_unique(tuple(stage.name for stage in definition.stages), "source.duplicate-stage")
    for stage in definition.stages:
        _check_stage(stage, definition.stage_groups)
    _check_declared_groups(definition)
    for overlay in definition.overlays:
        for stage_name, slots in overlay.stages:
            keys = tuple(slot.key for slot in slots)
            _check_unique(keys, "source.duplicate-slot", stage=stage_name)


def _check_stage(stage: StageDefinition, groups: tuple[str, ...]) -> None:
    _check_unique(stage.slot_keys, "source.duplicate-slot", stage=stage.name)
    _check_signing(stage.signs, stage.slot_keys, stage=stage.name)
    if stage.skip is not None:
        skip_keys = tuple(slot.key for slot in stage.skip.evidence)
        _check_unique(skip_keys, "source.duplicate-skip-slot", stage=stage.name)
        _check_signing(stage.skip.signs, skip_keys, stage=stage.name)
    _check_group(stage, groups)


def _check_signing(signs: str | None, keys: tuple[str, ...], *, stage: str) -> None:
    if signs is not None and signs not in keys:
        raise WorkflowDefinitionRefusedError("source.unknown-signing-slot", signs, stage=stage)


def _check_group(stage: StageDefinition, groups: tuple[str, ...]) -> None:
    if not groups:
        if stage.group is not None:
            raise WorkflowDefinitionRefusedError(
                "source.undeclared-group", stage.group, stage=stage.name
            )
        return
    if stage.group is None:
        raise WorkflowDefinitionRefusedError("source.missing-group", stage.name, stage=stage.name)
    if stage.group not in groups:
        raise WorkflowDefinitionRefusedError(
            "source.undeclared-group", stage.group, stage=stage.name
        )


def _check_declared_groups(definition: WorkflowDefinition) -> None:
    owned = {stage.group for stage in definition.stages}
    for group in definition.stage_groups:
        if group not in owned:
            raise WorkflowDefinitionRefusedError("source.empty-group", group)


def _check_unique(values: tuple[str, ...], rule: str, *, stage: str | None = None) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise WorkflowDefinitionRefusedError(rule, value, stage=stage)
        seen.add(value)


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value)


def _sequence(value: object) -> Sequence[object]:
    return cast(Sequence[object], value)


def _text(value: object) -> str:
    return cast(str, value)


def _integer(value: object) -> int:
    return cast(int, value)


def _optional(value: object) -> str | None:
    return None if value is None else _text(value)
