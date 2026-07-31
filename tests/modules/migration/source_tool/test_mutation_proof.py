"""Conservation derivation tests.

AC4 (narrowed): reconcile.py derives its conservation counts from the signed
frozen export; corpus cardinality remains schema-pinned until S5 (the exit
plan's S5 compares the exact signed set, not the number 14). The structural
guard in test_structural_guard.py proves no fixture-corpus cardinality
literals (86, 243, 27, 14) exist as module-level constants in product code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ctower_client.models import (
    CtowerProjectImportRun,
    ProjectDeliveryView,
)
from tools.migration.ctower_project.ctower_project_source.executor import (
    ImportPassReceipt,
    execute_import,
)
from tools.migration.ctower_project.ctower_project_source.exporter import (
    FrozenExport,
    compare_exports,
    freeze_export,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import (
    ImportPlan,
    build_import_plan,
)
from tools.migration.ctower_project.ctower_project_source.reconcile import reconcile
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
from .test_import_reconcile import FakeGeneratedClient, _delivery, _run

__all__: tuple[str, ...] = ()


def _frozen_pair(
    fixture: SyntheticFixture,
) -> tuple[FrozenExport, dict[str, Any], dict[str, Any], ImportPlan]:
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
    return first, equality, alias_map, plan


def _full_reconcile(
    fixture: SyntheticFixture,
    frozen: FrozenExport,
    equality: dict[str, Any],
    alias_map: dict[str, Any],
    plan: ImportPlan,
    *,
    run: CtowerProjectImportRun | None = None,
    delivery: ProjectDeliveryView | None = None,
) -> dict[str, Any]:
    client = FakeGeneratedClient()
    first = execute_import(plan, client=client, apply=True)
    second = execute_import(plan, client=client, apply=True)
    assert isinstance(first, ImportPassReceipt)
    assert isinstance(second, ImportPassReceipt)
    client.run = run or _run(fixture, frozen, plan)
    client.delivery = delivery or _delivery(fixture, client.run)
    return reconcile(
        frozen,
        equality,
        alias_map,
        plan,
        first,
        second,
        client=client,
        review=REVIEW,
        signer=fixture.signer,
    )


def test_reconcile_accepts_standard_fixture_checkpoint_set(tmp_path: Path) -> None:
    """Reconcile accepts the standard fixture's checkpoint set.

    The run and delivery are built from the fixture's own checkpoint keys
    (derived from the frozen export), so reconcile must accept. This is the
    happy path — it does not change the checkpoint count (that is impossible
    within schema bounds until S5).
    """
    fixture = make_fixture(tmp_path)
    frozen, equality, alias_map, plan = _frozen_pair(fixture)

    # The run and delivery are built from the fixture's own checkpoint keys,
    # so they already derive counts from the corpus. Reconcile must accept.
    report = _full_reconcile(fixture, frozen, equality, alias_map, plan)
    assert report["expected_graph"] == report["actual_graph"]


def test_reconcile_refuses_when_target_checkpoint_count_mismatches(
    tmp_path: Path,
) -> None:
    """If the target has fewer checkpoints than the corpus, reconcile refuses.

    The conservation check must derive the expected count from the frozen
    artifacts, not from a hardcoded literal.
    """
    fixture = make_fixture(tmp_path)
    frozen, equality, alias_map, plan = _frozen_pair(fixture)

    # Build a delivery with one fewer checkpoint row — conservation must refuse.
    run = _run(fixture, frozen, plan)
    full_delivery = _delivery(fixture, run)
    trimmed_delivery = full_delivery.model_copy(update={"rows": full_delivery.rows[:-1]})
    with pytest.raises(MigrationRefusal) as caught:
        _full_reconcile(
            fixture,
            frozen,
            equality,
            alias_map,
            plan,
            run=run,
            delivery=trimmed_delivery,
        )
    assert caught.value.code == RefusalCode.RECONCILIATION_MISMATCH


def test_dropping_one_alias_entry_refuses_request_identity_coverage(
    tmp_path: Path,
) -> None:
    """Dropping one alias_map entry must refuse with RECONCILIATION_MISMATCH.

    The alias conservation predicate (reconcile._verify_alias_conservation)
    derives the expected request-identity set from the signed frozen export
    and asserts every exported request identity has exactly one alias-map
    entry. Dropping one entry breaks request identity coverage.
    """
    fixture = make_fixture(tmp_path)
    frozen, equality, alias_map, _plan = _frozen_pair(fixture)

    # Drop one alias-map entry and re-seal.
    trimmed_map = {**alias_map, "entries": alias_map["entries"][:-1]}
    trimmed_map = fixture.signer.seal(trimmed_map, "map_digest")

    # Rebuild the plan so its alias_map_digest matches the trimmed map,
    # otherwise reconcile refuses on "artifact binding" before reaching
    # the identity-coverage predicate we are testing.
    trimmed_plan = build_import_plan(
        frozen,
        equality,
        trimmed_map,
        run_id=RUN_ID,
        cutover_id=CUTOVER_ID,
        commander_custodian_id=COMMANDER_ID,
        verifier=fixture.verifier,
    )

    with pytest.raises(MigrationRefusal) as caught:
        _full_reconcile(fixture, frozen, equality, trimmed_map, trimmed_plan)
    assert caught.value.code == RefusalCode.RECONCILIATION_MISMATCH
    assert "request identity coverage" in caught.value.context
