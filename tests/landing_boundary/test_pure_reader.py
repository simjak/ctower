"""The check is a pure reader: nothing it can import could write authoritative state."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

__all__: tuple[str, ...] = ()

_MODULE_ROOT = Path(__file__).parents[2] / "tools" / "landing_boundary"
_PERMITTED_ROOTS = frozenset({"pydantic", "ctower_kernel", "tools"})
_PERMITTED_KERNEL_MODULES = frozenset({"ctower_kernel.workflow"})


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            imported.add(node.module)
    return imported


def _third_party(imported: set[str]) -> set[str]:
    return {name for name in imported if name.split(".")[0] not in sys.stdlib_module_names}


@pytest.mark.parametrize("path", sorted(_MODULE_ROOT.glob("*.py")), ids=lambda path: path.name)
def test_the_check_imports_no_client_and_no_persistence(path: Path) -> None:
    imported = _third_party(_imported_modules(path.read_text(encoding="utf-8")))

    assert {name.split(".")[0] for name in imported} <= _PERMITTED_ROOTS


@pytest.mark.parametrize("path", sorted(_MODULE_ROOT.glob("*.py")), ids=lambda path: path.name)
def test_the_check_reads_the_kernel_only_for_the_pinned_graph(path: Path) -> None:
    imported = _third_party(_imported_modules(path.read_text(encoding="utf-8")))
    kernel = {name for name in imported if name.startswith("ctower_kernel")}

    assert kernel <= _PERMITTED_KERNEL_MODULES


@pytest.mark.parametrize("path", sorted(_MODULE_ROOT.glob("*.py")), ids=lambda path: path.name)
def test_the_check_owns_only_its_own_tools_modules(path: Path) -> None:
    imported = _third_party(_imported_modules(path.read_text(encoding="utf-8")))
    owned = {name for name in imported if name.startswith("tools")}

    assert all(name.startswith("tools.landing_boundary") for name in owned)
