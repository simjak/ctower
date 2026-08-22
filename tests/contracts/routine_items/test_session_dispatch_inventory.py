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

_REGISTRY_DENOMINATOR = 17
_ITEM_PATH_REFERENCES = 10


def test_active_routine_contracts_and_surfaces_contain_no_session_dispatch() -> None:
    pack_root = ROOT / "packs/routines"
    packs = tuple(sorted(pack_root.glob("*/v1.yaml")))
    assert len(packs) == _REGISTRY_DENOMINATOR
    item_path = 0
    for path in packs:
        pack = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        assert pack.get("handler_kind") != "beat_dispatch", path
        assert "target_session" not in json.dumps(pack), path
        item_path += 1 if pack.get("handler_kind") == "routine_item" else 0
    assert item_path == _ITEM_PATH_REFERENCES

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
