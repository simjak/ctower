from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tools.migration.ctower_project.ctower_project_source.exporter import (
    FrozenExport,
    compare_exports,
    freeze_export,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import build_import_plan
from tools.migration.ctower_project.ctower_project_source.refusal import (
    MigrationRefusal,
    RefusalCode,
)
from tools.migration.ctower_project.ctower_project_source.source import ReadOnlySourceRoot

from .fixtures import (
    COMMANDER_ID,
    CUTOVER_ID,
    REVIEW,
    RUN_ID,
    SyntheticFixture,
    make_fixture,
)

__all__: tuple[str, ...] = ()


def _artifacts(tmp_path: Path) -> tuple[Any, dict[str, Any], dict[str, Any], Any]:
    fixture = make_fixture(tmp_path)
    root = ReadOnlySourceRoot(tmp_path)
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
    return fixture, equality, fixture.alias_map(equality), first


def _plan(
    fixture: SyntheticFixture,
    equality: dict[str, Any],
    alias: dict[str, Any],
    frozen: FrozenExport,
) -> None:
    build_import_plan(
        frozen,
        equality,
        alias,
        run_id=RUN_ID,
        cutover_id=CUTOVER_ID,
        commander_custodian_id=COMMANDER_ID,
        verifier=fixture.verifier,
    )


def test_attention_and_duplicate_alias_identities_refuse(tmp_path: Path) -> None:
    fixture, equality, alias, frozen = _artifacts(tmp_path)
    alias["entries"][0]["disposition"] = "attention_required"
    alias["entries"][0]["planned_target_ref"] = None
    alias = fixture.signer.seal(alias, "map_digest")
    with pytest.raises(MigrationRefusal) as caught:
        _plan(fixture, equality, alias, frozen)
    assert caught.value.code == RefusalCode.ALIAS_ATTENTION_REQUIRED
    alias = fixture.alias_map(equality)
    alias["entries"][1]["identity"] = dict(alias["entries"][0]["identity"])
    alias["entries"][1]["reason_code"] = "different_reviewed_mapping"
    alias = fixture.signer.seal(alias, "map_digest")
    with pytest.raises(MigrationRefusal) as caught:
        _plan(fixture, equality, alias, frozen)
    assert caught.value.code == RefusalCode.ALIAS_IDENTITY_DUPLICATE


def test_alias_identity_outside_export_and_scope_rebinding_refuse(tmp_path: Path) -> None:
    fixture, equality, alias, frozen = _artifacts(tmp_path)
    alias["entries"][0]["identity"]["immutable_source_id"] = "R999"
    alias = fixture.signer.seal(alias, "map_digest")
    with pytest.raises(MigrationRefusal) as caught:
        _plan(fixture, equality, alias, frozen)
    assert caught.value.code == RefusalCode.ALIAS_OUTSIDE_EXPORT
    alias = fixture.alias_map(equality)
    alias["cutover_id"] = "775407dd-4133-4b4e-89ef-04bc37075078"
    alias = fixture.signer.seal(alias, "map_digest")
    with pytest.raises(MigrationRefusal) as caught:
        _plan(fixture, equality, alias, frozen)
    assert caught.value.code == RefusalCode.IMPORT_SCOPE_MISMATCH
