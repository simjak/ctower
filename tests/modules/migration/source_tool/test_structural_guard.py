"""Structural guard: no fixture-corpus cardinality literals in product code.

This guard walks the authored migration product trees (the source tool and
the kernel's server-side reconciliation) and asserts that the four
fixture-corpus cardinality values (86, 243, 27, 14) do not appear as
module-level assignment literals in any product .py file. They are permitted
in contracts/domain/migration/ (the JSON schemas), the frozen vectors
(migration-vectors.json), and generated/python/ctower_client/models.py — the
generated boundary model whose ``Field(min_length=14, max_length=14)`` pins on
``checkpoint_definitions``/``project_delivery_rows`` are the structural
enforcement of the signed checkpoint set at finalization
(``_reconciliation_sql.py``'s ``model_validate_json`` call), not a restatement
a reviewer should flag. That file is included below so the guard's coverage
matches this docstring's claim rather than the two authored trees leaving it
unscanned by omission.

This is a structural guard, not a grep: it uses AST parsing to discover
module-level constant assignments by value, regardless of the name the
author chooses.  A renamed literal (e.g. ``_EXPECTED_CHECKPOINTS = 14``)
gating the delivery check will fail this guard, unlike a four-string grep
of one file.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import NamedTuple

__all__: tuple[str, ...] = ()

# The four fixture-corpus cardinality values that must not appear as
# module-level assignment literals in migration product code.
_FORBIDDEN_CARDINALITIES = {86, 243, 27, 14}

# The product trees to scan, plus the one generated file that legitimately
# pins the same cardinality (see module docstring). Both the source tool and
# server reconciliation consume the same signed corpus and neither may
# restate its cardinality as a bare module-level literal.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_PRODUCT_ROOTS = (
    _REPOSITORY_ROOT / "tools" / "migration",
    _REPOSITORY_ROOT / "packages" / "ctower-kernel" / "src" / "ctower_kernel" / "migration",
    _REPOSITORY_ROOT / "generated" / "python" / "ctower_client" / "models.py",
)

# Number of forbidden-cardinality hits the renamed-literal test expects.
_EXPECTED_HIT_COUNT = 2


class _ForbiddenHit(NamedTuple):
    file: Path
    line: int
    target: str
    value: int


def _check_assign(
    node: ast.Assign | ast.AnnAssign,
    py_file: Path,
) -> list[_ForbiddenHit]:
    """Check a single module-level assignment node for forbidden cardinality values."""
    value = _eval_literal(node.value)  # type: ignore[arg-type]
    if not isinstance(value, int) or value not in _FORBIDDEN_CARDINALITIES:
        return []
    hits: list[_ForbiddenHit] = []
    if isinstance(node, ast.Assign):
        for target in node.targets:
            name = _target_name(target)
            if name is not None:
                hits.append(_ForbiddenHit(py_file, node.lineno, name, value))
    else:  # ast.AnnAssign
        name = _target_name(node.target)
        if name is not None:
            hits.append(_ForbiddenHit(py_file, node.lineno, name, value))
    return hits


def _product_files(root: Path) -> list[Path]:
    """A root is either a directory to walk or a single file to scan directly."""
    return [root] if root.is_file() else sorted(root.rglob("*.py"))


def _scan_product_tree(root: Path) -> list[_ForbiddenHit]:
    """Walk all .py files under root, find module-level assignments of forbidden cardinalities."""
    hits: list[_ForbiddenHit] = []
    for py_file in _product_files(root):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign) or (
                isinstance(node, ast.AnnAssign) and node.value is not None
            ):
                hits.extend(_check_assign(node, py_file))
    return hits


def _eval_literal(node: ast.expr) -> object:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _target_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def test_no_fixture_cardinality_literals_in_product_code() -> None:
    """No module-level assignment of 86, 243, 27, or 14 in migration products.

    This is a structural AST-based guard, not a string grep. It discovers
    assignments by value regardless of the variable name, so a renamed
    literal like ``_EXPECTED_CHECKPOINTS = 14`` gating the delivery check
    will fail this guard. The four values are permitted in
    contracts/domain/migration/ schemas, migration-vectors.json, and
    generated/python/ctower_client/models.py (see module docstring).
    """
    scanned = [candidate for root in _PRODUCT_ROOTS for candidate in _product_files(root)]
    assert all(_product_files(root) for root in _PRODUCT_ROOTS), (
        "guard scanned zero Python files under a configured product root "
        "(root missing or path broke) — a guard that scans nothing cannot fail"
    )
    hits = [hit for root in _PRODUCT_ROOTS for hit in _scan_product_tree(root)]
    assert not hits, "fixture cardinality literals found in product code:\n" + "\n".join(
        f"  {hit.file}:{hit.line}  {hit.target} = {hit.value}" for hit in hits
    )
    assert any(path.name == "_pass_two_sql.py" for path in scanned)
    assert any(path.name == "models.py" for path in scanned), (
        "guard's docstring claims generated/python/ctower_client/models.py as a permitted "
        "home for these cardinalities — it must actually be scanned, not just named"
    )


def test_guard_detects_renamed_literal_gating_delivery(tmp_path: Path) -> None:
    """Negative: a renamed cardinality literal (reviewer's E1) must fail the guard.

    The reviewer's E1 experiment added ``_EXPECTED_CHECKPOINTS = 14`` to
    reconcile.py and replaced the derived count with it. This test simulates
    that by writing a temp module with the renamed literal and verifying
    the scanner catches it — proving the guard is structural, not a grep.
    """
    # Create a fake product module with a renamed literal.
    fake_module = tmp_path / "fake_product.py"
    fake_module.write_text(
        "_EXPECTED_CHECKPOINTS = 14\n_REQUEST_COUNT = 86\nx = 1  # not a cardinality\n",
        encoding="utf-8",
    )
    hits = _scan_product_tree(tmp_path)
    assert len(hits) == _EXPECTED_HIT_COUNT
    assert {hit.value for hit in hits} == {14, 86}
    assert {hit.target for hit in hits} == {"_EXPECTED_CHECKPOINTS", "_REQUEST_COUNT"}
