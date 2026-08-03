"""Execute a TypeScript driver against the browser surface's real modules.

Node runs TypeScript directly by stripping types, which is how
`test_reading_selectors.py` and `test_inspection_grammar.py` drive `selectors.ts`
and `commands.ts` with no bundler, no network and no clock. Those two modules
import nothing at runtime, so Node resolves them exactly as they are written.

The modules this helper exists for do have runtime imports, and they are written
the way the application's bundler resolves them: extensionless, and `@/` for the
source root. Node's ESM resolver understands neither form. So the surface's `.ts`
files are copied into a temporary tree with exactly those two specifier shapes
rewritten and nothing else touched — no module is stubbed, no behaviour is
replaced, and the code that runs is the code that ships. A driver that reached a
module the copy had altered would be proving something about the copy.

Type-only imports (`import type`) are erased before Node ever resolves them, so
the surface's `react` and `@ctower/client` type imports need no handling here.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import tools.process_execution as process_execution  # noqa: PLR0402

_ROOT = Path(__file__).resolve().parents[2]
_SURFACE = Path("apps/ctower-ui/src")
_TIMEOUT_SECONDS = 120
_SPECIFIER = re.compile(r'(from\s+")([^"]+)(")')


def _resolved(specifier: str, source: Path) -> str:
    """The same file, named the way Node's resolver needs it."""
    if specifier.startswith("@/"):
        target = _ROOT / _SURFACE / specifier[len("@/") :]
        relative = Path(
            *([".."] * (len(source.relative_to(_ROOT / _SURFACE).parts) - 1))
        ) / target.relative_to(_ROOT / _SURFACE)
        specifier = (
            f"./{relative.as_posix()}" if not str(relative).startswith(".") else str(relative)
        )
        candidate = target
    elif specifier.startswith("."):
        candidate = (source.parent / specifier).resolve()
    else:
        # a bare specifier is a built-in or a package; those resolve unchanged
        return specifier
    if candidate.suffix == "":
        for suffix in (".ts", ".tsx"):
            if candidate.with_suffix(suffix).is_file():
                return f"{specifier}{suffix}"
    return specifier


def _rewrite(text: str, source: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{_resolved(match.group(2), source)}{match.group(3)}"

    return _SPECIFIER.sub(replace, text)


def _materialize(into: Path) -> None:
    surface = _ROOT / _SURFACE
    for path in sorted(p for p in surface.rglob("*") if p.suffix in (".ts", ".tsx")):
        text = path.read_text(encoding="utf-8")
        rewritten = _rewrite(text, path)
        target = into / _SURFACE / path.relative_to(surface)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rewritten, encoding="utf-8")


def drive(fixture: Path) -> dict[str, Any]:
    """Run one checked-in driver and return the object it emitted."""
    node = shutil.which("node")
    if node is None:
        # not a skip: this is a required suite, and a verification host without
        # the toolchain it declares is a failure, not a reason to pass quietly
        raise RuntimeError("node is not on PATH; the surface fixtures cannot run")
    with tempfile.TemporaryDirectory() as directory:
        tree = Path(directory)
        _materialize(tree)
        driver = tree / fixture.relative_to(_ROOT)
        driver.parent.mkdir(parents=True, exist_ok=True)
        driver.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
        completed = process_execution.run(
            (node, "--no-warnings", str(driver)),
            timeout_seconds=_TIMEOUT_SECONDS,
            check=True,
            capture_output=True,
        )
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise TypeError(f"{fixture.name} did not emit an object")
    return parsed


def materialize(into: Path) -> None:
    """Expose the copy so a test can assert it is only a copy."""
    _materialize(into)


def specifiers(text: str) -> list[str]:
    """Every import specifier in one module, for the copy's own assertions."""
    return [match.group(2) for match in _SPECIFIER.finditer(text)]


def without_specifiers(text: str) -> str:
    """The module with its import specifiers removed, so a copy can be diffed."""
    return _SPECIFIER.sub("", text)


SURFACE = _SURFACE
ROOT = _ROOT
