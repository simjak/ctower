"""Every public Project-scoped Record read must guard before SQL materialization."""

from __future__ import annotations

import ast
import shutil
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[2]
_RECORD_ROOT = ROOT / "packages/ctower-kernel/src/ctower_kernel/record"
_INTERFACE = _RECORD_ROOT / "interface.py"
_POSTGRES = _RECORD_ROOT / "postgres.py"
_PROJECTION_ROOT = ROOT / "packages/ctower-kernel/src/ctower_kernel/projections"


@dataclass(frozen=True, slots=True)
class _InventoryRow:
    public_owner: str
    public_method: str
    implementation: str
    source_path: Path
    function_name: str
    predicate_line: int | None
    materialization_line: int | None
    identity_flow: bool = True
    refusal_dominates: bool = True

    @property
    def composes_predicate(self) -> bool:
        return (
            self.predicate_line is not None
            and self.materialization_line is not None
            and self.predicate_line < self.materialization_line
            and self.identity_flow
            and self.refusal_dominates
        )

    def output(self) -> str:
        status = "yes" if self.composes_predicate else "no"
        try:
            source_path = self.source_path.relative_to(ROOT)
        except ValueError:
            source_path = self.source_path
        return (
            f"{self.public_owner}.{self.public_method} -> "
            f"{source_path}:{self.function_name} "
            f"composes-predicate {status}"
        )


class RecordProjectReadInventoryTests(unittest.TestCase):
    def test_projection_maintenance_returns_metadata_not_board_data(self) -> None:
        interface = ast.parse(_PROJECTION_ROOT.joinpath("interface.py").read_text(encoding="utf-8"))
        public = next(
            node
            for node in interface.body
            if isinstance(node, ast.ClassDef) and node.name == "Projections"
        )
        returns = {
            node.name: ast.unparse(node.returns)
            for node in public.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"catch_up", "rebuild"}
            and node.returns is not None
        }
        self.assertEqual({"catch_up", "rebuild"}, set(returns))
        self.assertEqual(
            {"ProjectionMaintenanceResult"},
            {return_type.replace(" | None", "") for return_type in returns.values()},
        )

    def test_every_project_scoped_record_read_composes_grant_before_materialization(self) -> None:
        inventory = _discover_inventory()
        self.assertTrue(inventory, "the Project-read inventory discovered no reads")
        for row in inventory:
            print(row.output())

        failures = [row.output() for row in inventory if not row.composes_predicate]
        self.assertEqual(
            [], failures, "unguarded Project-scoped Record reads: " + "; ".join(failures)
        )

    def test_projection_read_inventory_rejects_a_planted_unguarded_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection_root = Path(temporary) / "projections"
            shutil.copytree(_PROJECTION_ROOT, projection_root)
            board_sql = projection_root / "_board_sql.py"
            original = board_sql.read_text(encoding="utf-8")
            planted_call = "        refusal = project_scope_refusal(\n"
            self.assertIn(planted_call, original)
            board_sql.write_text(
                original.replace(planted_call, "        refusal = _planted_scope_refusal(\n", 1),
                encoding="utf-8",
            )

            planted = _discover_projection_inventory(projection_root)
            failures = [row.output() for row in planted if not row.composes_predicate]
            print("planted projection read guard failures:", failures)
            self.assertTrue(failures, "the planted projection read unexpectedly passed the guard")

            board_sql.write_text(original, encoding="utf-8")
            restored = _discover_projection_inventory(projection_root)
            print(
                "restored projection read guard failures:",
                [row.output() for row in restored if not row.composes_predicate],
            )
            self.assertTrue(restored)
            self.assertTrue(all(row.composes_predicate for row in restored))

    def test_projection_read_inventory_rejects_identity_discard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection_root = Path(temporary) / "projections"
            shutil.copytree(_PROJECTION_ROOT, projection_root)
            board_sql = projection_root / "_board_sql.py"
            original = board_sql.read_text(encoding="utf-8")
            mutated = original.replace("actor=actor", "actor=None", 1)
            self.assertNotEqual(original, mutated)
            board_sql.write_text(mutated, encoding="utf-8")

            inventory = _discover_projection_inventory(projection_root)
            failures = [row.output() for row in inventory if not row.composes_predicate]
            print("identity-discard projection guard failures:", failures)
            self.assertTrue(
                failures,
                "the identity-discard projection read unexpectedly passed the guard",
            )


def _discover_inventory() -> tuple[_InventoryRow, ...]:
    return (*_discover_record_inventory(), *_discover_projection_inventory())


def _discover_record_inventory() -> tuple[_InventoryRow, ...]:
    interface = ast.parse(_INTERFACE.read_text(encoding="utf-8"), filename=str(_INTERFACE))
    public_reads = tuple(
        _public_reads(interface, scope_names={"project_key", "project_keys", "ticket_id"})
    )
    postgres = ast.parse(_POSTGRES.read_text(encoding="utf-8"), filename=str(_POSTGRES))
    aliases = _postgres_sql_aliases(
        postgres,
        module_prefix="ctower_kernel.record._",
        module_root=_RECORD_ROOT,
    )
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


def _discover_projection_inventory(
    projection_root: Path = _PROJECTION_ROOT,
) -> tuple[_InventoryRow, ...]:
    interface_path = projection_root / "interface.py"
    postgres_path = projection_root / "postgres.py"
    interface = ast.parse(interface_path.read_text(encoding="utf-8"), filename=str(interface_path))
    public_reads = tuple(
        _public_reads(interface, scope_names={"project_key", "project_keys", "ticket_id", "query"})
    )
    postgres = ast.parse(postgres_path.read_text(encoding="utf-8"), filename=str(postgres_path))
    aliases = _postgres_sql_aliases(
        postgres,
        module_prefix="ctower_kernel.projections._",
        module_root=projection_root,
    )
    rows: list[_InventoryRow] = []
    for owner, method in public_reads:
        matches = [
            target for _implementation, target in _adapter_targets(postgres, method, aliases)
        ]
        if not matches:
            raise AssertionError(f"no Postgres projection adapter found for {owner}.{method}")
        for target in matches:
            source_path, function_name = _resolve_projection_target(target, method, projection_root)
            source = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            function = _function(source, function_name)
            predicate_line = _first_call_line(function, "project_scope_refusal")
            materialization_line = _projection_materialization_line(source, function)
            rows.append(
                _InventoryRow(
                    public_owner=owner,
                    public_method=method,
                    implementation="PostgresProjections",
                    source_path=source_path,
                    function_name=function_name,
                    predicate_line=predicate_line,
                    materialization_line=materialization_line,
                    identity_flow=_projection_identity_flow(
                        postgres, method, target, projection_root
                    ),
                    refusal_dominates=_scope_guard_dominates_materialization(
                        function, materialization_line
                    ),
                )
            )
    return tuple(rows)


def _public_reads(tree: ast.Module, *, scope_names: set[str]) -> list[tuple[str, str]]:
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


def _postgres_sql_aliases(
    tree: ast.Module,
    *,
    module_prefix: str,
    module_root: Path,
) -> dict[str, tuple[Path, str]]:
    aliases: dict[str, tuple[Path, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if not node.module.startswith(module_prefix):
            continue
        module_path = module_root / (node.module.rsplit(".", 1)[-1] + ".py")
        for imported in node.names:
            aliases[imported.asname or imported.name] = (module_path, imported.name)
    return aliases


def _resolve_projection_target(
    target: tuple[Path, str], method_name: str, projection_root: Path
) -> tuple[Path, str]:
    source_path, function_name = target
    if source_path != projection_root / "_postgres_sql.py":
        return target
    source = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    aliases = _postgres_sql_aliases(
        source,
        module_prefix="ctower_kernel.projections._",
        module_root=projection_root,
    )
    function = _function(source, function_name)
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
    function = _function(source, function_name)
    if _calls(function, "_read_view"):
        return source_path, "_read_view"
    return target


def _projection_identity_flow(
    postgres: ast.Module,
    method_name: str,
    target: tuple[Path, str],
    projection_root: Path,
) -> bool:
    if method_name != "board":
        source = ast.parse(target[0].read_text(encoding="utf-8"), filename=str(target[0]))
        return _actor_arguments_reach_predicate(_function(source, target[1]))

    board = _function(postgres, "board")
    aliases = _postgres_sql_aliases(
        postgres,
        module_prefix="ctower_kernel.projections._",
        module_root=projection_root,
    )
    read_view_call = next(
        (
            call
            for call in ast.walk(board)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and aliases.get(call.func.id) == target
        ),
        None,
    )
    if read_view_call is None or not _positional_argument_is_name(read_view_call, 1, "actor"):
        return False

    board_sql = ast.parse(
        (projection_root / "_board_sql.py").read_text(encoding="utf-8"),
        filename=str(projection_root / "_board_sql.py"),
    )
    read_view = _function(board_sql, "read_view")
    inner_call = next(
        (
            call
            for call in ast.walk(read_view)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_read_view"
        ),
        None,
    )
    if inner_call is None or not _keyword_argument_is_name(inner_call, "actor", "actor"):
        return False
    return _actor_arguments_reach_predicate(_function(board_sql, "_read_view"))


def _actor_arguments_reach_predicate(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
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


def _projection_materialization_line(
    source: ast.Module, function: ast.FunctionDef | ast.AsyncFunctionDef
) -> int | None:
    direct = _first_materialization_execute_line(function)
    if direct is not None:
        return direct
    for call in ast.walk(function):
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_read_view_data"
        ):
            return _first_materialization_execute_line(_function(source, "_read_view_data"))
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


def _scope_guard_dominates_materialization(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    materialization_line: int | None = None,
) -> bool:
    predicate_line = _first_call_line(function, "project_scope_refusal")
    materialization_line = (
        materialization_line
        if materialization_line is not None
        else _first_materialization_execute_line(function)
    )
    if (
        predicate_line is None
        or materialization_line is None
        or predicate_line >= materialization_line
    ):
        return False
    predicate_assignments = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "project_scope_refusal"
            for call in ast.walk(node.value)
        )
    ]
    if len(predicate_assignments) != 1:
        return False
    targets = {
        target.id for target in predicate_assignments[0].targets if isinstance(target, ast.Name)
    }
    if not targets:
        return False
    for node in ast.walk(function):
        if not isinstance(node, ast.If) or node.lineno <= predicate_line:
            continue
        if node.end_lineno is None or node.end_lineno >= materialization_line:
            continue
        if not any(_is_not_none_test(node.test, target) for target in targets):
            continue
        if any(
            isinstance(child, ast.Return)
            for statement in node.body
            for child in ast.walk(statement)
        ):
            return True
    return False


def _is_not_none_test(node: ast.AST, name: str) -> bool:
    return (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.IsNot)
        and len(node.comparators) == 1
        and isinstance(node.left, ast.Name)
        and node.left.id == name
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is None
    )


def _calls(function: ast.AST, name: str) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        for node in ast.walk(function)
    )


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
