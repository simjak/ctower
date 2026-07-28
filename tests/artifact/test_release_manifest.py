from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.release_manifest import interface


def test_manifest_binds_clean_source_artifact_resources_runtime_and_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    artifacts = tmp_path / "artifacts"
    source.mkdir()
    artifacts.mkdir()
    _write(source / "packages/ctower-kernel/migrations/manifest.json", '{"migrations":[]}\n')
    _write(source / "generated/.generated-manifest.json", '{"artifacts":[]}\n')
    _write(source / "packs/workflow.yaml", "schema: ctower.test/v1\n")
    _git(source, "init")
    _git(source, "config", "user.name", "Ctower Test")
    _git(source, "config", "user.email", "ctower-test@example.invalid")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "fixture")
    wheel = artifacts / "ctower_workspace-0.0.0-py3-none-any.whl"
    wheel.write_bytes(b"tested-wheel")
    output = artifacts / "manifest.json"
    monkeypatch.setattr(interface, "_python_identity", lambda _path: ("3.13.14", "standard"))

    manifest = interface.build_manifest(
        source,
        wheel,
        output,
        python_executable=Path("/approved/python"),
        predecessor="sha256:" + "1" * 64,
    )

    encoded = json.loads(output.read_text(encoding="utf-8"))
    assert manifest.source_commit == _git(source, "rev-parse", "HEAD")
    assert manifest.source_tree == _git(source, "rev-parse", "HEAD^{tree}")
    assert encoded["python"] == {
        "implementation": "CPython",
        "version": "3.13.14",
        "gil": "standard",
    }
    assert encoded["predecessor"] == "sha256:" + "1" * 64
    assert interface.verify_manifest(
        output,
        wheel,
        source / "packs",
        python_executable=Path("/approved/python"),
    ) == manifest

    wheel.write_bytes(b"tampered-wheel")
    with pytest.raises(ValueError, match="differs"):
        interface.verify_manifest(
            output,
            wheel,
            source / "packs",
            python_executable=Path("/approved/python"),
        )


def test_manifest_refuses_dirty_source_and_nonapproved_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write(source / "packages/ctower-kernel/migrations/manifest.json", "{}\n")
    _write(source / "generated/.generated-manifest.json", "{}\n")
    _write(source / "packs/pack.yaml", "pack: fixed\n")
    _git(source, "init")
    _git(source, "config", "user.name", "Ctower Test")
    _git(source, "config", "user.email", "ctower-test@example.invalid")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "fixture")
    wheel = tmp_path / "artifact.whl"
    wheel.write_bytes(b"wheel")
    output = tmp_path / "manifest.json"
    _write(source / "dirty.txt", "not committed\n")
    monkeypatch.setattr(interface, "_python_identity", lambda _path: ("3.13.14", "standard"))

    with pytest.raises(ValueError, match="clean source"):
        interface.build_manifest(
            source,
            wheel,
            output,
            python_executable=Path("/approved/python"),
            predecessor=None,
        )

    monkeypatch.undo()
    monkeypatch.setattr(
        interface.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="CPython\n3.12.0\nstandard\n"),
    )
    with pytest.raises(ValueError, match="approved exact"):
        interface._python_identity(Path("/usr/bin/python3"))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
