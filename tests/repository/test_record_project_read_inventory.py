"""Every public Project-scoped Record read must guard before SQL materialization."""

from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[2]
_RECORD_ROOT = ROOT / "packages/ctower-kernel/src/ctower_kernel/record"
_INTERFACE = _RECORD_ROOT / "interface.py"
_POSTGRES = _RECORD_ROOT / "postgres.py"


@dataclass(frozen=True, slots=True)
class _InventoryRow:
    public_owner: str
    public_method: str
    implementation: str
    source_path: Path
    function_name: str
    predicate_line: int | None
    materialization_line: int | None

    @property
    def composes_predicate(self) -> bool:
        return (
            self.predicate_line is not None
            and self.materialization_line is not None
            and self.predicate_line < self.materialization_line
        )

    def output(self) -> str:
        status = "yes" if self.composes_predicate else "no"
        return (
            f"{self.public_owner}.{self.public_method} -> "
            f"{self.source_path.relative_to(ROOT)}:{self.function_name} "
            f"composes-predicate {status}"
        )


class RecordProjectReadInventoryTests(unittest.TestCase):
    def test_every_project_scoped_record_read_composes_grant_before_materialization(self) -> None:
        inventory = _discover_inventory()
        self.assertTrue(inventory, "the Record Project-read inventory discovered no reads")
        for row in inventory:
            print(row.output())

        failures = [row.output() for row in inventory if not row.composes_predicate]
        self.assertEqual(
            [], failures, "unguarded Project-scoped Record reads: " + "; ".join(failures)
        )


def _discover_inventory() -> tuple[_InventoryRow, ...]:
    interface = ast.parse(_INTERFACE.read_text(encoding="utf-8"), filename=str(_INTERFACE))
    public_reads = tuple(_public_reads(interface))
    postgres = ast.parse(_POSTGRES.read_text(encoding="utf-8"), filename=str(_POSTGRES))
    aliases = _postgres_sql_aliases(postgres)
    adapter_methods = tuple(
        (method, implementation, target)
        for owner, method in public_reads
        for implementation, target in _adapter_targets(postgres, method, aliases)
    )
    rows: list[_InventoryRow] = []
    for owner, method in public_reads:
        matches = [
            (implementation, target)
            for candidate_method, implementation, target in adapter_methods
            if candidate_method == method
        ]
        if not matches:
            raise AssertionError(f"no Postgres Record adapter found for {owner}.{method}")
        for implementation, target in matches:
            source_path, function_name = target
            source = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            function = _function(source, function_name)
            predicate_line = _first_call_line(function, "project_scope_refusal")
            materialization_line = _first_materialization_execute_line(function)
            rows.append(
                _InventoryRow(
                    public_owner=owner,
                    public_method=method,
                    implementation=implementation,
                    source_path=source_path,
                    function_name=function_name,
                    predicate_line=predicate_line,
                    materialization_line=materialization_line,
                )
            )
    return tuple(rows)


def _public_reads(tree: ast.Module) -> list[tuple[str, str]]:
    reads: list[tuple[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not _is_protocol(node):
            continue
        for method in node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names = {
                argument.arg
                for argument in (
                    *method.args.posonlyargs,
                    *method.args.args,
                    *method.args.kwonlyargs,
                )
            }
            if method.name.startswith("_") or "actor" not in names:
                continue
            if not names & {"project_key", "project_keys", "ticket_id"}:
                continue
            if "command" in names:
                continue
            reads.append((node.name, method.name))
    return reads


def _is_protocol(node: ast.ClassDef) -> bool:
    return any(
        (isinstance(base, ast.Name) and base.id == "Protocol")
        or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
        for base in node.bases
    )


def _postgres_sql_aliases(tree: ast.Module) -> dict[str, tuple[Path, str]]:
    aliases: dict[str, tuple[Path, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if not node.module.startswith("ctower_kernel.record._"):
            continue
        module_path = _RECORD_ROOT / (node.module.rsplit(".", 1)[-1] + ".py")
        for imported in node.names:
            aliases[imported.asname or imported.name] = (module_path, imported.name)
    return aliases


def _adapter_targets(
    tree: ast.Module,
    method_name: str,
    aliases: dict[str, tuple[Path, str]],
) -> list[tuple[str, tuple[Path, str]]]:
    targets: list[tuple[str, tuple[Path, str]]] = []
    for owner in ast.walk(tree):
        if not isinstance(owner, ast.ClassDef):
            continue
        method = next(
            (
                child
                for child in owner.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == method_name
            ),
            None,
        )
        if method is None:
            continue
        for call in ast.walk(method):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                continue
            target = aliases.get(call.func.id)
            if target is not None:
                targets.append((owner.name, target))
    return targets


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one {name} definition, found {len(matches)}")
    return matches[0]


def _first_call_line(function: ast.AST, name: str) -> int | None:
    lines = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    ]
    return min(lines) if lines else None


def _first_materialization_execute_line(function: ast.AST) -> int | None:
    lines: list[int] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "execute" or not node.args:
            continue
        sql = _string_constants(node.args[0]).upper()
        if "SET ROLE" not in sql:
            lines.append(node.lineno)
    return min(lines) if lines else None


def _string_constants(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_string_constants(value) for value in node.values)
    return ""
