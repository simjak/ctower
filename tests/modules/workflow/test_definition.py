"""Behavior of the authored Workflow Definition source through its Interface.

The positive fixture is the operator-approved S8 Workflow YAML extracted from
`mockups/ctower-ui/workflow.html` in the mission-control review workspace, so this
suite proves the approved screen is a real kernel input rather than a retyped copy.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from ctower_kernel.workflow import ActivityClass, WorkflowGraph
from ctower_kernel.workflow.definition import (
    ResolvedStage,
    ResolvedWorkflow,
    WorkflowDefinition,
    WorkflowDefinitionRefusedError,
    WorkflowResolution,
    canonical_yaml,
    load_workflow_definition,
    normalized_workflow_payload,
    resolve_workflow_definition,
)

ROOT = Path(__file__).parents[3]
FIXTURES = ROOT / "tests/contracts/workflow/fixtures"
APPROVED = FIXTURES / "approved-s8-workflow.yaml"
COMPLETE = FIXTURES / "complete-workflow-definition.yaml"
_ACTIVITY_CHECK = re.compile(r"activity_class text NOT NULL CHECK \(activity_class IN \(([^)]*)\)")
__all__: tuple[str, ...] = ()


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _mutated(path: Path, old: str, new: str) -> str:
    source = _text(path)
    assert source.count(old) == 1, f"mutation anchor is not unique: {old!r}"
    return source.replace(old, new)


def _resolution() -> WorkflowResolution:
    return WorkflowResolution(
        activity_classes={
            "intake": ActivityClass.WORK,
            "build": ActivityClass.WORK,
            "review": ActivityClass.VERIFICATION,
            "qa": ActivityClass.VERIFICATION,
            "resolve-close": ActivityClass.WORK,
        },
        transition_predicates={
            ("intake", "build"): "intake.complete@1",
            ("build", "review"): "build.complete@1",
            ("review", "qa"): "review.complete@1",
            ("qa", "resolve-close"): "qa.complete@1",
        },
        failure_classes={"changes-requested": "review.changes-requested@1"},
        input_contract="software-change-ticket-v1",
        terminal_contract="verified-release-and-retro-v1",
        execution_policy_ref="engineering.software-factory.execution@1",
        gate_policy_ref="engineering.software-factory.gates@1",
        status="published",
        note="Normalized from one authored ctower.workflow-definition/v1 revision.",
    )


def _complete() -> WorkflowDefinition:
    return load_workflow_definition(_text(COMPLETE))


def _stage(resolved: ResolvedWorkflow, name: str) -> ResolvedStage:
    stage = resolved.stage(name)
    assert stage is not None, f"{name} is not a resolved stage"
    return stage


def test_the_approved_mockup_source_validates_and_loads() -> None:
    definition = load_workflow_definition(_text(APPROVED))

    assert definition.reference == "engineering.software-factory@12"
    assert definition.company == "jakit-labs"
    assert definition.signed_by == "em-185-decision"
    assert [stage.name for stage in definition.stages] == ["intake", "build", "review", "qa"]
    assert [stage.owner for stage in definition.stages] == ["commander", "engineer", "review", "qa"]
    intake = definition.stages[0]
    assert intake.slot_keys == ("source-reference", "prohibited-data-scan")
    assert intake.evidence[0].assertions == (
        ("required", True),
        ("shape", "<project>-R<nnn> | gh#<n>"),
    )
    assert definition.stages[3].evidence[0].assertions[1] == ("widths", (390, 768, 1440))
    assert [(edge.source, edge.destination) for edge in definition.transitions] == [
        ("build", "review")
    ]
    assert [overlay.project for overlay in definition.overlays] == ["lastmachines", "bh-loop"]


def test_the_approved_mockup_defaults_no_omitted_member() -> None:
    definition = load_workflow_definition(_text(APPROVED))

    assert definition.stage_groups == ()
    for stage in definition.stages:
        assert stage.group is None
        assert stage.signs is None
        assert stage.gate is None
        assert stage.skip is None
        assert stage.failure_routes == ()


def test_the_compact_excerpt_reports_its_missing_graph_at_plan_time() -> None:
    definition = load_workflow_definition(_text(APPROVED))

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        resolve_workflow_definition(definition)

    assert refusal.value.rule == "transition.divergent-requires"
    assert (refusal.value.stage, refusal.value.name) == ("build", "review")


def test_an_overlay_target_outside_the_excerpt_is_named_at_plan_time() -> None:
    definition = load_workflow_definition(_text(APPROVED))

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        resolve_workflow_definition(definition, project="lastmachines")

    assert refusal.value.rule == "overlay.unknown-stage"
    assert refusal.value.name == "staging"


_STAGE_MUTATIONS = [
    ("      owner: engineer\n", "", "source.schema", "$.spec.stages[1]"),
    (
        "    - name: build\n",
        "    - name: intake\n",
        "source.duplicate-stage",
        "intake",
    ),
    (
        "        - key: scoped-tests\n          required: true\n",
        "        - key: scoped-tests\n          required: false\n",
        "source.schema",
        "$.spec.stages[1].evidence[0].required",
    ),
    (
        "          command: just test <path>\n",
        "          rubber_stamp: true\n",
        "source.schema",
        "$.spec.stages[1].evidence[0].rubber_stamp",
    ),
    (
        "          widths: [390, 768, 1440]\n",
        "          widths: [1, 768, 1440]\n",
        "source.schema",
        "$.spec.stages[3].evidence[0].widths[0]",
    ),
    (
        "      owner: engineer\n",
        "      owner: engineer\n      signs: status-file\n",
        "source.unknown-signing-slot",
        "status-file",
    ),
    (
        "      owner: engineer\n",
        "      owner: engineer\n      group: implementation\n",
        "source.undeclared-group",
        "implementation",
    ),
    (
        "      to: review\n",
        "      to: review\n      on_missing: warn\n",
        "source.duplicate-key",
        "on_missing",
    ),
]


@pytest.mark.parametrize(("old", "new", "rule", "name"), _STAGE_MUTATIONS)
def test_a_mutated_stage_refuses_by_name(old: str, new: str, rule: str, name: str) -> None:
    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        load_workflow_definition(_mutated(APPROVED, old, new))

    assert (refusal.value.rule, refusal.value.name) == (rule, name)


@pytest.mark.parametrize(
    ("old", "new", "rule"),
    [
        ("  name: engineering.software-factory\n", "  name: ab\n", "source.schema"),
        ("  name: engineering.software-factory\n", "  name: my_workflow\n", "source.schema"),
        ("  company: jakit-labs\n", "  company: jl\n", "source.schema"),
    ],
)
def test_a_published_key_the_authored_contract_refuses_is_refused_at_gate_one(
    old: str,
    new: str,
    rule: str,
) -> None:
    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        load_workflow_definition(_mutated(APPROVED, old, new))

    assert refusal.value.rule == rule


def test_a_source_local_key_shorter_than_a_catalog_key_is_accepted() -> None:
    definition = load_workflow_definition(_text(APPROVED))

    assert definition.stages[3].name == "qa"


@pytest.mark.parametrize(
    ("document", "rule", "name"),
    [
        ("apiVersion: ctower/v1\napiVersion: ctower/v1\n", "source.duplicate-key", "apiVersion"),
        ("base: &a {k: 1}\nuse: *a\n", "source.anchor", "alias-or-anchor"),
        ("apiVersion: !!str ctower/v1\n", "source.tag", "custom-tag"),
        ("base: {k: 1}\nuse:\n  <<: {j: 2}\n", "source.merge-key", "<<"),
        ("? [1, 2]\n: value\n", "source.mapping-key", "(1, 2)"),
        ("- one\n- two\n", "source.shape", "document"),
        ("apiVersion: 2026-01-01\n", "source.scalar", "date"),
        ("apiVersion: 'unterminated\n", "source.undecodable", "document"),
    ],
)
def test_yaml_structure_outside_the_contract_refuses_by_name(
    document: str,
    rule: str,
    name: str,
) -> None:
    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        load_workflow_definition(document)

    assert (refusal.value.rule, refusal.value.name) == (rule, name)


@pytest.mark.parametrize(
    ("document", "name"),
    [
        pytest.param("# padding\n" * 40_000, "document-bytes", id="bytes"),
        pytest.param("root: [" + "1," * 20_000 + "1]\n", "document-nodes", id="nodes"),
        pytest.param(
            "root:\n" + "".join(f"{' ' * i}- " for i in range(40)) + "1\n",
            "document-depth",
            id="depth",
        ),
    ],
)
def test_a_document_beyond_its_decoding_bounds_refuses(document: str, name: str) -> None:
    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        load_workflow_definition(document)

    assert (refusal.value.rule, refusal.value.name) == ("source.bounds", name)


def test_an_unknown_top_level_member_refuses_by_name() -> None:
    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        load_workflow_definition(_mutated(APPROVED, "overlays:\n", "extras: 1\noverlays:\n"))

    assert refusal.value.name == "$.extras"


@pytest.mark.parametrize(
    ("old", "new", "rule", "name"),
    [
        ("      group: implementation\n", "", "source.missing-group", "build"),
        (
            "      group: implementation\n",
            "      group: shipping\n",
            "source.undeclared-group",
            "shipping",
        ),
        (
            "      group: delivery\n",
            "      group: verification\n",
            "source.empty-group",
            "delivery",
        ),
    ],
)
def test_a_declared_group_vocabulary_maps_every_stage_both_ways(
    old: str,
    new: str,
    rule: str,
    name: str,
) -> None:
    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        load_workflow_definition(_mutated(COMPLETE, old, new))

    assert (refusal.value.rule, refusal.value.name) == (rule, name)


def test_an_edge_naming_an_undeclared_stage_is_refused_by_name() -> None:
    definition = load_workflow_definition(
        _mutated(
            COMPLETE,
            "    - from: review\n      to: qa\n",
            "    - from: review\n      to: nowhere\n",
        )
    )

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        resolve_workflow_definition(definition)

    assert (refusal.value.rule, refusal.value.name) == ("graph.unknown-stage", "nowhere")


def test_the_approved_excerpt_round_trips_through_its_canonical_export() -> None:
    definition = load_workflow_definition(_text(APPROVED))

    canonical = canonical_yaml(definition)

    assert load_workflow_definition(canonical) == definition
    assert "stage_groups" not in canonical
    assert "signs:" not in canonical
    assert "# jakit-labs" not in canonical


def test_a_project_overlay_applies_after_the_base_in_authored_order() -> None:
    definition = _complete()

    base = resolve_workflow_definition(definition)
    lastmachines = resolve_workflow_definition(definition, project="lastmachines")
    bh_loop = resolve_workflow_definition(definition, project="bh-loop")
    unlisted = resolve_workflow_definition(definition, project="ctower.control-plane")

    assert _stage(base, "qa").slot_keys == ("uses-not-loads",)
    assert _stage(lastmachines, "qa").slot_keys == ("uses-not-loads", "k3d-only")
    assert _stage(lastmachines, "resolve-close").slot_keys == (
        "retro-note",
        "deployment-receipt",
    )
    assert _stage(bh_loop, "intake").slot_keys == (
        "source-reference",
        "prohibited-data-scan",
        "phi-fixture-refused",
    )
    assert _stage(bh_loop, "qa").slot_keys == _stage(base, "qa").slot_keys
    assert _stage(unlisted, "qa").slot_keys == _stage(base, "qa").slot_keys


def test_an_overlay_changes_no_graph_owner_or_skip_fact() -> None:
    definition = _complete()

    base = resolve_workflow_definition(definition)
    lastmachines = resolve_workflow_definition(definition, project="lastmachines")

    assert base.transitions == lastmachines.transitions
    assert base.initial_stage == lastmachines.initial_stage
    assert [stage.owner for stage in base.stages] == [stage.owner for stage in lastmachines.stages]
    assert _stage(base, "qa").skip == _stage(lastmachines, "qa").skip
    assert _stage(base, "qa").signing_slot == _stage(lastmachines, "qa").signing_slot


def test_an_overlay_colliding_with_a_base_slot_is_refused_by_name() -> None:
    definition = load_workflow_definition(
        _mutated(COMPLETE, "      - key: k3d-only\n", "      - key: uses-not-loads\n")
    )

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        resolve_workflow_definition(definition, project="lastmachines")

    assert refusal.value.rule == "overlay.slot-collision"
    assert (refusal.value.name, refusal.value.stage) == ("uses-not-loads", "qa")


def test_a_terminal_stage_carries_its_required_set_without_an_outgoing_edge() -> None:
    resolved = resolve_workflow_definition(_complete())

    terminal = _stage(resolved, "resolve-close")
    assert terminal.terminal is True
    assert terminal.slot_keys == ("retro-note",)
    assert [stage.name for stage in resolved.stages if stage.terminal] == ["resolve-close"]
    assert resolved.initial_stage == "intake"


@pytest.mark.parametrize(
    ("old", "new", "rule", "name"),
    [
        (
            "      requires: [source-reference, prohibited-data-scan]\n",
            "      requires: [prohibited-data-scan, source-reference]\n",
            "transition.divergent-requires",
            "build",
        ),
        (
            "      requires: [uses-not-loads]\n",
            "      requires: [uses-not-loads, k3d-only]\n",
            "transition.divergent-requires",
            "resolve-close",
        ),
        (
            "        changes-requested: build\n",
            "        changes-requested: nowhere\n",
            "graph.unknown-route-target",
            "changes-requested",
        ),
    ],
)
def test_graph_completeness_is_decided_at_plan_time(
    old: str,
    new: str,
    rule: str,
    name: str,
) -> None:
    definition = load_workflow_definition(_mutated(COMPLETE, old, new))

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        resolve_workflow_definition(definition)

    assert (refusal.value.rule, refusal.value.name) == (rule, name)


def test_more_than_one_entry_stage_is_refused_with_both_named() -> None:
    definition = load_workflow_definition(
        _mutated(
            COMPLETE,
            "    - from: intake\n      to: build\n"
            "      requires: [source-reference, prohibited-data-scan]\n"
            "      on_missing: refuse\n",
            "",
        )
    )

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        resolve_workflow_definition(definition)

    assert refusal.value.rule == "graph.entry-stage"
    assert refusal.value.name == "intake,build"


def test_a_graph_without_a_terminal_stage_is_refused() -> None:
    definition = load_workflow_definition(
        _mutated(
            COMPLETE,
            "    - from: qa\n      to: resolve-close\n      requires: [uses-not-loads]\n"
            "      on_missing: refuse\n",
            "    - from: qa\n      to: resolve-close\n      requires: [uses-not-loads]\n"
            "      on_missing: refuse\n"
            "    - from: resolve-close\n      to: intake\n      requires: [retro-note]\n"
            "      on_missing: refuse\n",
        )
    )

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        resolve_workflow_definition(definition)

    assert refusal.value.rule == "graph.no-terminal-stage"


def test_a_stage_unreachable_from_the_entry_stage_is_refused_by_name() -> None:
    definition = load_workflow_definition(
        _mutated(
            COMPLETE,
            "    - from: review\n      to: qa\n      requires: [code-review-verdict]\n"
            "      on_missing: refuse\n",
            "    - from: resolve-close\n      to: qa\n      requires: [retro-note]\n"
            "      on_missing: refuse\n",
        )
    )

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        resolve_workflow_definition(definition)

    assert (refusal.value.rule, refusal.value.name) == ("graph.unreachable-stage", "qa")


def test_a_source_document_round_trips_through_its_canonical_export() -> None:
    definition = _complete()

    canonical = canonical_yaml(definition)

    assert load_workflow_definition(canonical) == definition
    assert canonical_yaml(load_workflow_definition(canonical)) == canonical
    assert "# A complete revision" not in canonical


def test_the_normalized_projection_round_trips_to_one_stable_digest() -> None:
    definition = _complete()
    resolution = _resolution()

    resolved = resolve_workflow_definition(definition)
    payload = normalized_workflow_payload(resolved, resolution)
    graph = WorkflowGraph.from_mapping(payload)
    exported = load_workflow_definition(canonical_yaml(definition))
    rebuilt = WorkflowGraph.from_mapping(
        normalized_workflow_payload(resolve_workflow_definition(exported), resolution)
    )

    assert payload["schema"] == "ctower.workflow/v1"
    assert graph.reference == "engineering.software-factory@13"
    assert graph.initial_stage == "intake"
    assert [stage.key for stage in graph.stages] == [
        "intake",
        "build",
        "review",
        "qa",
        "resolve-close",
    ]
    assert payload["failure_routes"] == [
        {"from": "review", "failure_class_ref": "review.changes-requested@1", "to": "build"}
    ]
    assert rebuilt.digest == graph.digest


def test_an_overlay_normalizes_to_the_same_graph_digest() -> None:
    definition = _complete()
    resolution = _resolution()

    base = WorkflowGraph.from_mapping(
        normalized_workflow_payload(resolve_workflow_definition(definition), resolution)
    )
    overlaid = WorkflowGraph.from_mapping(
        normalized_workflow_payload(
            resolve_workflow_definition(definition, project="lastmachines"), resolution
        )
    )

    assert overlaid.digest == base.digest


@pytest.mark.parametrize(
    ("mutate", "rule", "name"),
    [
        pytest.param(
            lambda item: replace(item, activity_classes={}),
            "payload.activity-class",
            "intake",
            id="activity-class",
        ),
        pytest.param(
            lambda item: replace(item, transition_predicates={}),
            "payload.transition-predicate",
            "build",
            id="transition-predicate",
        ),
        pytest.param(
            lambda item: replace(item, failure_classes={}),
            "payload.failure-class",
            "changes-requested",
            id="failure-class",
        ),
    ],
)
def test_an_unresolved_normalized_fact_refuses_with_that_fact_named(
    mutate: Callable[[WorkflowResolution], WorkflowResolution],
    rule: str,
    name: str,
) -> None:
    resolved = resolve_workflow_definition(_complete())
    resolution = mutate(_resolution())

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        normalized_workflow_payload(resolved, resolution)

    assert (refusal.value.rule, refusal.value.name) == (rule, name)


def test_a_resolved_set_without_a_signing_slot_refuses_with_its_stage_named() -> None:
    definition = load_workflow_definition(_mutated(COMPLETE, "      signs: retro-note\n", ""))
    resolved = resolve_workflow_definition(definition)

    with pytest.raises(WorkflowDefinitionRefusedError) as refusal:
        normalized_workflow_payload(resolved, _resolution())

    assert refusal.value.rule == "payload.signing-slot"
    assert (refusal.value.name, refusal.value.stage) == ("resolve-close", "resolve-close")


def test_the_normalized_activity_vocabulary_derives_from_the_record_constraint() -> None:
    migration = (ROOT / "packages/ctower-kernel/migrations/0004_proof_workflow.sql").read_text(
        encoding="utf-8"
    )
    declared = {
        tuple(sorted(value.strip().strip("'") for value in match.split(",")))
        for match in _ACTIVITY_CHECK.findall(migration)
    }
    payload = normalized_workflow_payload(resolve_workflow_definition(_complete()), _resolution())
    stages = payload["stages"]
    assert isinstance(stages, list)

    assert declared == {tuple(sorted(item.value for item in ActivityClass))}
    assert {str(stage["activity_class"]) for stage in stages} <= {
        item.value for item in ActivityClass
    }
