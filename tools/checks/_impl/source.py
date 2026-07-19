"""Build one language-aware source model for policy evaluation."""

from __future__ import annotations

import ast
import fnmatch
import io
import tokenize
from pathlib import Path

from tools.checks._impl.model import (
    ClassMetric,
    FunctionMetric,
    ImportRef,
    PolicyConfig,
    SourceMetric,
)

_BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match, ast.IfExp)
_NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)


def discover_sources(root: Path, policy: PolicyConfig) -> tuple[Path, ...]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in policy.source_extensions:
            continue
        relative = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(relative, pattern) for pattern in policy.excludes):
            continue
        paths.append(path)
    return tuple(sorted(paths))


def analyze_source(root: Path, path: Path) -> SourceMetric:
    relative = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return _analyze_python(path, relative, text)
    return SourceMetric(
        absolute_path=path,
        path=relative,
        logical_lines=_logical_script_lines(text),
        functions=(),
        classes=(),
        public_exports=(),
        imports=(),
    )


def _logical_python_lines(text: str) -> int:
    ignored = {
        tokenize.COMMENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }
    lines = {
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(text).readline)
        if token.type not in ignored and token.string.strip()
    }
    return len(lines)


def _logical_script_lines(text: str) -> int:
    lines = 0
    in_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if in_block:
            if "*/" in line:
                in_block = False
                line = line.split("*/", maxsplit=1)[1].strip()
            else:
                continue
        if line.startswith("/*"):
            if "*/" not in line[2:]:
                in_block = True
                continue
            line = line.split("*/", maxsplit=1)[1].strip()
        if line and not line.startswith("//"):
            lines += 1
    return lines


def _node_lines(node: ast.AST) -> int:
    return len({child.lineno for child in ast.walk(node) if hasattr(child, "lineno")})


def _complexity(node: ast.AST) -> int:
    branches = sum(1 for child in ast.walk(node) if isinstance(child, _BRANCH_NODES))
    boolean_branches = sum(
        max(0, len(child.values) - 1) for child in ast.walk(node) if isinstance(child, ast.BoolOp)
    )
    handlers = sum(len(child.handlers) for child in ast.walk(node) if isinstance(child, ast.Try))
    return 1 + branches + boolean_branches + handlers


def _max_nesting(node: ast.AST) -> int:
    def visit(current: ast.AST, depth: int) -> int:
        next_depth = depth + 1 if isinstance(current, _NESTING_NODES) else depth
        child_depths = [visit(child, next_depth) for child in ast.iter_child_nodes(current)]
        return max([next_depth, *child_depths])

    return max(0, visit(node, 0) - 1)


def _function_metrics(tree: ast.Module) -> tuple[FunctionMetric, ...]:
    metrics = [
        FunctionMetric(
            name=node.name,
            line=node.lineno,
            logical_lines=_node_lines(node),
            complexity=_complexity(node),
            nesting=_max_nesting(node),
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    return tuple(sorted(metrics, key=lambda item: (item.line, item.name)))


def _class_metrics(tree: ast.Module) -> tuple[ClassMetric, ...]:
    return tuple(
        ClassMetric(
            name=node.name,
            line=node.lineno,
            public_methods=sum(
                1
                for child in node.body
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                and not child.name.startswith("_")
            ),
        )
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    )


def _public_exports(tree: ast.Module) -> tuple[str, ...]:
    if any(
        isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
        for node in tree.body
    ):
        raise ValueError("star re-exports make the public surface unresolvable")
    declared = _declared_all(tree)
    if declared is not None:
        return tuple(sorted(declared))
    exports: set[str] = set()
    for node in tree.body:
        export = _definition_export(node)
        if export is not None:
            exports.add(export)
        exports.update(_assignment_exports(node))
        exports.update(_import_exports(node))
    return tuple(sorted(exports))


def _declared_all(tree: ast.Module) -> set[str] | None:
    declaration: ast.expr | None = None
    for node in tree.body:
        if isinstance(node, ast.AugAssign) and _is_all_target(node.target):
            raise ValueError("augmented __all__ is not statically resolvable")
        value = _declared_all_value(node)
        if value is None:
            continue
        if declaration is not None:
            raise ValueError("multiple __all__ declarations are not statically resolvable")
        declaration = value
    if declaration is None:
        return None
    if not isinstance(declaration, ast.List | ast.Tuple | ast.Set):
        raise TypeError("dynamic __all__ is not statically resolvable")
    values = {
        item.value
        for item in declaration.elts
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }
    if len(values) != len(declaration.elts):
        raise ValueError("__all__ must contain only unique string literals")
    return values


def _declared_all_value(node: ast.stmt) -> ast.expr | None:
    if isinstance(node, ast.Assign) and any(_is_all_target(target) for target in node.targets):
        return node.value
    if isinstance(node, ast.AnnAssign) and _is_all_target(node.target):
        if node.value is None:
            raise ValueError("annotated __all__ requires a literal value")
        return node.value
    return None


def _is_all_target(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "__all__"


def _import_exports(node: ast.stmt) -> set[str]:
    if isinstance(node, ast.Import):
        names = (alias.asname or alias.name.split(".", maxsplit=1)[0] for alias in node.names)
    elif isinstance(node, ast.ImportFrom):
        names = (alias.asname or alias.name for alias in node.names if alias.name != "*")
    else:
        return set()
    return {name for name in names if not name.startswith("_")}


def _definition_export(node: ast.stmt) -> str | None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return node.name if not node.name.startswith("_") else None
    return None


def _assignment_exports(node: ast.stmt) -> set[str]:
    if not isinstance(node, ast.Assign | ast.AnnAssign):
        return set()
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {
        target.id
        for target in targets
        if isinstance(target, ast.Name) and not target.id.startswith("_")
    }


def _imports(tree: ast.Module) -> tuple[ImportRef, ...]:
    imports: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(ImportRef(alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            imports.append(ImportRef(node.module, node.lineno))
    return tuple(imports)


def _analyze_python(path: Path, relative: str, text: str) -> SourceMetric:
    try:
        tree = ast.parse(text, filename=relative)
        return SourceMetric(
            absolute_path=path,
            path=relative,
            logical_lines=_logical_python_lines(text),
            functions=_function_metrics(tree),
            classes=_class_metrics(tree),
            public_exports=_public_exports(tree),
            imports=_imports(tree),
        )
    except (SyntaxError, TypeError, ValueError, tokenize.TokenError) as error:
        return SourceMetric(
            absolute_path=path,
            path=relative,
            logical_lines=len(text.splitlines()),
            functions=(),
            classes=(),
            public_exports=(),
            imports=(),
            parse_error=str(error),
        )
