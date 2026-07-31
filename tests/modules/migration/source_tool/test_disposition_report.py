"""Exhaustive disposition report and zero-bulk-import validity (AC2).

AC2: Every legacy source/stable ID has exactly one disposition; only the
reviewed still-actionable set is carried forward, with exact aliases, and
zero bulk import is a valid plan.

Proof: signed source-selection, alias-map, and import-plan objects plus
the exhaustive disposition report.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from tools.migration.ctower_project.ctower_project_source.exporter import (
    FrozenExport,
    compare_exports,
    freeze_export,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import (
    ImportPlan,
    build_import_plan,
    seal_import_plan,
)
from tools.migration.ctower_project.ctower_project_source.source import (
    ReadOnlySourceRoot,
)

from .fixtures import (
    COMMANDER_ID,
    CUTOVER_ID,
    DISPOSITIONS,
    REVIEW,
    RUN_ID,
    SyntheticFixture,
    make_fixture,
)

__all__: tuple[str, ...] = ()


def _full_pipeline(
    fixture: SyntheticFixture,
) -> tuple[FrozenExport, FrozenExport, dict[str, Any], dict[str, Any], ImportPlan]:
    root = ReadOnlySourceRoot(fixture.root)
    first = freeze_export(
        fixture.selection,
        root,
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage="export_a",
        verifier=fixture.verifier,
    )
    second = freeze_export(
        fixture.selection,
        root,
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage="export_b",
        verifier=fixture.verifier,
    )
    equality = compare_exports(first, second, review=REVIEW, signer=fixture.signer)
    alias_map = fixture.alias_map(equality)
    plan = build_import_plan(
        first,
        equality,
        alias_map,
        run_id=RUN_ID,
        cutover_id=CUTOVER_ID,
        commander_custodian_id=COMMANDER_ID,
        verifier=fixture.verifier,
    )
    return first, second, equality, alias_map, plan


def test_every_legacy_request_id_has_exactly_one_disposition(
    tmp_path: Path,
) -> None:
    """Every legacy source ID in the alias map has exactly one disposition entry."""
    fixture = make_fixture(tmp_path)
    _, _, _, alias_map, _ = _full_pipeline(fixture)
    entries = alias_map["entries"]
    # Every entry has a disposition from the reviewed set.
    reviewed_dispositions = {
        "created_ticket",
        "alias_linked_existing",
        "project_checkpoint_definition",
        "decision_link",
        "external_effect_link",
        "artifact_linked_not_proof",
        "provenance_only",
        "exact_duplicate",
        "excluded_out_of_scope",
    }
    for entry in entries:
        assert entry["disposition"] in reviewed_dispositions, (
            f"unreviewed disposition: {entry['disposition']}"
        )
    # Every identity appears exactly once.
    identities = [
        (e["identity"]["namespace"], e["identity"]["immutable_source_id"]) for e in entries
    ]
    assert len(identities) == len(set(identities)), "duplicate identity in alias map"


def test_disposition_report_is_exhaustive_and_matches_vectors(
    tmp_path: Path,
) -> None:
    """The disposition counts in the alias map match the frozen vectors exactly."""
    fixture = make_fixture(tmp_path)
    _, _, _, alias_map, _ = _full_pipeline(fixture)
    entries = alias_map["entries"]
    counts = Counter(e["disposition"] for e in entries)
    # The disposition counts must match the DISPOSITIONS tuple from the fixture.
    expected = Counter(DISPOSITIONS)
    assert counts == expected, f"disposition mismatch: {counts} != {expected}"
    # No attention_required entries.
    assert counts.get("attention_required", 0) == 0


def test_stable_aliases_are_exact_and_reviewed(tmp_path: Path) -> None:
    """Stable aliases carry forward the exact reviewed set with target ticket IDs."""
    fixture = make_fixture(tmp_path)
    _, _, _, alias_map, _ = _full_pipeline(fixture)
    stable_aliases = alias_map["stable_aliases"]
    # Every stable alias has a stable_item_id and target_ticket_id.
    for alias in stable_aliases:
        assert alias["stable_item_id"], "missing stable_item_id"
        assert alias["target_ticket_id"], "missing target_ticket_id"
    # The stable aliases match the fixture's stable IDs exactly.
    stable_ids = {alias["stable_item_id"] for alias in stable_aliases}
    assert stable_ids == set(fixture.stable_ids)


def test_zero_bulk_import_is_a_valid_plan(tmp_path: Path) -> None:
    """A zero-operation import plan is valid — zero bulk import is allowed.

    D27: 'Bulk legacy import stays dormant behind a separate future decision.'
    The tool must accept a plan with zero operations (zero bulk import)
    as a valid plan. The minimal carry-forward set can be empty — every
    entry is either excluded_out_of_scope or project_checkpoint_definition,
    both of which produce no import operations.
    """
    fixture = make_fixture(tmp_path)
    first, _, equality, alias_map, _ = _full_pipeline(fixture)
    # Build a zero-operation plan by setting all dispositions to
    # excluded_out_of_scope (produces no operations).
    zero_alias_map = dict(alias_map)
    for entry in zero_alias_map["entries"]:
        entry["disposition"] = "excluded_out_of_scope"
        entry["planned_target_ref"] = None
        entry["reason_code"] = "reviewed_zero_bulk_import"
    zero_alias_map["attention_required"] = 0
    zero_alias_map = fixture.signer.seal(zero_alias_map, "map_digest")
    # The zero-operation plan must build successfully.
    plan = build_import_plan(
        first,
        equality,
        zero_alias_map,
        run_id=RUN_ID,
        cutover_id=CUTOVER_ID,
        commander_custodian_id=COMMANDER_ID,
        verifier=fixture.verifier,
    )
    # The plan is valid — it builds and seals without error.
    sealed = seal_import_plan(plan, first, review=REVIEW, signer=fixture.signer)
    assert sealed["batch_count"] == len(plan.batches)
    # Zero bulk import means no bulk importer is needed — the plan is
    # a valid carry-forward plan that creates no new tickets.
    assert "plan_digest" in sealed


def test_signed_source_selection_alias_map_and_import_plan_are_valid(
    tmp_path: Path,
) -> None:
    """The signed source-selection, alias-map, and import-plan objects are valid."""
    fixture = make_fixture(tmp_path)
    first, _second, equality, alias_map, plan = _full_pipeline(fixture)

    # Source selection is signed and verified.
    assert "manifest_digest" in fixture.selection
    assert "signature" in fixture.selection
    digest = fixture.verifier.verify(fixture.selection, "manifest_digest")
    assert digest == fixture.selection["manifest_digest"]

    # Export equality is signed and verified.
    assert "report_digest" in equality
    assert "signature" in equality
    eq_digest = fixture.verifier.verify(equality, "report_digest")
    assert eq_digest == equality["report_digest"]

    # Alias map is signed and verified.
    assert "map_digest" in alias_map
    assert "signature" in alias_map
    map_digest = fixture.verifier.verify(alias_map, "map_digest")
    assert map_digest == alias_map["map_digest"]

    # Import plan is sealed and valid.
    sealed_plan = seal_import_plan(plan, first, review=REVIEW, signer=fixture.signer)
    assert "plan_digest" in sealed_plan
    assert "signature" in sealed_plan
    plan_digest = fixture.verifier.verify(sealed_plan, "plan_digest")
    assert plan_digest == sealed_plan["plan_digest"]


def test_only_reviewed_still_actionable_set_is_carried_forward(
    tmp_path: Path,
) -> None:
    """Excluded items are not carried forward — only the reviewed still-actionable set."""
    fixture = make_fixture(tmp_path)
    _first, _unused, _equality, alias_map, plan = _full_pipeline(fixture)
    # The excluded items (R546, R669+) must not appear in the plan operations.
    excluded_ids = {"R546", "R669+"}
    for batch in plan.batches:
        for op in batch.operations:
            op_data = op.model_dump(mode="json", by_alias=True)
            source = op_data.get("source", {})
            assert source.get("immutable_source_id") not in excluded_ids, (
                f"excluded item carried forward: {source.get('immutable_source_id')}"
            )
    # The alias map entries for excluded items have disposition "excluded_out_of_scope".
    excluded_entries = [
        e for e in alias_map["entries"] if e["disposition"] == "excluded_out_of_scope"
    ]
    assert len(excluded_entries) == 1, "exactly one excluded_out_of_scope entry"
    # The excluded entry's identity must be a reviewed request ID.
    excluded_id = excluded_entries[0]["identity"]["immutable_source_id"]
    assert excluded_id in set(fixture.request_ids), f"excluded id not in request IDs: {excluded_id}"
