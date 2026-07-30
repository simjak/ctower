"""Prove that one installed environment provides the checkout's console scripts."""

from __future__ import annotations

import argparse
import json
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import tools.process_execution as process_execution  # noqa: PLR0402

__all__ = ["main"]

_PROBE_TIMEOUT_SECONDS = 60.0
_RESULT_PREFIX = "runtime-preflight-result: "
_PROBE = f"""
import importlib.metadata
import json
import sys

expected = json.loads(sys.stdin.read())
installed = {{}}
for entry_point in importlib.metadata.entry_points(group="console_scripts"):
    installed.setdefault(entry_point.name, []).append(entry_point)

checks = []
for name, target in sorted(expected.items()):
    candidates = installed.get(name, [])
    error = None
    if not candidates:
        error = "console entry point is not installed"
    elif len(candidates) != 1:
        error = f"expected one installed entry point, found {{len(candidates)}}"
    elif candidates[0].value != target:
        error = (
            f"installed target {{candidates[0].value!r}} does not match "
            f"checkout target {{target!r}}"
        )
    else:
        try:
            loaded = candidates[0].load()
        except Exception as exc:
            error = f"cannot load {{target!r}}: {{type(exc).__name__}}: {{exc}}"
        else:
            if not callable(loaded):
                error = f"loaded target {{target!r}} is not callable"
    checks.append({{"name": name, "target": target, "error": error}})

print({_RESULT_PREFIX!r} + json.dumps({{"checks": checks}}, sort_keys=True))
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Check project-script entry points in one candidate Python environment."""

    parser = argparse.ArgumentParser(prog="python -m tools.runtime_preflight")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--python", type=Path, required=True)
    arguments = parser.parse_args(argv)

    try:
        scripts = _project_scripts(arguments.pyproject)
        python = arguments.python.absolute()
        if not python.is_file():
            raise FileNotFoundError(f"candidate interpreter does not exist: {python}")
        checks = _probe(python, scripts)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"runtime preflight: FAIL\n  {error}")
        return 1

    failures = tuple(check for check in checks if check["error"] is not None)
    print(f"runtime preflight: {'FAIL' if failures else 'PASS'}")
    print(f"environment: {python}")
    print(f"project scripts: {len(checks)}")
    for check in checks:
        outcome = "FAIL" if check["error"] is not None else "PASS"
        detail = f": {check['error']}" if check["error"] is not None else ""
        print(f"  {outcome} {check['name']} -> {check['target']}{detail}")
    return 1 if failures else 0


def _project_scripts(pyproject: Path) -> dict[str, str]:
    with pyproject.open("rb") as stream:
        document = tomllib.load(stream)
    project = _mapping(document.get("project"), "[project]")
    scripts = _mapping(project.get("scripts"), "[project.scripts]")
    if not scripts:
        raise ValueError("[project.scripts] must declare at least one console script")
    parsed: dict[str, str] = {}
    for name, target in scripts.items():
        if not isinstance(name, str) or not name:
            raise TypeError("[project.scripts] names must be non-empty strings")
        if not isinstance(target, str) or not target:
            raise TypeError(f"[project.scripts].{name} must be a non-empty string")
        parsed[name] = target
    return parsed


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a table")
    return cast("Mapping[str, object]", value)


def _probe(python: Path, scripts: Mapping[str, str]) -> tuple[dict[str, str | None], ...]:
    result = process_execution.run(
        [str(python), "-I", "-c", _PROBE],
        timeout_seconds=_PROBE_TIMEOUT_SECONDS,
        check=False,
        input_text=json.dumps(scripts, sort_keys=True),
        capture_output=True,
    )
    output = result.stdout or ""
    payload_line = next(
        (line for line in reversed(output.splitlines()) if line.startswith(_RESULT_PREFIX)),
        None,
    )
    if result.returncode != 0 or payload_line is None:
        detail = output.strip() or f"candidate interpreter exited {result.returncode}"
        raise RuntimeError(f"candidate interpreter probe failed: {detail}")
    payload = json.loads(payload_line.removeprefix(_RESULT_PREFIX))
    if not isinstance(payload, dict) or not isinstance(payload.get("checks"), list):
        raise TypeError("candidate interpreter returned a malformed probe result")
    return tuple(_check(item) for item in payload["checks"])


def _check(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise TypeError("candidate interpreter returned a malformed script check")
    name = value.get("name")
    target = value.get("target")
    error = value.get("error")
    if not isinstance(name, str) or not isinstance(target, str):
        raise TypeError("candidate interpreter returned an untyped script check")
    if error is not None and not isinstance(error, str):
        raise TypeError("candidate interpreter returned an untyped script error")
    return {"name": name, "target": target, "error": error}


if __name__ == "__main__":
    raise SystemExit(main())
