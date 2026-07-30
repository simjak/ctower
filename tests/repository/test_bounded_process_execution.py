"""Production process execution stays behind one deadline-enforcing chokepoint."""

from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

import pytest

import tools.process_execution as process_execution  # noqa: PLR0402

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[2]
_PRODUCTION_ROOTS = ("apps", "packages", "tools")
_ADAPTER = Path("tools/process_execution.py")
_EXPECTED_DIRECT_SITE = (_ADAPTER, "subprocess.Popen")
_EXPECTED_ADAPTER_CALLS = 14
type _ResolvedReference = str | None


@dataclass(frozen=True, slots=True)
class _ProcessSite:
    path: Path
    line: int
    operation: str
    bounded: bool


class BoundedProcessExecutionTests(unittest.TestCase):
    def test_production_process_inventory_has_one_bounded_chokepoint(self) -> None:
        _assert_production_process_inventory()

    def test_inventory_rejects_a_new_unbounded_process_site(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            _assert_inventory_rejects_unbounded_site(Path(name))

    def test_process_deadline_is_required_and_terminates_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            _assert_deadline_terminates_descendants(Path(name))


def _assert_production_process_inventory() -> None:
    sites = _process_sites(ROOT)

    direct = {(site.path, site.operation) for site in sites if site.operation != "run"}
    unbounded = tuple(site for site in sites if not site.bounded)

    assert direct == {_EXPECTED_DIRECT_SITE}
    assert unbounded == ()
    assert len(tuple(site for site in sites if site.operation == "run")) == _EXPECTED_ADAPTER_CALLS


def _assert_inventory_rejects_unbounded_site(tmp_path: Path) -> None:
    sources = {
        "aliased_from.py": (
            "from subprocess import run as invoke\ninvoke(['/usr/bin/false'], check=False)\n"
        ),
        "aliased_module.py": (
            "import subprocess as process\nprocess.run(['/usr/bin/false'], check=False)\n"
        ),
        "from_import.py": "from subprocess import run\nrun(['/usr/bin/false'], check=False)\n",
        "literal_module.py": (
            "import subprocess\nsubprocess.run(['/usr/bin/false'], check=False)\n"
        ),
        "process_alias.py": "from subprocess import run as exported_run\n",
        "reexport.py": (
            "from tools.process_alias import exported_run\n"
            "exported_run(['/usr/bin/false'], check=False)\n"
        ),
    }
    source_root = tmp_path / "tools"
    source_root.mkdir()
    for name, source in sources.items():
        (source_root / name).write_text(source, encoding="utf-8")

    assert _process_sites(tmp_path) == tuple(
        _ProcessSite(
            path=Path("tools") / name,
            line=2,
            operation="subprocess.run",
            bounded=False,
        )
        for name in (
            "aliased_from.py",
            "aliased_module.py",
            "from_import.py",
            "literal_module.py",
            "reexport.py",
        )
    )


def _assert_deadline_terminates_descendants(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="timeout_seconds"):
        process_execution.run([sys.executable, "-c", "pass"], check=True)  # type: ignore[call-arg]
    terminated = tmp_path / "terminated"
    child = (
        "import pathlib,signal,time;"
        f"path=pathlib.Path({str(terminated)!r});"
        "signal.signal(signal.SIGTERM,lambda *_: (path.write_text('terminated'),exit(0)));"
        "time.sleep(30)"
    )
    parent = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',{child!r}]);"
        "time.sleep(30)"
    )

    with pytest.raises(process_execution.ProcessTimeoutError):
        process_execution.run(
            [sys.executable, "-c", parent],
            timeout_seconds=2.0,
            check=True,
        )

    assert terminated.read_text(encoding="utf-8") == "terminated"


def _process_sites(root: Path) -> tuple[_ProcessSite, ...]:
    sources: dict[str, tuple[Path, ast.Module]] = {}
    packages: set[str] = set()
    paths: list[Path] = []
    for source_root in _PRODUCTION_ROOTS:
        paths.extend((root / source_root).rglob("*.py"))
    for path in sorted(paths):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root)
        module = _module_name(relative)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        sources[module] = (relative, tree)
        if path.name == "__init__.py":
            packages.add(module)
    exports = {
        module: _module_exports(module, tree, is_package=module in packages)
        for module, (_path, tree) in sources.items()
    }
    sites: list[_ProcessSite] = []
    for module, (path, tree) in sources.items():
        sites.extend(
            _SiteVisitor(
                path,
                module,
                exports,
                is_package=module in packages,
            ).collect(tree)
        )
    return tuple(sites)


def _module_name(path: Path) -> str:
    parts = path.with_suffix("").parts
    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _module_exports(
    module: str,
    tree: ast.Module,
    *,
    is_package: bool,
) -> dict[str, _ResolvedReference]:
    exports: dict[str, _ResolvedReference] = {}
    for statement in tree.body:
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            exports.update(_import_bindings(statement, module, is_package=is_package))
        elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
            _bind_assignment(statement, exports)
    return exports


def _import_bindings(
    node: ast.Import | ast.ImportFrom,
    module: str,
    *,
    is_package: bool,
) -> dict[str, str]:
    if isinstance(node, ast.Import):
        return {
            alias.asname or alias.name.split(".", maxsplit=1)[0]: (
                alias.name if alias.asname else alias.name.split(".", maxsplit=1)[0]
            )
            for alias in node.names
        }
    imported_module = _absolute_import(
        module,
        node.module,
        level=node.level,
        is_package=is_package,
    )
    return {
        alias.asname or alias.name: f"{imported_module}.{alias.name}"
        for alias in node.names
        if alias.name != "*"
    }


def _absolute_import(
    current: str,
    imported: str | None,
    *,
    level: int,
    is_package: bool,
) -> str:
    if level == 0:
        return imported or ""
    package = current if is_package else current.rpartition(".")[0]
    parts = package.split(".") if package else []
    if level > 1:
        parts = parts[: -(level - 1)]
    if imported:
        parts.extend(imported.split("."))
    return ".".join(parts)


def _bind_assignment(
    node: ast.Assign | ast.AnnAssign,
    bindings: dict[str, _ResolvedReference],
) -> None:
    value = node.value
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    reference = _expression_reference(value, [bindings])
    for target in targets:
        if isinstance(target, ast.Name):
            bindings[target.id] = reference


def _expression_reference(
    expression: ast.expr | None,
    scopes: list[dict[str, _ResolvedReference]],
) -> _ResolvedReference:
    if isinstance(expression, ast.Name):
        for scope in reversed(scopes):
            if expression.id in scope:
                return scope[expression.id]
        return None
    if isinstance(expression, ast.Attribute):
        owner = _expression_reference(expression.value, scopes)
        return f"{owner}.{expression.attr}" if owner else None
    return None


def _resolve_reference(
    reference: _ResolvedReference,
    exports: dict[str, dict[str, _ResolvedReference]],
    *,
    seen: frozenset[str] = frozenset(),
) -> _ResolvedReference:
    if reference is None or reference in seen:
        return reference
    if reference in {
        "subprocess",
        "subprocess.Popen",
        "subprocess.run",
        "tools.process_execution",
        "tools.process_execution.run",
    }:
        return reference
    for module in sorted(exports, key=len, reverse=True):
        prefix = f"{module}."
        if not reference.startswith(prefix):
            continue
        member, separator, remainder = reference[len(prefix) :].partition(".")
        target = exports[module].get(member)
        if target is None:
            return reference
        resolved = _resolve_reference(target, exports, seen=seen | {reference})
        if separator and resolved:
            resolved = f"{resolved}.{remainder}"
        return _resolve_reference(resolved, exports, seen=seen | {reference})
    return reference


class _SiteVisitor(ast.NodeVisitor):
    def __init__(
        self,
        path: Path,
        module: str,
        exports: dict[str, dict[str, _ResolvedReference]],
        *,
        is_package: bool,
    ) -> None:
        self._path = path
        self._module = module
        self._is_package = is_package
        self._exports = exports
        self._scopes: list[dict[str, _ResolvedReference]] = [dict(exports[module])]
        self._sites: list[_ProcessSite] = []

    def collect(self, tree: ast.Module) -> tuple[_ProcessSite, ...]:
        self.visit(tree)
        return tuple(self._sites)

    def visit_Import(self, node: ast.Import) -> None:
        self._scopes[-1].update(_import_bindings(node, self._module, is_package=self._is_package))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._scopes[-1].update(_import_bindings(node, self._module, is_package=self._is_package))

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        _bind_assignment(node, self._scopes[-1])

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        _bind_assignment(node, self._scopes[-1])

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        reference = _resolve_reference(
            _expression_reference(node.func, self._scopes),
            self._exports,
        )
        if reference in {"subprocess.Popen", "subprocess.run"}:
            self._sites.append(
                _ProcessSite(
                    self._path,
                    node.lineno,
                    reference,
                    self._path == _ADAPTER,
                )
            )
        elif reference == "tools.process_execution.run":
            has_timeout = any(keyword.arg == "timeout_seconds" for keyword in node.keywords)
            self._sites.append(_ProcessSite(self._path, node.lineno, "run", has_timeout))
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        arguments = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
        scope: dict[str, _ResolvedReference] = {argument.arg: None for argument in arguments}
        if node.args.vararg:
            scope[node.args.vararg.arg] = None
        if node.args.kwarg:
            scope[node.args.kwarg.arg] = None
        self._scopes.append(scope)
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()
