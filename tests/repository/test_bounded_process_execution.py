"""Production process execution stays behind one deadline-enforcing chokepoint."""

from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

import tools.process_execution as process_execution  # noqa: PLR0402

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[2]
_PRODUCTION_ROOTS = ("apps", "packages", "tools")
_ADAPTER = Path("tools/process_execution.py")
_EXPECTED_DIRECT_SITE = (_ADAPTER, "subprocess.Popen")
_BOUNDED_ENTRY_POINTS = ("pipeline", "run")
_BOUNDED_REFERENCES = frozenset(f"tools.process_execution.{name}" for name in _BOUNDED_ENTRY_POINTS)
# Async subprocess creation (asyncio.create_subprocess_exec/_shell) never takes a timeout
# argument itself; the deadline is only real if the site's enclosing function also carries
# an asyncio.wait_for(..., timeout=...) or `async with asyncio.timeout(...)` whose deadline
# argument is not the literal `None` (both stdlib APIs treat a `None` deadline as unbounded).
_ASYNC_SUBPROCESS_REFERENCES = frozenset(
    {"asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell"}
)
_ASYNC_DEADLINE_REFERENCES = frozenset({"asyncio.wait_for", "asyncio.timeout"})
_TERMINAL_REFERENCES = (
    _BOUNDED_REFERENCES
    | _ASYNC_SUBPROCESS_REFERENCES
    | _ASYNC_DEADLINE_REFERENCES
    | {
        "asyncio",
        "subprocess",
        "subprocess.Popen",
        "subprocess.run",
        "tools.process_execution",
    }
)
_EXPECTED_ADAPTER_CALLS = {"pipeline": 2, "run": 15}
# Every authored async subprocess creation site production-wide, keyed by (path, operation).
# A new call site must be added here deliberately, alongside proof it is bounded — the
# assertion below fails loudly on an unreviewed addition instead of silently inventorying it.
_EXPECTED_ASYNC_SITES = frozenset(
    {
        (
            Path("apps/ctower-api/src/ctower_api/_backup_adapter.py"),
            "asyncio.create_subprocess_exec",
        ),
        (Path("tools/checks/_impl/suites.py"), "asyncio.create_subprocess_exec"),
        (Path("tools/checks/playwright.py"), "asyncio.create_subprocess_exec"),
    }
)
# Sites reviewed and accepted as temporarily unbounded, keyed by (path, operation). Empty in
# steady state: every authored async subprocess site must resolve to an approved bounded
# interface. Populate only with an exact, sourced reason tied to a tracked fix in flight; the
# `stale_exceptions` assertion in _assert_production_process_inventory fails loudly once the
# named site becomes bounded, forcing the entry's removal in the same change that fixes it.
#
# tools/checks/playwright.py: gh#114 (PR simjak/ctower#307, reviewed APPROVE, mergeable) already
# wraps this exact call in asyncio.wait_for(process.wait(), timeout=_TIMEOUT_SECONDS) plus
# owned-process tree termination — #307 is pinned-unmerged as of gh#113's own build (see
# coordination/2026-08-05_1430--engineer-r113-process-vocab--policy-tool.status.md), so this
# repository's `origin/main` still carries the pre-fix bare `await process.wait()`. Remove this
# entry in the same change that observes #307 has merged (the stale-exception assertion above
# will fail and name it).
_ASYNC_EXCEPTIONS: frozenset[tuple[Path, str]] = frozenset(
    {(Path("tools/checks/playwright.py"), "asyncio.create_subprocess_exec")}
)
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

    def test_inventory_rejects_a_new_unbounded_async_site(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            _assert_inventory_rejects_unbounded_async_site(Path(name))

    def test_process_deadline_is_required_and_terminates_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            _assert_deadline_terminates_descendants(Path(name))


def _assert_production_process_inventory() -> None:
    sites = _process_sites(ROOT)
    sync_sites = tuple(site for site in sites if site.operation not in _ASYNC_SUBPROCESS_REFERENCES)
    async_sites = tuple(site for site in sites if site.operation in _ASYNC_SUBPROCESS_REFERENCES)

    direct = {
        (site.path, site.operation)
        for site in sync_sites
        if site.operation not in _BOUNDED_ENTRY_POINTS
    }
    unbounded_sync = tuple(site for site in sync_sites if not site.bounded)
    calls = {
        name: len(tuple(site for site in sync_sites if site.operation == name))
        for name in _BOUNDED_ENTRY_POINTS
    }
    async_inventory = {(site.path, site.operation) for site in async_sites}
    unbounded_async = tuple(site for site in async_sites if not site.bounded)
    unreviewed_async = tuple(
        site for site in unbounded_async if (site.path, site.operation) not in _ASYNC_EXCEPTIONS
    )
    stale_exceptions = _ASYNC_EXCEPTIONS - {(site.path, site.operation) for site in unbounded_async}

    assert direct == {_EXPECTED_DIRECT_SITE}
    assert unbounded_sync == ()
    assert calls == _EXPECTED_ADAPTER_CALLS
    assert async_inventory == _EXPECTED_ASYNC_SITES
    assert unreviewed_async == ()
    assert stale_exceptions == set(), f"exception no longer applies, remove it: {stale_exceptions}"


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


_UNBOUNDED_ASYNC_FIXTURES = {
    "aliased_from.py": (
        "from asyncio import create_subprocess_exec as spawn\n"
        "async def run() -> None:\n"
        "    return await spawn('/usr/bin/false')\n"
    ),
    "aliased_module.py": (
        "import asyncio as aio\n"
        "async def run() -> None:\n"
        "    return await aio.create_subprocess_exec('/usr/bin/false')\n"
    ),
    "from_import.py": (
        "from asyncio import create_subprocess_exec\n"
        "async def run() -> None:\n"
        "    return await create_subprocess_exec('/usr/bin/false')\n"
    ),
    "literal_module.py": (
        "import asyncio\n"
        "async def run() -> None:\n"
        "    return await asyncio.create_subprocess_exec('/usr/bin/false')\n"
    ),
    "literal_shell.py": (
        "import asyncio\n"
        "async def run() -> None:\n"
        "    return await asyncio.create_subprocess_shell('/usr/bin/false')\n"
    ),
    "process_alias.py": "from asyncio import create_subprocess_exec as exported_spawn\n",
    "reexport.py": (
        "from tools.process_alias import exported_spawn\n"
        "async def run() -> None:\n"
        "    return await exported_spawn('/usr/bin/false')\n"
    ),
    "none_deadline.py": (
        "import asyncio\n"
        "async def run() -> None:\n"
        "    process = await asyncio.create_subprocess_exec('/usr/bin/false')\n"
        "    return await asyncio.wait_for(process.wait(), timeout=None)\n"
    ),
}
_BOUNDED_ASYNC_FIXTURES = {
    "bounded_wait_for.py": (
        "import asyncio\n"
        "async def run(deadline: float) -> int:\n"
        "    process = await asyncio.create_subprocess_exec('/usr/bin/false')\n"
        "    return await asyncio.wait_for(process.wait(), timeout=deadline)\n"
    ),
    "bounded_timeout_context.py": (
        "import asyncio\n"
        "async def run(deadline: float) -> None:\n"
        "    process = await asyncio.create_subprocess_exec('/usr/bin/false')\n"
        "    async with asyncio.timeout(deadline):\n"
        "        await process.wait()\n"
    ),
}


def _assert_inventory_rejects_unbounded_async_site(tmp_path: Path) -> None:
    source_root = tmp_path / "tools"
    source_root.mkdir()
    fixtures = {**_UNBOUNDED_ASYNC_FIXTURES, **_BOUNDED_ASYNC_FIXTURES}
    for name, source in fixtures.items():
        (source_root / name).write_text(source, encoding="utf-8")

    async_sites = {
        (site.path, site.line): site.bounded
        for site in _process_sites(tmp_path)
        if site.operation in _ASYNC_SUBPROCESS_REFERENCES
    }
    expected_unbounded = {
        (Path("tools") / name, 3)
        for name in _UNBOUNDED_ASYNC_FIXTURES
        if name != "process_alias.py"
    }
    expected_bounded = {(Path("tools") / name, 3) for name in _BOUNDED_ASYNC_FIXTURES}

    assert {key for key, bounded in async_sites.items() if not bounded} == expected_unbounded
    assert {key for key, bounded in async_sites.items() if bounded} == expected_bounded


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
    if reference in _TERMINAL_REFERENCES:
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


def _function_has_async_deadline(
    node: ast.AsyncFunctionDef,
    module: str,
    exports: dict[str, dict[str, _ResolvedReference]],
) -> bool:
    scope = [dict(exports[module])]
    for child in _iter_without_nested_functions(node):
        if not isinstance(child, ast.Call):
            continue
        reference = _resolve_reference(_expression_reference(child.func, scope), exports)
        if reference == "asyncio.wait_for" and _has_live_deadline(
            child, position=1, keyword="timeout"
        ):
            return True
        if reference == "asyncio.timeout" and _has_live_deadline(
            child, position=0, keyword="delay"
        ):
            return True
    return False


def _has_live_deadline(call: ast.Call, *, position: int, keyword: str) -> bool:
    value = next((entry.value for entry in call.keywords if entry.arg == keyword), None)
    if value is None and position < len(call.args):
        value = call.args[position]
    if value is None:
        return False
    return not (isinstance(value, ast.Constant) and value.value is None)


def _iter_without_nested_functions(node: ast.AST) -> Iterator[ast.AST]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield child
        yield from _iter_without_nested_functions(child)


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
        self._async_bounded: list[bool] = [False]
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
        self._visit_function(node, async_bounded=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        bounded = _function_has_async_deadline(node, self._module, self._exports)
        self._visit_function(node, async_bounded=bounded)

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
        elif reference in _BOUNDED_REFERENCES:
            has_timeout = any(keyword.arg == "timeout_seconds" for keyword in node.keywords)
            entry_point = reference.rpartition(".")[2]
            self._sites.append(_ProcessSite(self._path, node.lineno, entry_point, has_timeout))
        elif reference in _ASYNC_SUBPROCESS_REFERENCES:
            self._sites.append(
                _ProcessSite(self._path, node.lineno, reference, self._async_bounded[-1])
            )
        self.generic_visit(node)

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, *, async_bounded: bool
    ) -> None:
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
        self._async_bounded.append(async_bounded)
        for statement in node.body:
            self.visit(statement)
        self._async_bounded.pop()
        self._scopes.pop()
