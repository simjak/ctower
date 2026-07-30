"""Bootstrap preflight tests for checkout-derived console scripts."""

from __future__ import annotations

import os
import sys
import sysconfig
import tomllib
import venv
from pathlib import Path

import pytest

from tools.runtime_preflight import main

__all__: tuple[str, ...] = ()


def test_preflight_passes_when_every_checkout_script_loads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = _environment(tmp_path, {"example": "fixture_cli:main"})
    pyproject = _pyproject(tmp_path, {"example": "fixture_cli:main"})

    assert main(["--pyproject", str(pyproject), "--python", str(environment)]) == 0
    assert "runtime preflight: PASS" in _output(capsys)


def test_preflight_discovers_a_script_added_only_to_pyproject(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = _environment(tmp_path, {"example": "fixture_cli:main"})
    pyproject = _pyproject(tmp_path, {"example": "fixture_cli:main"})
    document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    scripts = document["project"]["scripts"]
    scripts["added-after-preflight-was-written"] = "fixture_cli:main"
    pyproject.write_text(
        _toml_scripts(scripts),
        encoding="utf-8",
    )

    assert main(["--pyproject", str(pyproject), "--python", str(environment)]) == 1
    output = _output(capsys)
    assert "added-after-preflight-was-written" in output
    assert "console entry point is not installed" in output


def test_executable_stub_cannot_hide_an_unimportable_entry_point(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scripts = {"path-only-would-pass": "module_that_is_not_installed:main"}
    environment = _environment(tmp_path, scripts, install_module=False)
    pyproject = _pyproject(tmp_path, scripts)
    stub = environment.parent / "path-only-would-pass"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o700)

    assert os.access(stub, os.X_OK), "the deliberately weak path check would pass"
    assert main(["--pyproject", str(pyproject), "--python", str(environment)]) == 1
    output = _output(capsys)
    assert "path-only-would-pass" in output
    assert "cannot load 'module_that_is_not_installed:main'" in output


def test_checkout_source_cannot_hide_an_unimportable_installed_entry_point(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scripts = {"checkout-leak-would-pass": "tools.runtime_preflight:main"}
    environment = _environment(tmp_path, scripts, install_module=False)
    pyproject = _pyproject(tmp_path, scripts)

    assert main(["--pyproject", str(pyproject), "--python", str(environment)]) == 1
    output = _output(capsys)
    assert "checkout-leak-would-pass" in output
    assert "ModuleNotFoundError" in output


def test_runbook_preflights_before_every_persistent_runtime_command() -> None:
    runbook = (Path(__file__).parents[2] / "deploy/private-vps/development/README.md").read_text(
        encoding="utf-8"
    )

    preflight = runbook.index("-m tools.runtime_preflight")
    manifest = runbook.index("/venv/bin/ctower-runtime-manifest build")
    installation = runbook.index("/venv/bin/ctower-private-vps install-runtime")

    assert preflight < manifest < installation
    assert "\nctower-runtime-manifest " not in runbook
    assert "\nctower-private-vps " not in runbook
    assert "\nctower-shadow-ctl " not in runbook


def _environment(
    root: Path,
    scripts: dict[str, str],
    *,
    install_module: bool = True,
) -> Path:
    home = root / "environment"
    venv.EnvBuilder(with_pip=False).create(home)
    python = home / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    purelib = _purelib(python)
    if install_module:
        (purelib / "fixture_cli.py").write_text(
            "def main():\n    return None\n",
            encoding="utf-8",
        )
    metadata = purelib / "fixture-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: fixture\nVersion: 1.0\n",
        encoding="utf-8",
    )
    entries = "\n".join(f"{name} = {target}" for name, target in sorted(scripts.items()))
    (metadata / "entry_points.txt").write_text(
        f"[console_scripts]\n{entries}\n",
        encoding="utf-8",
    )
    return python


def _purelib(python: Path) -> Path:
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    if sys.platform == "win32":
        return python.parents[1] / "Lib/site-packages"
    expected = python.parents[1] / f"lib/{version}/site-packages"
    if expected.exists():
        return expected
    return Path(sysconfig.get_path("purelib"))


def _pyproject(root: Path, scripts: dict[str, str]) -> Path:
    path = root / "pyproject.toml"
    path.write_text(_toml_scripts(scripts), encoding="utf-8")
    return path


def _toml_scripts(scripts: dict[str, str]) -> str:
    entries = "\n".join(f'{name} = "{target}"' for name, target in sorted(scripts.items()))
    return f'[project]\nname = "fixture"\n\n[project.scripts]\n{entries}\n'


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out
