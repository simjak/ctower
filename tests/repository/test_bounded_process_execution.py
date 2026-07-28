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
_EXPECTED_ADAPTER_CALLS = 12


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
    source = tmp_path / "tools/new_operation.py"
    source.parent.mkdir()
    source.write_text(
        "import subprocess\nsubprocess.run(['/usr/bin/false'], check=False)\n",
        encoding="utf-8",
    )

    assert _process_sites(tmp_path) == (
        _ProcessSite(
            path=Path("tools/new_operation.py"),
            line=2,
            operation="subprocess.run",
            bounded=False,
        ),
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
    sites: list[_ProcessSite] = []
    for source_root in _PRODUCTION_ROOTS:
        for path in sorted((root / source_root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(root)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            sites.extend(_sites_in_tree(relative, tree))
    return tuple(sites)


def _sites_in_tree(path: Path, tree: ast.AST) -> tuple[_ProcessSite, ...]:
    sites: list[_ProcessSite] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        site = _process_site(path, node)
        if site is not None:
            sites.append(site)
    return tuple(sites)


def _process_site(path: Path, node: ast.Call) -> _ProcessSite | None:
    if not isinstance(node.func, ast.Attribute):
        return None
    owner = node.func.value
    if (
        isinstance(owner, ast.Name)
        and owner.id == "subprocess"
        and node.func.attr in {"Popen", "run"}
    ):
        return _ProcessSite(
            path,
            node.lineno,
            f"subprocess.{node.func.attr}",
            path == _ADAPTER,
        )
    if isinstance(owner, ast.Name) and owner.id == "process_execution" and node.func.attr == "run":
        has_timeout = any(keyword.arg == "timeout_seconds" for keyword in node.keywords)
        return _ProcessSite(path, node.lineno, "run", has_timeout)
    return None
