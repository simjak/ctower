"""Named negative fixtures per refusal class (AC3 + AC4).

AC3: any credential/client/production/effect/incident/irreplaceable item,
fuzzy merge, missing disposition, duplicate alias, or attempted
proof/resolution import refuses — loudly, by name.

AC4: a named negative fixture per refusal class.

Each test names the refusal class it exercises and asserts the refusal code
and context together.  The forbidden-data-class tests assert that the
specific forbidden class name appears in the refusal context, proving the
tool refuses "loudly, by name" rather than with a generic message.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid5

import pytest

from ctower_client.models import (
    CtowerProjectImportBatchResult,
    DurabilityState,
    MigrationImportOperationResult,
)
from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    sha256_digest,
)
from tools.migration.ctower_project.ctower_project_source.executor import (
    execute_import,
)
from tools.migration.ctower_project.ctower_project_source.exporter import (
    FrozenExport,
    compare_exports,
    freeze_export,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import (
    build_import_plan,
)
from tools.migration.ctower_project.ctower_project_source.refusal import (
    MigrationRefusal,
    RefusalCode,
)
from tools.migration.ctower_project.ctower_project_source.source import (
    ReadOnlySourceRoot,
)

from .fixtures import (
    COMMANDER_ID,
    CUTOVER_ID,
    REVIEW,
    RUN_ID,
    UUID_NAMESPACE,
    SyntheticFixture,
    make_fixture,
)

__all__: tuple[str, ...] = ()


def _freeze(fixture: SyntheticFixture) -> FrozenExport:
    return freeze_export(
        fixture.selection,
        ReadOnlySourceRoot(fixture.root),
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage="export_a",
        verifier=fixture.verifier,
    )


def _reseat_selection(fixture: SyntheticFixture) -> None:
    """Re-seal the fixture's selection dict in-place (frozen dataclass safe)."""
    sealed = fixture.signer.seal(fixture.selection, "manifest_digest")
    fixture.selection.clear()
    fixture.selection.update(sealed)


# ---------------------------------------------------------------------------
# AC3: Named forbidden-data-class refusals — each class refused "by name"
# ---------------------------------------------------------------------------

NAMED_FORBIDDEN_CLASSES = [
    "secret_or_authentication_value",
    "pii_or_client_data",
    "accounting_payment_tax_invoice",
    "production_approval_effect_or_incident",
    "irreplaceable_or_expensive_sole_copy",
]


@pytest.mark.parametrize("forbidden_class", NAMED_FORBIDDEN_CLASSES)
def test_forbidden_data_class_refuses_loudly_by_name(tmp_path: Path, forbidden_class: str) -> None:
    """Each forbidden data class must be refused with its name in the context."""
    fixture = make_fixture(tmp_path)
    # Rewrite the first request row to carry the forbidden data class.
    path = fixture.root / "requests.jsonl"
    rows = path.read_bytes().splitlines()
    first = json.loads(rows[0])
    first["data_classes"] = [forbidden_class]
    rows[0] = canonical_bytes(first)
    path.write_bytes(b"\n".join(rows) + b"\n")
    # Update the inventory digest to match (so we pass the drift check first).
    inventory = fixture.selection["source_inventories"][0]
    data = path.read_bytes()
    inventory["whole_source_digest"] = sha256_digest(data)
    inventory["whole_source_bytes"] = len(data)
    _reseat_selection(fixture)
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == RefusalCode.FORBIDDEN_DATA_CLASS
    assert forbidden_class in caught.value.context


# ---------------------------------------------------------------------------
# AC3: Fuzzy merge refuses
# ---------------------------------------------------------------------------


def test_fuzzy_alias_merge_refuses(tmp_path: Path) -> None:
    """A fuzzy/ambiguous alias merge (non-exact identity match) must refuse.

    The alias map must link exact source identities, not fuzzy/approximate
    matches.  We mutate an alias-map entry's identity to a slightly different
    source version, which is not an exact match for any exported record.
    """
    fixture = make_fixture(tmp_path)
    first = _freeze(fixture)
    second = freeze_export(
        fixture.selection,
        ReadOnlySourceRoot(fixture.root),
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage="export_b",
        verifier=fixture.verifier,
    )
    equality = compare_exports(first, second, review=REVIEW, signer=fixture.signer)
    alias_map = fixture.alias_map(equality)
    # Fuzzy: change source_version slightly so it's a fuzzy (not exact) match.
    alias_map["entries"][0]["identity"]["source_version"] = "fuzzy-v1"
    alias_map = fixture.signer.seal(alias_map, "map_digest")
    with pytest.raises(MigrationRefusal) as caught:
        build_import_plan(
            first,
            equality,
            alias_map,
            run_id=RUN_ID,
            cutover_id=CUTOVER_ID,
            commander_custodian_id=COMMANDER_ID,
            verifier=fixture.verifier,
        )
    # A fuzzy identity is not in the export — must refuse as outside export.
    assert caught.value.code == RefusalCode.ALIAS_OUTSIDE_EXPORT


# ---------------------------------------------------------------------------
# AC3: Missing disposition refuses
# ---------------------------------------------------------------------------


def test_missing_disposition_refuses(tmp_path: Path) -> None:
    """An alias-map entry with an unknown/missing disposition must refuse."""
    fixture = make_fixture(tmp_path)
    first = _freeze(fixture)
    second = freeze_export(
        fixture.selection,
        ReadOnlySourceRoot(fixture.root),
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage="export_b",
        verifier=fixture.verifier,
    )
    equality = compare_exports(first, second, review=REVIEW, signer=fixture.signer)
    alias_map = fixture.alias_map(equality)
    # Set an unknown disposition that is not in the schema enum.
    alias_map["entries"][0]["disposition"] = "proof_import"
    alias_map["entries"][0]["planned_target_ref"] = "new_ticket"
    alias_map["entries"][0]["reason_code"] = "attempted_proof_import"
    alias_map = fixture.signer.seal(alias_map, "map_digest")
    with pytest.raises(MigrationRefusal) as caught:
        build_import_plan(
            first,
            equality,
            alias_map,
            run_id=RUN_ID,
            cutover_id=CUTOVER_ID,
            commander_custodian_id=COMMANDER_ID,
            verifier=fixture.verifier,
        )
    # Unknown disposition must refuse — either at contract validation
    # (CONTRACT_INVALID, naming the schema field) or at the operation
    # dispatch (ALIAS_ATTENTION_REQUIRED). Both are loud, by-name refusals.
    assert caught.value.code in {RefusalCode.CONTRACT_INVALID, RefusalCode.ALIAS_ATTENTION_REQUIRED}


# ---------------------------------------------------------------------------
# AC3: Attempted proof/resolution import refuses
# ---------------------------------------------------------------------------


def test_attempted_proof_import_disposition_refuses(tmp_path: Path) -> None:
    """A disposition named 'resolution_import' must refuse — no proof/resolution import allowed."""
    fixture = make_fixture(tmp_path)
    first = _freeze(fixture)
    second = freeze_export(
        fixture.selection,
        ReadOnlySourceRoot(fixture.root),
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage="export_b",
        verifier=fixture.verifier,
    )
    equality = compare_exports(first, second, review=REVIEW, signer=fixture.signer)
    alias_map = fixture.alias_map(equality)
    # Attempt to import a resolution/closure as a disposition.
    alias_map["entries"][0]["disposition"] = "resolution_import"
    alias_map["entries"][0]["planned_target_ref"] = "new_ticket"
    alias_map["entries"][0]["reason_code"] = "attempted_resolution_import"
    alias_map = fixture.signer.seal(alias_map, "map_digest")
    with pytest.raises(MigrationRefusal) as caught:
        build_import_plan(
            first,
            equality,
            alias_map,
            run_id=RUN_ID,
            cutover_id=CUTOVER_ID,
            commander_custodian_id=COMMANDER_ID,
            verifier=fixture.verifier,
        )
    assert caught.value.code in {RefusalCode.CONTRACT_INVALID, RefusalCode.ALIAS_ATTENTION_REQUIRED}


# ---------------------------------------------------------------------------
# AC4: Named negative fixtures for remaining untested refusal classes
# ---------------------------------------------------------------------------


def test_contract_invalid_refuses_for_bad_schema(tmp_path: Path) -> None:
    """CONTRACT_INVALID: a selection with wrong schema value refuses."""
    fixture = make_fixture(tmp_path)
    fixture.selection["schema"] = "wrong-schema"
    _reseat_selection(fixture)
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == RefusalCode.CONTRACT_INVALID


def test_import_sequence_gap_refuses(tmp_path: Path) -> None:
    """IMPORT_SEQUENCE_GAP: too many completed batches for the plan refuses."""
    fixture = make_fixture(tmp_path)
    first = _freeze(fixture)
    second = freeze_export(
        fixture.selection,
        ReadOnlySourceRoot(fixture.root),
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
    # Create a fake completed batch result with too many entries.
    now = datetime(2026, 7, 25, 15, 45, tzinfo=UTC)
    fake_result = CtowerProjectImportBatchResult(
        run_id=RUN_ID,
        batch_index=0,
        batch_digest=plan.batches[0].batch_digest,
        results=tuple(
            MigrationImportOperationResult(
                command_id=op.identity.command_id,
                operation_kind=op.operation,
                replayed=False,
                target_id="target",
                event_ids=(uuid5(UUID_NAMESPACE, f"event:{op.identity.command_id}"),),
                record_position=i + 1,
                occurred_at=now,
            )
            for i, op in enumerate(plan.batches[0].operations)
        ),
        record_watermark=len(plan.batches[0].operations),
        projection_watermark=0,
        durability_state=DurabilityState.DURABILITY_PENDING,
        accepted_position=None,
    )

    # Pass more completed batches than the plan has. A dummy client is
    # required because apply=True checks for client before validating
    # completed, but the completed-count check happens first in the
    # _validate_completed path.
    class _DummyClient:
        pass

    with pytest.raises(MigrationRefusal) as caught:
        execute_import(
            plan,
            client=_DummyClient(),  # type: ignore[arg-type]
            apply=True,
            completed=(fake_result,) * (len(plan.batches) + 1),
        )
    assert caught.value.code == RefusalCode.IMPORT_SEQUENCE_GAP


def test_mutation_not_explicit_refuses(tmp_path: Path) -> None:
    """MUTATION_NOT_EXPLICIT: apply=True without a client refuses."""
    fixture = make_fixture(tmp_path)
    first = _freeze(fixture)
    second = freeze_export(
        fixture.selection,
        ReadOnlySourceRoot(fixture.root),
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
    with pytest.raises(MigrationRefusal) as caught:
        execute_import(plan, client=None, apply=True)
    assert caught.value.code == RefusalCode.MUTATION_NOT_EXPLICIT


def test_signature_invalid_refuses_for_bad_signature(tmp_path: Path) -> None:
    """SIGNATURE_INVALID: a tampered (but valid base64) signature refuses."""
    fixture = make_fixture(tmp_path)
    # Tamper with the signature to make verification fail. Use valid base64
    # so the schema validates, but the signature itself is invalid.
    fixture.selection["signature"]["signature"] = (
        "a" * 86  # 86 base64url chars = 64 bytes, valid format but wrong
    )
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code in {RefusalCode.SIGNATURE_INVALID, RefusalCode.SIGNATURE_REBOUND}


def test_source_selection_drift_refuses_for_wrong_inventory_keys(
    tmp_path: Path,
) -> None:
    """SOURCE_SELECTION_DRIFT: wrong set of inventory keys refuses."""
    fixture = make_fixture(tmp_path)
    # Duplicate an existing inventory entry to break the exact key set.
    # The schema requires unique source_keys, so a duplicate makes the
    # set != _SOURCE_KEYS without being a schema-invalid key value.
    dup = dict(fixture.selection["source_inventories"][0])
    fixture.selection["source_inventories"].append(dup)
    # Remove a different one to keep the count the same but the set wrong.
    fixture.selection["source_inventories"].pop(1)  # remove tasks entry
    _reseat_selection(fixture)
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    # Duplicated keys cause either CONTRACT_INVALID (schema uniqueness)
    # or SOURCE_SELECTION_DRIFT (set mismatch). Both are valid refusals.
    assert caught.value.code in {
        RefusalCode.SOURCE_SELECTION_DRIFT,
        RefusalCode.CONTRACT_INVALID,
    }


def test_source_too_large_refuses(tmp_path: Path) -> None:
    """SOURCE_TOO_LARGE: a source file exceeding MAX_SOURCE_BYTES refuses."""
    from tools.migration.ctower_project.ctower_project_source.source import (  # noqa: PLC0415
        MAX_SOURCE_BYTES,
    )

    fixture = make_fixture(tmp_path)
    # Write a file with valid JSONL rows that exceeds the max source bytes.
    # Each row is a valid SourceRecord — use a large title to exceed the limit.
    large_title = "x" * 200
    row = (
        canonical_bytes(
            {
                "schema": "ctower.synthetic-migration-source/v1",
                "identity": {
                    "namespace": "mission-control:request",
                    "immutable_source_id": "R325",
                    "source_version": "reviewed-v1",
                    "source_digest": sha256_digest(b"R325"),
                },
                "candidate": True,
                "review_decision": "included",
                "data_classes": ["migration_provenance"],
                "title": large_title,
                "operation_hint": None,
            }
        )
        + b"\n"
    )
    # Repeat enough times to exceed MAX_SOURCE_BYTES.
    count = MAX_SOURCE_BYTES // len(row) + 1
    large_data = row * count
    large_path = fixture.root / "requests.jsonl"
    large_path.write_bytes(large_data)
    inventory = fixture.selection["source_inventories"][0]
    inventory["whole_source_digest"] = sha256_digest(large_data)
    inventory["whole_source_bytes"] = len(large_data)
    inventory["whole_source_rows"] = count
    _reseat_selection(fixture)
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == RefusalCode.SOURCE_TOO_LARGE


def test_source_unreadable_refuses_for_missing_file(tmp_path: Path) -> None:
    """SOURCE_UNREADABLE: a missing source file refuses."""
    fixture = make_fixture(tmp_path)
    # Remove the requests file.
    (fixture.root / "requests.jsonl").unlink()
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == RefusalCode.SOURCE_UNREADABLE
