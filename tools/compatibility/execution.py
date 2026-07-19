from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from tools.compatibility.contract import Candidate, CompatibilityError, CompatibilityMatrix

_ARTIFACT_REASON = {"status": "not_exercised", "reason_code": "artifact_absent"}


def execute_candidate_matrix(
    matrix: CompatibilityMatrix, environments: tuple[str, ...]
) -> list[dict[str, object]]:
    """Execute candidates through private clean-environment adapters."""
    uv = _required_tool("uv", required="macos-host" in environments)
    docker = _required_tool("docker", required="linux-container" in environments)
    probe_source = Path(__file__).with_name("probe.py")
    runs: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="ctower-compat-") as raw_root:
        scratch = Path(raw_root)
        for candidate in matrix.candidates:
            if "macos-host" in environments:
                runs.append(_execute_host(matrix, candidate, scratch, probe_source, uv))
            if "linux-container" in environments:
                runs.append(_execute_linux(matrix, candidate, scratch, probe_source, docker))
    return runs


def _required_tool(name: str, *, required: bool) -> str:
    executable = shutil.which(name)
    if required and executable is None:
        raise CompatibilityError(f"{name} is required for compatibility evidence")
    return executable or name


def _execute_host(
    matrix: CompatibilityMatrix,
    candidate: Candidate,
    scratch: Path,
    probe_source: Path,
    bootstrap_uv: str,
) -> dict[str, object]:
    run_root = scratch / f"host-{candidate.version}"
    run_root.mkdir()
    probe = run_root / "probe.py"
    shutil.copyfile(probe_source, probe)
    venv = run_root / "venv"
    environment = _host_environment(run_root)
    uv = _uv_command(bootstrap_uv, matrix.uv_version)
    commands: list[list[str]] = []
    _prepare_host(candidate, matrix, venv, uv, environment, commands)
    python = venv / "bin" / "python"
    freeze = _checked([*uv, "pip", "freeze", "--python", str(python)], environment, commands).stdout
    output = run_root / "result.json"
    _run_probe(python, probe, output, candidate, matrix, environment, commands)
    run = _read_probe(output)
    replacements = {str(run_root): "$CTOWER_COMPAT_ROOT", bootstrap_uv: "$BOOTSTRAP_UV"}
    return _decorate_run(run, matrix, "macos-host", freeze, commands, replacements)


def _host_environment(run_root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "UV_CACHE_DIR": str(run_root / "uv-cache"),
        "UV_PYTHON_INSTALL_DIR": str(run_root / "managed-python"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _uv_command(bootstrap_uv: str, version: str) -> list[str]:
    return [bootstrap_uv, "tool", "run", "--from", f"uv=={version}", "uv"]


def _prepare_host(
    candidate: Candidate,
    matrix: CompatibilityMatrix,
    venv: Path,
    uv: list[str],
    environment: dict[str, str],
    commands: list[list[str]],
) -> None:
    _checked([*uv, "python", "install", candidate.version], environment, commands)
    _checked(
        [
            *uv,
            "venv",
            "--python",
            candidate.version,
            "--python-preference",
            "only-managed",
            str(venv),
        ],
        environment,
        commands,
    )
    _checked(
        [
            *uv,
            "pip",
            "install",
            "--python",
            str(venv / "bin" / "python"),
            "--no-cache",
            *matrix.requirements,
        ],
        environment,
        commands,
    )


def _run_probe(
    python: Path,
    probe: Path,
    output: Path,
    candidate: Candidate,
    matrix: CompatibilityMatrix,
    environment: dict[str, str],
    commands: list[list[str]],
) -> None:
    _checked(
        [
            str(python),
            str(probe),
            "--version",
            candidate.version,
            "--requirements",
            json.dumps(matrix.requirements),
            "--output",
            str(output),
        ],
        environment,
        commands,
    )


def _execute_linux(
    matrix: CompatibilityMatrix,
    candidate: Candidate,
    scratch: Path,
    probe_source: Path,
    docker: str,
) -> dict[str, object]:
    run_root = scratch / f"linux-{candidate.version}"
    run_root.mkdir()
    shutil.copyfile(probe_source, run_root / "probe.py")
    name = f"ctower-compat-{candidate.version.replace('.', '-')}-{uuid.uuid4().hex[:8]}"
    commands: list[list[str]] = []
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        _create_container(docker, name, run_root, candidate, environment, commands)
        freeze = _exercise_container(docker, name, matrix, candidate, environment, commands)
        image_details = _inspect_image(docker, candidate, environment, commands)
        run = _read_probe(run_root / "result.json")
        replacements = {
            str(run_root): "$CTOWER_COMPAT_ROOT",
            docker: "$DOCKER",
            name: "$CTOWER_CONTAINER",
        }
        result = _decorate_run(run, matrix, "linux-container", freeze, commands, replacements)
        result["image"] = candidate.linux_image
        _inject_image_identity(result, image_details)
        return result
    finally:
        _spawn([docker, "rm", "-f", name], {**os.environ})


def _create_container(
    docker: str,
    name: str,
    run_root: Path,
    candidate: Candidate,
    environment: dict[str, str],
    commands: list[list[str]],
) -> None:
    _checked(
        [
            docker,
            "create",
            "--name",
            name,
            "--network",
            "bridge",
            "--mount",
            f"type=bind,source={run_root},target=/fixture",
            "--workdir",
            "/fixture",
            candidate.linux_image,
            "sleep",
            "infinity",
        ],
        environment,
        commands,
    )
    _checked([docker, "start", name], environment, commands)


def _exercise_container(
    docker: str,
    name: str,
    matrix: CompatibilityMatrix,
    candidate: Candidate,
    environment: dict[str, str],
    commands: list[list[str]],
) -> str:
    prefix = [docker, "exec", name, "python"]
    _checked(
        [
            *prefix,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            *matrix.requirements,
        ],
        environment,
        commands,
    )
    freeze = _checked([*prefix, "-m", "pip", "freeze", "--all"], environment, commands).stdout
    _checked(
        [
            *prefix,
            "/fixture/probe.py",
            "--version",
            candidate.version,
            "--requirements",
            json.dumps(matrix.requirements),
            "--output",
            "/fixture/result.json",
        ],
        environment,
        commands,
    )
    return freeze


def _inspect_image(
    docker: str,
    candidate: Candidate,
    environment: dict[str, str],
    commands: list[list[str]],
) -> dict[str, Any]:
    raw = _checked(
        [docker, "image", "inspect", candidate.linux_image], environment, commands
    ).stdout
    value = json.loads(raw)
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise CompatibilityError("docker image inspection was malformed")
    return value[0]


def _inject_image_identity(run: dict[str, object], image: dict[str, Any]) -> None:
    interpreter = run.get("interpreter")
    if not isinstance(interpreter, dict):
        raise CompatibilityError("probe omitted interpreter identity")
    interpreter["image_id"] = image["Id"]
    interpreter["image_architecture"] = image["Architecture"]
    interpreter["image_os"] = image["Os"]


def _decorate_run(
    run: dict[str, Any],
    matrix: CompatibilityMatrix,
    environment_name: str,
    freeze: str,
    commands: list[list[str]],
    replacements: dict[str, str],
) -> dict[str, object]:
    _inject_resolution(run, freeze, _canonical_commands(commands, replacements=replacements))
    run["environment"] = environment_name
    run["product_artifacts"] = {
        artifact: dict(_ARTIFACT_REASON) for artifact in matrix.product_artifacts
    }
    return run


def _checked(
    command: list[str],
    environment: dict[str, str],
    commands: list[list[str]],
) -> subprocess.CompletedProcess[str]:
    commands.append(command)
    started = time.monotonic()
    result = _spawn(command, environment)
    if result.returncode != 0:
        duration = round((time.monotonic() - started) * 1000)
        message = result.stderr.strip() or result.stdout.strip()
        raise CompatibilityError(
            f"command failed after {duration} ms: {command!r}: {message[-2000:]}"
        )
    return result


def _spawn(command: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        actions = [
            (os.POSIX_SPAWN_DUP2, stdout.fileno(), 1),
            (os.POSIX_SPAWN_DUP2, stderr.fileno(), 2),
        ]
        process_id = os.posix_spawn(command[0], command, environment, file_actions=actions)
        _, raw_status = os.waitpid(process_id, 0)
        stdout.seek(0)
        stderr.seek(0)
        return subprocess.CompletedProcess(
            command,
            os.waitstatus_to_exitcode(raw_status),
            stdout.read().decode(errors="replace"),
            stderr.read().decode(errors="replace"),
        )


def _read_probe(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CompatibilityError(f"malformed probe report: {error}") from error
    if not isinstance(value, dict):
        raise CompatibilityError("probe report must be an object")
    return value


def _inject_resolution(run: dict[str, Any], freeze: str, commands: list[list[str]]) -> None:
    observations = run.get("observations")
    if not isinstance(observations, list):
        raise CompatibilityError("probe observations must be an array")
    resolution = next(
        (item for item in observations if item.get("id") == "dependency_resolution"), None
    )
    if not isinstance(resolution, dict):
        raise CompatibilityError("probe omitted dependency resolution")
    lines = sorted(line.strip() for line in freeze.splitlines() if line.strip())
    details = resolution.setdefault("details", {})
    details["lock"] = lines
    details["lock_sha256"] = hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    details["commands"] = commands


def _canonical_commands(
    commands: list[list[str]], *, replacements: dict[str, str]
) -> list[list[str]]:
    ordered = sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)
    return [[_replace(argument, ordered) for argument in command] for command in commands]


def _replace(argument: str, replacements: list[tuple[str, str]]) -> str:
    for source, replacement in replacements:
        argument = argument.replace(source, replacement)
    return argument
