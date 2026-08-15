"""Closed-world authored Routine pack loading through the public worker boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import ctower_api.control_worker as control_worker_module
from ctower_kernel.runtime import RoutineRevision

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
EXPECTED_ROUTINE_PACKS = 17
DIRECTOR_DRIVE_PROMPT_BYTES = 566


def test_director_drive_pack_loads_exact_schedule_target_and_prompt_digest() -> None:
    revisions = control_worker_module.load_routine_revisions(ROOT / "packs")
    references = {revision.routine_ref for revision in revisions}
    director_drive = next(
        revision for revision in revisions if revision.routine_ref == "ctower.beat.director-drive@1"
    )

    assert len(revisions) == EXPECTED_ROUTINE_PACKS
    assert "ctower.beat.migration@1" not in references
    assert director_drive.timezone == "UTC"
    assert director_drive.minute_marks == (4, 34)
    assert director_drive.hour_marks is None
    assert director_drive.catch_up.value == "skip_missed"
    assert director_drive.beat_dispatch is not None
    assert director_drive.beat_dispatch.beat_key == "director-drive"
    assert director_drive.beat_dispatch.prompt_source == "state/beats/director-drive.txt"
    assert director_drive.beat_dispatch.target_session == "commander"
    prompt_bytes = director_drive.beat_dispatch.prompt.encode("utf-8")
    assert len(prompt_bytes) == DIRECTOR_DRIVE_PROMPT_BYTES
    assert prompt_bytes.endswith(b"\n")
    assert hashlib.sha256(prompt_bytes).hexdigest() == (
        "f2fcdf0589b945a89a6d29e404f33b1221f4e55c3987c1cf550212f258e3fe1c"
    )
    assert director_drive.beat_dispatch.prompt_sha256 == (
        "sha256:f2fcdf0589b945a89a6d29e404f33b1221f4e55c3987c1cf550212f258e3fe1c"
    )


def test_routine_pack_closed_world_names_either_one_sided_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader_globals = control_worker_module.load_routine_revisions.__globals__
    current_paths = cast(tuple[str, ...], loader_globals["_PACK_PATHS"])
    current_references = cast(frozenset[str], loader_globals["_EXPECTED_ROUTINE_REFS"])
    migration_path = "routines/ctower.beat.migration/v1.yaml"
    director_path = "routines/ctower.beat.director-drive/v1.yaml"

    monkeypatch.setitem(
        loader_globals,
        "_EXPECTED_ROUTINE_REFS",
        (current_references - {"ctower.beat.director-drive@1"}) | {"ctower.beat.migration@1"},
    )
    with pytest.raises(
        ValueError,
        match=r"ctower\.beat\.director-drive@1.*ctower\.beat\.migration@1",
    ):
        control_worker_module.load_routine_revisions(ROOT / "packs")

    original_loader = cast(Callable[[Path], RoutineRevision], loader_globals["_load_revision"])
    director_revision = original_loader(ROOT / "packs" / director_path)

    def load_with_old_path(path: Path) -> RoutineRevision:
        if path == ROOT / "packs" / migration_path:
            return replace(director_revision, routine_ref="ctower.beat.migration@1")
        return original_loader(path)

    monkeypatch.setitem(loader_globals, "_EXPECTED_ROUTINE_REFS", current_references)
    monkeypatch.setitem(
        loader_globals,
        "_PACK_PATHS",
        tuple(migration_path if path == director_path else path for path in current_paths),
    )
    monkeypatch.setitem(loader_globals, "_load_revision", load_with_old_path)
    with pytest.raises(
        ValueError,
        match=r"ctower\.beat\.migration@1.*ctower\.beat\.director-drive@1",
    ):
        control_worker_module.load_routine_revisions(ROOT / "packs")
