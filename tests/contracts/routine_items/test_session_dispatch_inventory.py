"""AC-RWI-01 inventory: active routines have no session-targeted dispatch path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]


_REMOVED_FILES = (
    "contracts/runtime/routine-v3.schema.json",
    "contracts/runtime/beat-dispatch-effect.schema.json",
    "packages/ctower-kernel/src/ctower_kernel/runtime/beats.py",
    "packages/ctower-kernel/src/ctower_kernel/runtime/_beat_dispatch_sql.py",
    "apps/ctower-api/src/ctower_api/_beat_dispatch_routes.py",
    "apps/ctowerctl/src/ctowerctl/_beat_dispatch_commands.py",
)

_UI_REMOVED_FILES = (
    "apps/ctower-ui/src/app/heartbeats/page.tsx",
    "apps/ctower-ui/src/read/beatRegistry.ts",
    "apps/ctower-ui/src/read/sources/cadenceHealth.ts",
)


def test_active_routine_contracts_and_surfaces_contain_no_session_dispatch() -> None:
    pack_root = ROOT / "packs/routines"
    packs = tuple(sorted(pack_root.glob("*/v1.yaml")))
    assert packs
    for path in packs:
        pack = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        assert pack.get("handler_kind") != "beat_dispatch", path
        assert "target_session" not in json.dumps(pack), path

    openapi = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    assert not any("beat" in path for path in cast(dict[str, object], openapi["paths"]))
    for relative in _REMOVED_FILES:
        assert not (ROOT / relative).exists(), relative


def test_session_dispatch_inventory_names_no_obsolete_target_symbols() -> None:
    source_roots = (
        ROOT / "packages/ctower-kernel/src/ctower_kernel/runtime",
        ROOT / "apps/ctower-api/src/ctower_api",
        ROOT / "apps/ctowerctl/src/ctowerctl",
    )
    forbidden = ("BeatDispatch", "beat_dispatch", "target_session", "beat-dispatch")
    violations = [
        f"{path}:{needle}"
        for source_root in source_roots
        for path in source_root.rglob("*.py")
        for needle in forbidden
        if needle in path.read_text(encoding="utf-8")
    ]
    assert violations == []


def test_ui_has_no_removed_session_dispatch_paths() -> None:
    ui_sources = (ROOT / "apps/ctower-ui/src", ROOT / "apps/ctower-ui/README.md")
    forbidden = (
        "beat-routines",
        "beat-dispatches",
        "targetSession",
        "BeatRoutineRead",
        "BeatDispatchRead",
        "cadenceRegistry",
        '"/heartbeats"',
    )
    paths = tuple(
        path
        for source_root in ui_sources
        for path in (
            tuple(source_root.rglob("*.ts")) + tuple(source_root.rglob("*.tsx"))
            if source_root.is_dir()
            else (source_root,)
        )
    )
    violations = [
        f"{path}:{needle}"
        for path in paths
        for needle in forbidden
        if needle in path.read_text(encoding="utf-8")
    ]
    assert violations == []
    for relative in _UI_REMOVED_FILES:
        assert not (ROOT / relative).exists(), relative
