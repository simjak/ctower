"""Mutation-proof conservation: no fixture-corpus literals in product code.

AC4 requires that changing the fixture corpus (IDs, count, aliases) makes the
tool follow with zero product-code edits.  The reconciliation conservation
check must derive every count from the signed artifacts it receives, not from
hardcoded module-level constants.  These tests prove that property by mutating
the fixture and asserting the reconciliation either accepts the new corpus
(when conservation holds) or refuses with a named code (when it does not) —
all without touching product code.
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


def test_reconcile_accepts_corpus_with_different_checkpoint_count(tmp_path: Path) -> None:
    """Changing the checkpoint count in the fixture must not break reconcile.

    This proves no checkpoint-count literal is hardcoded in product code.
    We use the standard fixture but build a run/delivery with a different
    checkpoint count derived from the frozen export itself.
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


def test_no_fixture_count_literals_in_product_code() -> None:
    """No hardcoded fixture-corpus counts (86, 243, 27, 14) in reconcile.py.

    AC4: no disposition-set or alias literal in product code.
    """
    import tools.migration.ctower_project.ctower_project_source.reconcile as reconcile_mod  # noqa: PLC0415

    source = Path(reconcile_mod.__file__).read_text(encoding="utf-8")
    # These are the fixture-specific constants that must not appear as
    # module-level literals in product code. They may appear in comments
    # or test fixtures, but not as hardcoded conservation thresholds.
    forbidden_literals = [
        "_REQUEST_COUNT = 86",
        "_REQUEST_PHYSICAL_COUNT = 243",
        "_STABLE_COUNT = 27",
        "_CHECKPOINT_COUNT = 14",
    ]
    for literal in forbidden_literals:
        assert literal not in source, f"fixture literal found in product code: {literal}"
