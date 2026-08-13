"""Small syntax-tree queries shared by HTTP contract tests."""

from __future__ import annotations

import ast
from pathlib import Path

__all__ = ["function_definitions"]


def function_definitions(root: Path, name: str) -> set[str]:
    definitions: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
            for node in ast.walk(tree)
        ):
            definitions.add(path.relative_to(root).as_posix())
    return definitions
