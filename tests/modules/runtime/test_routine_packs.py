"""Closed-world authored Routine pack loading through the public worker boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

import ctower_api.control_worker as control_worker_module
from ctower_kernel.runtime import RoutineRevision

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
EXPECTED_ROUTINE_PACKS = 17
EXPECTED_ITEM_PATH_REFERENCES = 10


def test_manibo_report_pack_loads_as_a_pointer_only_work_item() -> None:
    revisions = control_worker_module.load_routine_revisions(ROOT / "packs")
    references = {revision.routine_ref for revision in revisions}
    manibo_report = next(
        revision for revision in revisions if revision.routine_ref == "mc-cron.manibo-report@1"
    )

    assert len(revisions) == EXPECTED_ROUTINE_PACKS
    assert "ctower.beat.director-drive@1" in references
    assert manibo_report.timezone == "Europe/Vilnius"
    assert manibo_report.minute_marks == (0, 30)
    assert manibo_report.hour_marks is None
    assert manibo_report.catch_up.value == "skip_missed"
    assert manibo_report.routine_item is not None
    assert manibo_report.routine_item.knowledge_ref == "mc-cron.manibo-report"
    assert manibo_report.routine_item.document_id == UUID("a98100ac-1ac2-56f4-8754-e9550ebf67e7")
    assert manibo_report.routine_item.owner_seat == "manibo-commander"


def test_registry_derived_inventory_dispositions_every_one_of_seventeen_references() -> None:
    """AC-RWI-01/06: the whole registry is the denominator and none of it is omitted."""

    revisions = control_worker_module.load_routine_revisions(ROOT / "packs")
    knowledge_root = ROOT / "packages/ctower-kernel/src/ctower_kernel/knowledge/static/org"
    inventory = {
        revision.routine_ref: _disposition(revision, knowledge_root)
        for revision in sorted(revisions, key=lambda revision: revision.routine_ref)
    }
    for routine_ref, disposition in inventory.items():
        print(f"registry-inventory routine={routine_ref} disposition={disposition}")

    assert len(inventory) == EXPECTED_ROUTINE_PACKS
    item_path = {ref for ref, value in inventory.items() if value.startswith("item-path")}
    assert len(item_path) == EXPECTED_ITEM_PATH_REFERENCES
    assert {ref for ref in item_path if ref.startswith("ctower.beat.")} == {
        "ctower.beat.health@1",
        "ctower.beat.director-drive@1",
        "ctower.beat.bhloop@1",
        "ctower.beat.sprint@1",
        "ctower.beat.digest@1",
    }
    assert not [value for value in inventory.values() if value == "omitted"]
    assert all(
        not hasattr(revision, "beat_dispatch") and "target_session" not in repr(revision)
        for revision in revisions
    )


def _disposition(revision: RoutineRevision, knowledge_root: Path) -> str:
    """Name why each registered reference is or is not on the work-item path."""

    item = revision.routine_item
    if item is not None:
        document = knowledge_root / f"{item.knowledge_ref}.md"
        if not document.is_file():
            return "omitted"
        return f"item-path knowledge={item.knowledge_ref} owner={item.owner_seat}"
    if revision.dream_dispatch is not None:
        return "not-item-path dream-dispatch effect, no session target"
    return f"not-item-path fixed-operation {revision.handler_kind}, no session target"


def test_routine_pack_closed_world_names_either_one_sided_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader_globals = control_worker_module.load_routine_revisions.__globals__
    current_paths = cast(tuple[str, ...], loader_globals["_PACK_PATHS"])
    current_references = cast(frozenset[str], loader_globals["_EXPECTED_ROUTINE_REFS"])
    migration_path = "routines/mc-cron.migration/v1.yaml"
    report_path = "routines/mc-cron.manibo-report/v1.yaml"

    monkeypatch.setitem(
        loader_globals,
        "_EXPECTED_ROUTINE_REFS",
        (current_references - {"mc-cron.manibo-report@1"}) | {"mc-cron.migration@1"},
    )
    with pytest.raises(
        ValueError,
        match=r"mc-cron\.manibo-report@1.*mc-cron\.migration@1",
    ):
        control_worker_module.load_routine_revisions(ROOT / "packs")

    original_loader = cast(Callable[[Path], RoutineRevision], loader_globals["_load_revision"])
    report_revision = original_loader(ROOT / "packs" / report_path)

    def load_with_old_path(path: Path) -> RoutineRevision:
        if path == ROOT / "packs" / migration_path:
            return replace(report_revision, routine_ref="mc-cron.migration@1")
        return original_loader(path)

    monkeypatch.setitem(loader_globals, "_EXPECTED_ROUTINE_REFS", current_references)
    monkeypatch.setitem(
        loader_globals,
        "_PACK_PATHS",
        tuple(migration_path if path == report_path else path for path in current_paths),
    )
    monkeypatch.setitem(loader_globals, "_load_revision", load_with_old_path)
    with pytest.raises(
        ValueError,
        match=r"mc-cron\.migration@1.*mc-cron\.manibo-report@1",
    ):
        control_worker_module.load_routine_revisions(ROOT / "packs")
