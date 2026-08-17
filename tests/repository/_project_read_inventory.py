"""Projection-side analyzer for the Project-scoped Record read inventory.

This module holds the AST discovery helpers that belong to projection reads:
resolving the public Protocol read surface, following the Postgres adapter to
its SQL implementation, and proving Actor identity reaches the scope
predicate before any materialization. The Record-side discovery and the
unittest inventory live in ``test_record_project_read_inventory.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

__all__: tuple[str, ...] = ()

AdapterAliases = dict[str, tuple[Path, str]]


def public_reads(tree: ast.Module, *, scope_names: set[str]) -> list[tuple[str, str]]:
    """Every public Protocol method that reads Projects through an Actor."""

    reads: list[tuple[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not _is_protocol(node):
            continue
        for method in node.body:
            if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
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
            if not names & scope_names:
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


def postgres_sql_aliases(
    tree: ast.Module,
    *,
    module_prefix: str,
    module_root: Path,
) -> AdapterAliases:
    aliases: AdapterAliases = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if not node.module.startswith(module_prefix):
            continue
        module_path = module_root / (node.module.rsplit(".", maxsplit=1)[-1] + ".py")
        for imported in node.names:
            aliases[imported.asname or imported.name] = (module_path, imported.name)
    return aliases


def adapter_targets(
    tree: ast.Module,
    method_name: str,
    aliases: AdapterAliases,
) -> list[tuple[str, tuple[Path, str]]]:
    targets: list[tuple[str, tuple[Path, str]]] = []
    for owner in ast.walk(tree):
        if not isinstance(owner, ast.ClassDef):
            continue
        method = next(
            (
                child
                for child in owner.body
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
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


def resolve_projection_target(
    target: tuple[Path, str], method_name: str, projection_root: Path
) -> tuple[Path, str]:
    source_path, function_name = target
    if source_path != projection_root / "_postgres_sql.py":
        return target
    source = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    aliases = postgres_sql_aliases(
        source,
        module_prefix="ctower_kernel.projections._",
        module_root=projection_root,
    )
    function = single_function(source, function_name)
    desired = "read_view" if method_name == "board" else method_name
    for call in ast.walk(function):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        child = aliases.get(call.func.id)
        if child is None or child[1] != desired:
            continue
        if method_name == "board":
            return _resolve_board_target(child)
        return child
    return target


def _resolve_board_target(target: tuple[Path, str]) -> tuple[Path, str]:
    source_path, function_name = target
    if function_name != "read_view":
        return target
    source = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = single_function(source, function_name)
    if calls(function, "_read_view"):
        return source_path, "_read_view"
    return target


def projection_identity_flow(
    postgres: ast.Module,
    method_name: str,
    target: tuple[Path, str],
    projection_root: Path,
) -> bool:
    """Prove the Actor argument reaches the projection's scope predicate."""

    if method_name != "board":
        source = ast.parse(target[0].read_text(encoding="utf-8"), filename=str(target[0]))
        return actor_arguments_reach_predicate(single_function(source, target[1]))

    aliases = postgres_sql_aliases(
        postgres,
        module_prefix="ctower_kernel.projections._",
        module_root=projection_root,
    )
    read_view_call = _board_read_view_call(postgres, target, aliases)
    if read_view_call is None or not _positional_argument_is_name(read_view_call, 1, "actor"):
        return False

    board_sql = ast.parse(
        (projection_root / "_board_sql.py").read_text(encoding="utf-8"),
        filename=str(projection_root / "_board_sql.py"),
    )
    inner_call = _inner_read_view_call(board_sql)
    if inner_call is None or not _keyword_argument_is_name(inner_call, "actor", "actor"):
        return False
    return actor_arguments_reach_predicate(single_function(board_sql, "_read_view"))


def _board_read_view_call(
    postgres: ast.Module, target: tuple[Path, str], aliases: AdapterAliases
) -> ast.Call | None:
    board = single_function(postgres, "board")
    return next(
        (
            call
            for call in ast.walk(board)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and aliases.get(call.func.id) == target
        ),
        None,
    )


def _inner_read_view_call(board_sql: ast.Module) -> ast.Call | None:
    read_view = single_function(board_sql, "read_view")
    return next(
        (
            call
            for call in ast.walk(read_view)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_read_view"
        ),
        None,
    )


def actor_arguments_reach_predicate(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    actor = next(
        (
            argument
            for argument in (
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
            )
            if argument.arg == "actor"
        ),
        None,
    )
    if actor is None or actor.annotation is None or ast.unparse(actor.annotation) != "Actor":
        return False
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "project_scope_refusal"
    ]
    if len(calls) != 1:
        return False
    arguments = {keyword.arg: keyword.value for keyword in calls[0].keywords if keyword.arg}
    return all(
        _is_actor_attribute(arguments.get(name), attribute)
        for name, attribute in (("tenant_id", "tenant_id"), ("principal_id", "principal_id"))
    )


def projection_materialization_line(
    source: ast.Module, function: ast.FunctionDef | ast.AsyncFunctionDef
) -> int | None:
    direct = first_materialization_execute_line(function)
    if direct is not None:
        return direct
    for call in ast.walk(function):
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_read_view_data"
        ):
            return first_materialization_execute_line(single_function(source, "_read_view_data"))
    return None


def _is_actor_attribute(node: ast.AST | None, attribute: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attribute
        and isinstance(node.value, ast.Name)
        and node.value.id == "actor"
    )


def _positional_argument_is_name(call: ast.Call, position: int, name: str) -> bool:
    if position >= len(call.args):
        return False
    argument = call.args[position]
    return isinstance(argument, ast.Name) and argument.id == name


def _keyword_argument_is_name(call: ast.Call, keyword: str, name: str) -> bool:
    return any(
        item.arg == keyword and isinstance(item.value, ast.Name) and item.value.id == name
        for item in call.keywords
    )


def single_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one {name} definition, found {len(matches)}")
    return matches[0]


def calls(function: ast.AST, name: str) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        for node in ast.walk(function)
    )


def first_call_line(function: ast.AST, name: str) -> int | None:
    lines = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    ]
    return min(lines) if lines else None


def first_materialization_execute_line(function: ast.AST) -> int | None:
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
