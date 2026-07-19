"""Deterministic generated Python client contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from tools.codegen.generator import check

ROOT = Path(__file__).parents[3]


def test_generated_client_is_owned_and_byte_stable() -> None:
    check(ROOT)
    manifest = json.loads((ROOT / "generated/.generated-manifest.json").read_text(encoding="utf-8"))
    artifacts = cast(list[dict[str, object]], manifest["artifacts"])
    entries = [item for item in artifacts if item["id"] == "http-python-client"]

    assert len(entries) == 1
    outputs = cast(list[dict[str, str]], entries[0]["outputs"])
    assert {entry["path"] for entry in outputs} == {
        "generated/python/ctower_client/__init__.py",
        "generated/python/ctower_client/client.py",
        "generated/python/ctower_client/models.py",
    }
    for entry in outputs:
        digest = hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == f"sha256:{digest}"


def test_generated_python_carries_do_not_edit_notice() -> None:
    paths = tuple(sorted((ROOT / "generated/python/ctower_client").glob("*.py")))

    assert {path.name for path in paths} == {"__init__.py", "client.py", "models.py"}
    for path in paths:
        assert path.read_text(encoding="utf-8").startswith(
            '"""DO NOT EDIT: generated file; regenerate from declared inputs.'
        )
