"""Every public Project-scoped Record read must guard before SQL materialization."""

from __future__ import annotations

import ast
import shutil
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repository import _project_read_inventory as analyzer
else:
    from tests.repository import _project_read_inventory as analyzer

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
    scope_gate: bool = True

    @property
    def composes_predicate(self) -> bool:
        return (
            self.predicate_line is not None
            and self.materialization_line is not None
            and self.predicate_line < self.materialization_line
            and self.identity_flow
            and self.refusal_dominates
            and self.scope_gate
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

    def test_no_projection_query_type_can_omit_its_project_scope(self) -> None:
        interface = _PROJECTION_ROOT / "interface.py"
        scoped_query = "    project_key: str\n    lane: BoardLane | None = None\n"
        self.assertIn(scoped_query, interface.read_text(encoding="utf-8"))
        widened = interface.read_text(encoding="utf-8").replace(
            scoped_query, scoped_query.replace("project_key: str", "project_key: str | None"), 1
        )
        self.assertEqual(
            [],
            analyzer.optional_scope_fields(
                ast.parse(interface.read_text(encoding="utf-8")),
                scope_names={"project_key", "project_keys"},
            ),
        )
        rewidened = analyzer.optional_scope_fields(
            ast.parse(widened), scope_names={"project_key", "project_keys"}
        )
        print("re-widened projection scope fields:", rewidened)
        self.assertTrue(rewidened, "a re-widened Project scope was not reported")

    def test_projection_read_inventory_rejects_an_ungated_empty_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection_root = Path(temporary) / "projections"
            shutil.copytree(_PROJECTION_ROOT, projection_root)
            board_sql = projection_root / "_board_sql.py"
            original = board_sql.read_text(encoding="utf-8")
            mutated = original.replace("operator_only=True", "operator_only=False", 1)
            self.assertNotEqual(original, mutated)
            board_sql.write_text(mutated, encoding="utf-8")

            inventory = _discover_projection_inventory(projection_root)
            failures = [row.output() for row in inventory if not row.composes_predicate]
            print("ungated empty-scope guard failures:", failures)
            self.assertTrue(
                failures, "the ungated empty-scope projection read unexpectedly passed the guard"
            )

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
        analyzer.public_reads(
            interface,
            scope_names={"project_key", "project_keys", "ticket_id"},
            scoped_returns=set(),
            bases=analyzer.imported_protocols(
                interface,
                module_prefix="ctower_kernel.record.",
                module_root=_RECORD_ROOT,
            ),
        )
    )
    postgres = ast.parse(_POSTGRES.read_text(encoding="utf-8"), filename=str(_POSTGRES))
    aliases = analyzer.postgres_sql_aliases(
        postgres,
        module_prefix="ctower_kernel.record._",
        module_root=_RECORD_ROOT,
    )
    stores = _store_adapters(interface, postgres, aliases)
    adapter_methods = tuple(
        (method, implementation, target)
        for owner, method in public_reads
        for implementation, target in (
            *analyzer.adapter_targets(postgres, method, aliases),
            *_store_adapter_targets(stores.get(owner), method),
        )
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
        rows.extend(
            _record_read_row(owner, method, implementation, target)
            for implementation, target in matches
        )
    return tuple(rows)


def _record_read_row(
    owner: str,
    method: str,
    implementation: str,
    target: tuple[Path, str],
) -> _InventoryRow:
    source_path, function_name = target
    source = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = analyzer.single_function(source, function_name)
    return _InventoryRow(
        public_owner=owner,
        public_method=method,
        implementation=implementation,
        source_path=source_path,
        function_name=function_name,
        predicate_line=analyzer.first_call_line(function, "project_scope_refusal"),
        materialization_line=analyzer.first_materialization_execute_line(function),
        scope_gate=analyzer.empty_scope_refusals_are_operator_only(function),
    )


def _store_adapters(
    interface: ast.Module,
    postgres: ast.Module,
    aliases: analyzer.AdapterAliases,
) -> dict[str, tuple[Path, str]]:
    """Map each Record store Protocol to the module holding its Postgres adapter.

    A store adapter that stays inside ``postgres.py`` is already reachable by walking
    that module, so only the ones split into their own module are mapped here.
    """

    constructed = _constructed_stores(postgres)
    return {
        protocol: aliases[constructed[attribute]]
        for protocol, attribute in _store_properties(interface).items()
        if attribute in constructed and constructed[attribute] in aliases
    }


def _store_properties(interface: ast.Module) -> dict[str, str]:
    """Map each store Protocol named by a Record property to that property."""

    record = next(
        (
            node
            for node in interface.body
            if isinstance(node, ast.ClassDef) and node.name == "Record"
        ),
        None,
    )
    if record is None:
        return {}
    return {
        method.returns.id: method.name
        for method in record.body
        if isinstance(method, ast.FunctionDef)
        and isinstance(method.returns, ast.Name)
        and _is_property(method)
    }


def _is_property(method: ast.FunctionDef) -> bool:
    return any(
        isinstance(decorator, ast.Name) and decorator.id == "property"
        for decorator in method.decorator_list
    )


def _constructed_stores(postgres: ast.Module) -> dict[str, str]:
    """Map each PostgresRecord attribute to the adapter class its initializer builds."""

    record = next(
        (
            node
            for node in postgres.body
            if isinstance(node, ast.ClassDef) and node.name == "PostgresRecord"
        ),
        None,
    )
    if record is None:
        return {}
    stores: dict[str, str] = {}
    for assignment in ast.walk(record):
        constructed = _constructed_store(assignment)
        if constructed is not None:
            stores[constructed[0]] = constructed[1]
    return stores


def _constructed_store(assignment: ast.AST) -> tuple[str, str] | None:
    if not isinstance(assignment, ast.Assign) or not isinstance(assignment.value, ast.Call):
        return None
    if not isinstance(assignment.value.func, ast.Name) or len(assignment.targets) != 1:
        return None
    target = assignment.targets[0]
    if not isinstance(target, ast.Attribute) or not isinstance(target.value, ast.Name):
        return None
    if target.value.id != "self":
        return None
    return target.attr, assignment.value.func.id


def _store_adapter_targets(
    store: tuple[Path, str] | None, method_name: str
) -> list[tuple[str, tuple[Path, str]]]:
    """Follow a split-out store adapter to the SQL module that materializes its read."""

    if store is None:
        return []
    source_path, _implementation = store
    source = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    return analyzer.adapter_targets(
        source,
        method_name,
        analyzer.postgres_sql_aliases(
            source,
            module_prefix="ctower_kernel.record._",
            module_root=_RECORD_ROOT,
        ),
    )


def _discover_projection_inventory(
    projection_root: Path = _PROJECTION_ROOT,
) -> tuple[_InventoryRow, ...]:
    interface_path = projection_root / "interface.py"
    postgres_path = projection_root / "postgres.py"
    interface = ast.parse(interface_path.read_text(encoding="utf-8"), filename=str(interface_path))
    public_reads = tuple(
        analyzer.public_reads(
            interface,
            scope_names={"project_key", "project_keys", "ticket_id", "query"},
            scoped_returns=analyzer.project_bearing_returns(
                projection_root, scope_names={"project_key", "project_keys"}
            ),
        )
    )
    postgres = ast.parse(postgres_path.read_text(encoding="utf-8"), filename=str(postgres_path))
    aliases = analyzer.postgres_sql_aliases(
        postgres,
        module_prefix="ctower_kernel.projections._",
        module_root=projection_root,
    )
    rows: list[_InventoryRow] = []
    for owner, method in public_reads:
        matches = [
            target
            for _implementation, target in analyzer.adapter_targets(postgres, method, aliases)
        ]
        if not matches:
            raise AssertionError(f"no Postgres projection adapter found for {owner}.{method}")
        rows.extend(
            _projection_read_row(postgres, owner, method, target, projection_root)
            for target in matches
        )
    return tuple(rows)


def _projection_read_row(
    postgres: ast.Module,
    owner: str,
    method: str,
    target: tuple[Path, str],
    projection_root: Path,
) -> _InventoryRow:
    source_path, function_name = analyzer.resolve_projection_target(target, method, projection_root)
    source = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = analyzer.single_function(source, function_name)
    materialization_line = analyzer.projection_materialization_line(source, function)
    return _InventoryRow(
        public_owner=owner,
        public_method=method,
        implementation="PostgresProjections",
        source_path=source_path,
        function_name=function_name,
        predicate_line=analyzer.first_call_line(function, "project_scope_refusal"),
        materialization_line=materialization_line,
        identity_flow=analyzer.projection_identity_flow(postgres, method, target, projection_root),
        refusal_dominates=_scope_guard_dominates_materialization(function, materialization_line),
        scope_gate=analyzer.empty_scope_refusals_are_operator_only(function),
    )


def _scope_guard_dominates_materialization(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    materialization_line: int | None = None,
) -> bool:
    predicate_line = analyzer.first_call_line(function, "project_scope_refusal")
    materialization_line = (
        materialization_line
        if materialization_line is not None
        else analyzer.first_materialization_execute_line(function)
    )
    if not _predicate_precedes_materialization(predicate_line, materialization_line):
        return False
    predicate_assignments = _predicate_assignments(function)
    if len(predicate_assignments) != 1:
        return False
    targets = _assignment_targets(predicate_assignments[0])
    return bool(targets) and _has_early_scope_return(
        function, predicate_line, materialization_line, targets
    )


def _predicate_precedes_materialization(
    predicate_line: int | None,
    materialization_line: int | None,
) -> bool:
    return (
        predicate_line is not None
        and materialization_line is not None
        and predicate_line < materialization_line
    )


def _predicate_assignments(function: ast.AST) -> list[ast.Assign]:
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign) and analyzer.calls(node.value, "project_scope_refusal")
    ]


def _assignment_targets(assignment: ast.Assign) -> set[str]:
    return {target.id for target in assignment.targets if isinstance(target, ast.Name)}


def _has_early_scope_return(
    function: ast.AST,
    predicate_line: int | None,
    materialization_line: int | None,
    targets: set[str],
) -> bool:
    return any(
        _is_early_scope_return(node, predicate_line, materialization_line, targets)
        for node in ast.walk(function)
    )


def _is_early_scope_return(
    node: ast.AST,
    predicate_line: int | None,
    materialization_line: int | None,
    targets: set[str],
) -> bool:
    if not isinstance(node, ast.If):
        return False
    if predicate_line is None or node.lineno <= predicate_line:
        return False
    if materialization_line is None or node.end_lineno is None:
        return False
    if node.end_lineno >= materialization_line:
        return False
    if not any(_is_not_none_test(node.test, target) for target in targets):
        return False
    return any(
        isinstance(child, ast.Return) for statement in node.body for child in ast.walk(statement)
    )


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
