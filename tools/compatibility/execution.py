from __future__ import annotations

import hashlib
import re
import tempfile
import uuid
from pathlib import Path

from pydantic import ValidationError

from tools.compatibility.contract import (
    ArtifactEvidence,
    Candidate,
    CompatibilityError,
    CompatibilityMatrix,
    CompatibilityRun,
    DockerContainerInspection,
    DockerImageInspection,
    EnvironmentVariable,
    HostIdentity,
    ImageIdentity,
    ProbeResult,
    ProcessOperation,
    ProcessRequest,
    ProcessResult,
    ProductArtifactEvidence,
    ResolutionEvidence,
)
from tools.compatibility.environment import (
    bootstrap_environment,
    container_prefix,
    copy_probe_package,
    host_environment,
    macos_architecture,
    macos_python_request,
)
from tools.compatibility.environment import (
    docker_environment as build_docker_environment,
)
from tools.compatibility.process import ExecutionPort, LocalExecutionPort
from tools.compatibility.schema import parse_probe, read_json_object

_OUTPUT_LIMIT = 131_072
_GRACE_MS = 2_000
_TIMEOUTS: dict[ProcessOperation, int] = {
    "uv-bootstrap": 900_000,
    "python-install": 900_000,
    "venv-create": 180_000,
    "package-install": 900_000,
    "dependency-freeze": 60_000,
    "compatibility-probe": 900_000,
    "docker-create": 300_000,
    "docker-start": 60_000,
    "docker-package-install": 900_000,
    "docker-freeze": 60_000,
    "docker-probe": 900_000,
    "docker-inspect": 60_000,
    "docker-cleanup": 30_000,
    "probe-subprocess": 180_000,
}


def execute_candidate_matrix(
    matrix: CompatibilityMatrix, *, execution_port: ExecutionPort | None = None
) -> tuple[CompatibilityRun, ...]:
    """Run all fixed L0 legs with one explicit process boundary."""
    port = execution_port or LocalExecutionPort()
    uv = _required_tool(port, "uv")
    docker = _required_tool(port, "docker")
    host = port.host_identity()
    if host.system != "Darwin":
        raise CompatibilityError("macos-host execution requires a declared Darwin host")
    macos_architecture(host.machine)
    runs: list[CompatibilityRun] = []
    with tempfile.TemporaryDirectory(prefix="ctower-compat-") as raw_root:
        scratch = Path(raw_root)
        pinned_uv, bootstrap_commands = _bootstrap_uv(matrix, scratch, uv, port)
        for candidate in matrix.candidates:
            runs.append(
                _execute_host(
                    matrix,
                    candidate,
                    scratch,
                    host,
                    uv,
                    pinned_uv,
                    bootstrap_commands,
                    port,
                )
            )
            runs.append(_execute_linux(matrix, candidate, scratch, docker, port))
    return tuple(runs)


def _execute_host(
    matrix: CompatibilityMatrix,
    candidate: Candidate,
    scratch: Path,
    host: HostIdentity,
    bootstrap_uv: str,
    pinned_uv: str,
    bootstrap_commands: tuple[tuple[str, ...], ...],
    port: ExecutionPort,
) -> CompatibilityRun:
    run_root = scratch / f"host-{candidate.version}"
    run_root.mkdir(mode=0o700)
    package_root = copy_probe_package(run_root)
    environment = host_environment(run_root, package_root, matrix)
    freeze, commands, output = _run_host_commands(
        matrix,
        candidate,
        run_root,
        host,
        pinned_uv,
        bootstrap_commands,
        environment,
        port,
    )
    probe = parse_probe(read_json_object(output, label="probe result"))
    replacements = {
        str(run_root.parent): "$CTOWER_MATRIX_ROOT",
        bootstrap_uv: "$BOOTSTRAP_UV",
        pinned_uv: "$PINNED_UV",
    }
    return CompatibilityRun(
        **probe.model_dump(mode="python", by_alias=True),
        environment="macos-host",
        host_identity=host,
        resolution=_resolution(freeze, commands, replacements),
        product_artifacts=_absent_artifacts(),
        image_identity=None,
    )


def _run_host_commands(
    matrix: CompatibilityMatrix,
    candidate: Candidate,
    run_root: Path,
    host: HostIdentity,
    pinned_uv: str,
    bootstrap_commands: tuple[tuple[str, ...], ...],
    environment: tuple[EnvironmentVariable, ...],
    port: ExecutionPort,
) -> tuple[str, list[tuple[str, ...]], Path]:
    uv = (pinned_uv,)
    commands = list(bootstrap_commands)
    venv = run_root / "venv"
    python_request = macos_python_request(candidate.version, host.machine)
    install_python = (*uv, "python", "install", python_request)
    _checked(port, "python-install", install_python, environment)
    commands.append(install_python)
    venv_command = (
        *uv,
        "venv",
        "--python",
        python_request,
        "--python-preference",
        "only-managed",
        str(venv),
    )
    _checked(port, "venv-create", venv_command, environment)
    commands.append(venv_command)
    python = str(venv / "bin" / "python")
    install = (*uv, "pip", "install", "--python", python, "--no-cache", *matrix.requirements)
    _checked(port, "package-install", install, environment)
    commands.append(install)
    freeze_command = (*uv, "pip", "freeze", "--python", python)
    freeze = _checked(port, "dependency-freeze", freeze_command, environment).stdout
    commands.append(freeze_command)
    output = run_root / "result.json"
    probe_command = (
        python,
        "-m",
        "ctower_compat_probe.probe",
        "--version",
        candidate.version,
        "--output",
        str(output),
    )
    _checked(port, "compatibility-probe", probe_command, environment)
    commands.append(probe_command)
    return freeze, commands, output


def _execute_linux(
    matrix: CompatibilityMatrix,
    candidate: Candidate,
    scratch: Path,
    docker: str,
    port: ExecutionPort,
) -> CompatibilityRun:
    run_root = scratch / f"linux-{candidate.version}"
    run_root.mkdir(mode=0o700)
    copy_probe_package(run_root)
    (run_root / "home").mkdir(mode=0o700)
    (run_root / "tmp").mkdir(mode=0o700)
    name = f"ctower-compat-{candidate.version.replace('.', '-')}-{uuid.uuid4().hex[:12]}"
    owner_label = uuid.uuid4().hex
    docker_environment = build_docker_environment(docker)
    container_id: str | None = None
    try:
        container_id, create = _create_linux_container(
            candidate, run_root, name, owner_label, docker, docker_environment, port
        )
        return _run_linux_container(
            matrix,
            candidate,
            run_root,
            name,
            owner_label,
            container_id,
            docker,
            docker_environment,
            create,
            port,
        )
    finally:
        _cleanup_container(container_id, docker, docker_environment, port)


def _create_linux_container(
    candidate: Candidate,
    run_root: Path,
    name: str,
    owner_label: str,
    docker: str,
    environment: tuple[EnvironmentVariable, ...],
    port: ExecutionPort,
) -> tuple[str, tuple[str, ...]]:
    create = (
        docker,
        "create",
        "--name",
        name,
        "--network",
        "bridge",
        "--label",
        f"dev.ctower.compatibility.run={owner_label}",
        "--mount",
        f"type=bind,source={run_root},target=/fixture",
        candidate.linux_image,
        "/usr/local/bin/python",
        "-c",
        "import time; time.sleep(86400)",
    )
    container_id = _checked(port, "docker-create", create, environment).stdout.strip()
    if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise CompatibilityError("docker create returned a malformed container identity")
    return container_id, create


def _run_linux_container(
    matrix: CompatibilityMatrix,
    candidate: Candidate,
    run_root: Path,
    name: str,
    owner_label: str,
    container_id: str,
    docker: str,
    environment: tuple[EnvironmentVariable, ...],
    create: tuple[str, ...],
    port: ExecutionPort,
) -> CompatibilityRun:
    commands = [create]
    start = (docker, "start", container_id)
    _checked(port, "docker-start", start, environment)
    commands.append(start)
    image_inspection = _inspect_image(port, docker, candidate, environment)
    container_inspection = _inspect_container(port, docker, container_id, owner_label, environment)
    if container_inspection.image_id != image_inspection.image_id:
        raise CompatibilityError("created container image does not match the pinned image")
    freeze, probe, workload_commands = _run_linux_workload(
        matrix, candidate, run_root, container_id, docker, environment, port
    )
    commands.extend(workload_commands)
    image = _image_identity(candidate, image_inspection, container_inspection)
    replacements = {
        str(run_root): "$CTOWER_COMPAT_ROOT",
        docker: "$DOCKER",
        name: f"$CTOWER_CONTAINER[{candidate.version}]",
        container_id: f"$CTOWER_CONTAINER_ID[{candidate.version}]",
    }
    return CompatibilityRun(
        **probe.model_dump(mode="python", by_alias=True),
        environment="linux-container",
        host_identity=HostIdentity(
            system=probe.interpreter.system,
            machine=probe.interpreter.machine,
        ),
        resolution=_resolution(freeze, commands, replacements),
        product_artifacts=_absent_artifacts(),
        image_identity=image,
    )


def _run_linux_workload(
    matrix: CompatibilityMatrix,
    candidate: Candidate,
    run_root: Path,
    container_id: str,
    docker: str,
    environment: tuple[EnvironmentVariable, ...],
    port: ExecutionPort,
) -> tuple[str, ProbeResult, list[tuple[str, ...]]]:
    prefix = container_prefix(docker, container_id, matrix)
    install = (
        *prefix,
        "/usr/local/bin/python",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        *matrix.requirements,
    )
    _checked(port, "docker-package-install", install, environment)
    freeze_command = (*prefix, "/usr/local/bin/python", "-m", "pip", "freeze", "--all")
    freeze = _checked(port, "docker-freeze", freeze_command, environment).stdout
    probe_command = (
        *prefix,
        "/usr/local/bin/python",
        "-m",
        "ctower_compat_probe.probe",
        "--version",
        candidate.version,
        "--output",
        "/fixture/result.json",
    )
    _checked(port, "docker-probe", probe_command, environment)
    probe = parse_probe(read_json_object(run_root / "result.json", label="probe result"))
    return freeze, probe, [install, freeze_command, probe_command]


def _image_identity(
    candidate: Candidate,
    image: DockerImageInspection,
    container: DockerContainerInspection,
) -> ImageIdentity:
    return ImageIdentity(
        requested=candidate.linux_image,
        container_id=container.container_id,
        owner_label=container.owner_label,
        image_id=image.image_id,
        repository_digests=image.repository_digests,
        os=image.os,
        architecture=image.architecture,
    )


def _cleanup_container(
    container_id: str | None,
    docker: str,
    environment: tuple[EnvironmentVariable, ...],
    port: ExecutionPort,
) -> None:
    if container_id is None:
        return
    cleanup = (docker, "rm", "-f", container_id)
    result = _run(port, "docker-cleanup", cleanup, environment)
    if result.timed_out or result.returncode != 0:
        detail = _failure_detail(result)
        raise CompatibilityError(f"docker cleanup failed for {container_id}: {detail}")


def _bootstrap_uv(
    matrix: CompatibilityMatrix,
    scratch: Path,
    bootstrap_uv: str,
    port: ExecutionPort,
) -> tuple[str, tuple[tuple[str, ...], ...]]:
    environment = bootstrap_environment(scratch, matrix)
    install = (bootstrap_uv, "tool", "install", "--force", f"uv=={matrix.uv_version}")
    _checked(port, "uv-bootstrap", install, environment)
    pinned_uv = scratch / "uv-bin" / "uv"
    if not pinned_uv.is_file():
        raise CompatibilityError("pinned uv bootstrap did not create the expected executable")
    verify = (str(pinned_uv), "--version")
    version = _checked(port, "uv-bootstrap", verify, environment).stdout.strip()
    if version.split()[:2] != ["uv", matrix.uv_version]:
        raise CompatibilityError("pinned uv bootstrap reported the wrong version")
    return str(pinned_uv), (install, verify)


def _inspect_image(
    port: ExecutionPort,
    docker: str,
    candidate: Candidate,
    environment: tuple[EnvironmentVariable, ...],
) -> DockerImageInspection:
    template = (
        '{"image_id":{{json .Id}},"architecture":{{json .Architecture}},'
        '"os":{{json .Os}},"repository_digests":{{json .RepoDigests}}}'
    )
    result = _checked(
        port,
        "docker-inspect",
        (docker, "image", "inspect", "--format", template, candidate.linux_image),
        environment,
    )
    try:
        return DockerImageInspection.model_validate_json(result.stdout)
    except ValidationError as error:
        raise CompatibilityError(f"docker image inspection was malformed: {error}") from error


def _inspect_container(
    port: ExecutionPort,
    docker: str,
    container_id: str,
    owner_label: str,
    environment: tuple[EnvironmentVariable, ...],
) -> DockerContainerInspection:
    template = (
        '{"container_id":{{json .Id}},"image_id":{{json .Image}},'
        '"owner_label":{{json (index .Config.Labels "dev.ctower.compatibility.run")}}}'
    )
    result = _checked(
        port,
        "docker-inspect",
        (docker, "container", "inspect", "--format", template, container_id),
        environment,
    )
    try:
        inspection = DockerContainerInspection.model_validate_json(result.stdout)
    except ValidationError as error:
        raise CompatibilityError(f"docker container inspection was malformed: {error}") from error
    if inspection.container_id != container_id or inspection.owner_label != owner_label:
        raise CompatibilityError("created container ownership identity did not round-trip")
    return inspection


def _resolution(
    freeze: str,
    commands: list[tuple[str, ...]],
    replacements: dict[str, str],
) -> ResolutionEvidence:
    lock = tuple(sorted(line.strip() for line in freeze.splitlines() if line.strip()))
    payload = ("\n".join(lock) + "\n").encode()
    ordered = sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)
    sanitized = tuple(
        tuple(_replace(argument, ordered) for argument in command) for command in commands
    )
    return ResolutionEvidence(
        lock=lock,
        lock_sha256=hashlib.sha256(payload).hexdigest(),
        commands=sanitized,
    )


def _absent_artifacts() -> ProductArtifactEvidence:
    absent = ArtifactEvidence(status="not_exercised", reason_code="artifact_absent")
    return ProductArtifactEvidence(release_helper_wheel=absent, generated_clients=absent)


def _required_tool(port: ExecutionPort, name: str) -> str:
    executable = port.resolve_tool(name)
    if executable is None or not executable.startswith("/"):
        raise CompatibilityError(f"{name} is required as an absolute executable path")
    return executable


def _checked(
    port: ExecutionPort,
    operation: ProcessOperation,
    argv: tuple[str, ...],
    environment: tuple[EnvironmentVariable, ...],
) -> ProcessResult:
    result = _run(port, operation, argv, environment)
    if result.timed_out or result.returncode != 0:
        raise CompatibilityError(f"{operation} failed: {_failure_detail(result)}")
    return result


def _run(
    port: ExecutionPort,
    operation: ProcessOperation,
    argv: tuple[str, ...],
    environment: tuple[EnvironmentVariable, ...],
) -> ProcessResult:
    return port.run(
        ProcessRequest(
            operation=operation,
            argv=argv,
            environment=environment,
            timeout_ms=_TIMEOUTS[operation],
            terminate_grace_ms=_GRACE_MS,
            output_limit_bytes=_OUTPUT_LIMIT,
        )
    )


def _failure_detail(result: ProcessResult) -> str:
    state = "timed out" if result.timed_out else f"exited {result.returncode}"
    message = result.stderr.strip() or result.stdout.strip()
    return f"{state}; {message[-2000:]}" if message else state


def _replace(argument: str, replacements: list[tuple[str, str]]) -> str:
    for source, replacement in replacements:
        argument = argument.replace(source, replacement)
    return argument
