"""Closed-world authored Routine pack loading through the public worker boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import ctower_api.control_worker as control_worker_module
from ctower_kernel.runtime import RoutineRevision

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
EXPECTED_ROUTINE_PACKS = 12


def test_manibo_report_pack_loads_as_a_pointer_only_work_item() -> None:
    revisions = control_worker_module.load_routine_revisions(ROOT / "packs")
    references = {revision.routine_ref for revision in revisions}
    manibo_report = next(
        revision for revision in revisions if revision.routine_ref == "mc-cron.manibo-report@1"
    )

    assert len(revisions) == EXPECTED_ROUTINE_PACKS
    assert "ctower.beat.director-drive@1" not in references
    assert manibo_report.timezone == "Europe/Vilnius"
    assert manibo_report.minute_marks == (0, 30)
    assert manibo_report.hour_marks is None
    assert manibo_report.catch_up.value == "skip_missed"
    assert manibo_report.routine_item is not None
    assert manibo_report.routine_item.knowledge_ref == "mc-cron.manibo-report"
    assert manibo_report.routine_item.owner_seat == "manibo-commander"


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
