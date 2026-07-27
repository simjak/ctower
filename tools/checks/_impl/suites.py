"""Private expected-suite manifest parsing and structural verification."""

from __future__ import annotations

import ast
import asyncio
import os
import re
import sys
import tomllib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from tools.checks.owned_processes import (
    TerminationOutcome,
    TerminationResult,
    terminate_owned_processes,
)
from tools.checks.report import ExpectedSuitesReport, SuiteDisposition, SuiteResult

__all__ = ["verify_expected_suites"]

_SCHEMA = "ctower.expected-suites/v1"
_MANIFEST_PATH = "tools/checks/expected-suites.toml"
_MAX_TIMEOUT_SECONDS = 3600
_PROCESS_TERM_GRACE_SECONDS = 0.25
_PROCESS_KILL_GRACE_SECONDS = 0.25
_SUITE_OWNER_ENV = "CTOWER_VERIFY_SUITE_OWNER"
_MANIFEST_FIELDS = {"schema", "manifest_version", "active_phase", "phase_order", "suite"}
_BACKLOG_ID = re.compile(r"^CT-(?:L0|I[1-9][0-9]*)-[0-9]{3}$")
_SUITE_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_PORTABLE_COMMAND_TOKEN = re.compile(r"^\{[a-z][a-z0-9_-]*\}$")
_PORTABLE_PYTHON = "{python}"
_SUITE_FIELDS = {
    "id",
    "owner",
    "phase",
    "status",
    "path",
    "patterns",
    "command",
    "timeout_seconds",
}
_SKIP_DECORATORS = {
    "pytest.mark.skip",
    "pytest.mark.skipif",
    "pytest.mark.xfail",
    "unittest.skip",
    "unittest.skipIf",
    "unittest.skipUnless",
}


class ExpectedSuitesConfigurationError(ValueError):
    """The expected-suite manifest cannot safely define verification scope."""


@dataclass(frozen=True, slots=True)
class _SuiteSpec:
    suite_id: str
    owner: str
    phase: str
    status: str
    path: str
    patterns: tuple[str, ...]
    command: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class _Manifest:
    manifest_version: int
    active_phase: str
    phase_order: tuple[str, ...]
    suites: tuple[_SuiteSpec, ...]


def verify_expected_suites(root: Path, *, execute: bool = False) -> ExpectedSuitesReport:
    """Verify current suites exist and deferred suites remain explicitly non-passing."""

    try:
        manifest = _load_manifest(root)
    except ExpectedSuitesConfigurationError as error:
        return ExpectedSuitesReport(
            schema=_SCHEMA,
            manifest_version=0,
            active_phase="invalid",
            suites=(),
            manifest_errors=(str(error),),
        )
    active_index = manifest.phase_order.index(manifest.active_phase)
    results = tuple(_verify_suite(root, manifest, active_index, suite) for suite in manifest.suites)
    if execute and not any(item.disposition is SuiteDisposition.FAILED for item in results):
        results = asyncio.run(_execute_required_suites(root, manifest.suites, results))
    return ExpectedSuitesReport(
        schema=_SCHEMA,
        manifest_version=manifest.manifest_version,
        active_phase=manifest.active_phase,
        suites=results,
    )


def _load_manifest(root: Path) -> _Manifest:
    path = root / _MANIFEST_PATH
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ExpectedSuitesConfigurationError(f"cannot load {path}: {error}") from error
    version, active_phase, phase_order = _parse_manifest_header(data)
    suites = _parse_suites(data)
    return _Manifest(version, active_phase, phase_order, suites)


def _parse_manifest_header(data: Mapping[str, object]) -> tuple[int, str, tuple[str, ...]]:
    if set(data) != _MANIFEST_FIELDS:
        raise ExpectedSuitesConfigurationError(
            f"manifest must contain exactly {sorted(_MANIFEST_FIELDS)}"
        )
    if data.get("schema") != _SCHEMA:
        raise ExpectedSuitesConfigurationError(f"schema must be {_SCHEMA}")
    version = data.get("manifest_version")
    active_phase = data.get("active_phase")
    phase_order = _string_tuple(data.get("phase_order"), "phase_order")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ExpectedSuitesConfigurationError("manifest_version must be a positive integer")
    if not isinstance(active_phase, str) or active_phase not in phase_order:
        raise ExpectedSuitesConfigurationError("active_phase must occur in phase_order")
    _validate_phase_order(phase_order)
    return version, active_phase, phase_order


def _parse_suites(data: Mapping[str, object]) -> tuple[_SuiteSpec, ...]:
    suites_data = data.get("suite")
    if not isinstance(suites_data, list) or not suites_data:
        raise ExpectedSuitesConfigurationError("suite must be a non-empty array of tables")
    suites = tuple(_parse_suite(item, index) for index, item in enumerate(suites_data))
    if len({suite.suite_id for suite in suites}) != len(suites):
        raise ExpectedSuitesConfigurationError("suite IDs must be unique")
    return suites


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ExpectedSuitesConfigurationError(f"{label} must be a non-empty string array")
    return tuple(value)


def _validate_phase_order(phases: tuple[str, ...]) -> None:
    if len(set(phases)) != len(phases):
        raise ExpectedSuitesConfigurationError("phase_order entries must be unique")
    invalid = tuple(phase for phase in phases if _BACKLOG_ID.fullmatch(phase) is None)
    if invalid:
        raise ExpectedSuitesConfigurationError(
            f"phase_order contains invalid backlog IDs: {invalid}"
        )


def _parse_suite(value: object, index: int) -> _SuiteSpec:
    strings = _suite_strings(value, index)
    suite_id = strings["id"]
    owner = strings["owner"]
    phase = strings["phase"]
    status = strings["status"]
    path = strings["path"]
    _validate_suite_identity(index, suite_id, owner, phase, status)
    _validate_relative_path(path, f"suite[{index}].path")
    if not isinstance(value, dict):
        raise ExpectedSuitesConfigurationError(f"suite[{index}] must be a table")
    patterns = _string_tuple(value["patterns"], f"suite[{index}].patterns")
    for pattern in patterns:
        _validate_relative_path(pattern, f"suite[{index}].patterns")
    return _SuiteSpec(
        suite_id=suite_id,
        owner=owner,
        phase=phase,
        status=status,
        path=path,
        patterns=patterns,
        command=_command(value["command"], index),
        timeout_seconds=_timeout(value["timeout_seconds"], index),
    )


def _suite_strings(value: object, index: int) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != _SUITE_FIELDS:
        raise ExpectedSuitesConfigurationError(
            f"suite[{index}] must contain exactly {sorted(_SUITE_FIELDS)}"
        )
    strings = {name: value[name] for name in ("id", "owner", "phase", "status", "path")}
    if not all(isinstance(item, str) and item for item in strings.values()):
        raise ExpectedSuitesConfigurationError(f"suite[{index}] scalar fields must be strings")
    return {name: str(item) for name, item in strings.items()}


def _validate_suite_identity(
    index: int, suite_id: str, owner: str, phase: str, status: str
) -> None:
    if _SUITE_ID.fullmatch(suite_id) is None:
        raise ExpectedSuitesConfigurationError(f"suite[{index}].id has an invalid stable key")
    if _BACKLOG_ID.fullmatch(owner) is None or _BACKLOG_ID.fullmatch(phase) is None:
        raise ExpectedSuitesConfigurationError(f"suite[{index}] owner and phase need stable CT IDs")
    if status not in {"required", "deferred"}:
        raise ExpectedSuitesConfigurationError(
            f"suite[{index}] status must be required or deferred"
        )


def _timeout(value: object, index: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= _MAX_TIMEOUT_SECONDS
    ):
        raise ExpectedSuitesConfigurationError(
            f"suite[{index}].timeout_seconds must be an integer from 1 through "
            f"{_MAX_TIMEOUT_SECONDS}"
        )
    return value


def _command(value: object, index: int) -> tuple[str, ...]:
    command = _string_tuple(value, f"suite[{index}].command")
    for position, argument in enumerate(command):
        if argument == _PORTABLE_PYTHON:
            if position != 0:
                raise ExpectedSuitesConfigurationError(
                    f"suite[{index}].command portable Python token must be the executable"
                )
            continue
        if _PORTABLE_PYTHON in argument:
            raise ExpectedSuitesConfigurationError(
                f"suite[{index}].command portable Python token must be an exact argv element"
            )
        if _PORTABLE_COMMAND_TOKEN.fullmatch(argument) is not None:
            raise ExpectedSuitesConfigurationError(
                f"suite[{index}].command contains unsupported portable token {argument!r}"
            )
    return command


def _validate_relative_path(value: str, label: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value or value in {"", "."}:
        raise ExpectedSuitesConfigurationError(f"{label} must be a normalized relative path")


def _verify_suite(
    root: Path, manifest: _Manifest, active_index: int, suite: _SuiteSpec
) -> SuiteResult:
    if suite.phase not in manifest.phase_order:
        return _failure(suite, "phase is absent from phase_order")
    phase_is_current = manifest.phase_order.index(suite.phase) <= active_index
    expected_status = "required" if phase_is_current else "deferred"
    if suite.status != expected_status:
        return _failure(
            suite,
            f"status {suite.status!r} conflicts with active phase; expected {expected_status!r}",
        )
    if suite.status == "deferred":
        return _result(
            suite,
            SuiteDisposition.NOT_YET_REQUIRED,
            "declared for a later manifest phase; not yet required and not counted as passing",
        )
    errors = _required_suite_errors(root, suite)
    if errors:
        return _failure(suite, "; ".join(errors))
    return _result(
        suite,
        SuiteDisposition.REQUIRED,
        "current required suite is present, non-empty, and has no unexpected skip",
    )


def _required_suite_errors(root: Path, suite: _SuiteSpec) -> tuple[str, ...]:
    suite_path = root / suite.path
    try:
        resolved_path = suite_path.resolve()
        resolved_path.relative_to(root.resolve())
    except (OSError, ValueError):
        return ("suite path escapes the repository",)
    if not resolved_path.is_dir():
        return ("required suite path is missing or is not a directory",)
    files = tuple(
        sorted(
            {
                path
                for pattern in suite.patterns
                for path in resolved_path.rglob(pattern)
                if path.is_file()
            }
        )
    )
    if not files:
        return ("required suite matches no test files",)
    errors = [error for path in files for error in _test_file_errors(path, root)]
    if not any(_contains_test(path) for path in files):
        errors.append("required suite contains no executable test definitions")
    return tuple(errors)


def _test_file_errors(path: Path, root: Path) -> tuple[str, ...]:
    relative = path.relative_to(root).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return (f"cannot read {relative}: {error}",)
    if not source.strip():
        return (f"{relative} is empty",)
    if path.suffix == ".py":
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as error:
            return (f"{relative} is invalid Python: {error.msg}",)
        if _contains_skip(tree):
            return (f"{relative} contains an unexpected skip directive",)
    return ()


def _contains_test(path: Path) -> bool:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    if path.suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False
        return any(
            isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
            and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
    if path.suffix in {".js", ".ts", ".tsx"}:
        return bool(re.search(r"\b(?:it|test)\s*\(", source))
    return True


def _contains_skip(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef) and any(
            _qualified_name(item) in _SKIP_DECORATORS for item in node.decorator_list
        ):
            return True
        if isinstance(node, ast.Call):
            call_name = _qualified_name(node.func)
            if call_name in {"pytest.importorskip", "pytest.skip", "unittest.SkipTest"}:
                return True
            if call_name.endswith(".skipTest"):
                return True
    return False


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _qualified_name(node.func)
    return ""


async def _execute_required_suites(
    root: Path, specs: tuple[_SuiteSpec, ...], results: tuple[SuiteResult, ...]
) -> tuple[SuiteResult, ...]:
    executed: list[SuiteResult] = []
    for spec, result in zip(specs, results, strict=True):
        if result.disposition is SuiteDisposition.REQUIRED:
            executed.append(await _execute_suite(root, spec))
        else:
            executed.append(result)
    return tuple(executed)


async def _execute_suite(root: Path, suite: _SuiteSpec) -> SuiteResult:
    command = _execution_command(suite.command)
    process_owner = f"{suite.suite_id}-{uuid.uuid4().hex}"
    environment = os.environ.copy()
    environment[_SUITE_OWNER_ENV] = process_owner
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=root,
            env=environment,
            start_new_session=True,
        )
    except OSError as error:
        return _failure(suite, f"cannot execute command: {error}")
    try:
        return_code = await asyncio.wait_for(process.wait(), timeout=suite.timeout_seconds)
    except TimeoutError:
        cleanup = await _terminate_suite_process(process, process_owner)
        cleanup_failure = _cleanup_failure_message(cleanup)
        suffix = "" if cleanup_failure is None else f"; {cleanup_failure}"
        return _failure(suite, f"command timed out after {suite.timeout_seconds} seconds{suffix}")
    except BaseException:
        await _terminate_suite_process(process, process_owner)
        raise
    cleanup = await _terminate_suite_process(process, process_owner)
    return _completed_suite_result(suite, return_code, cleanup=cleanup)


def _completed_suite_result(
    suite: _SuiteSpec, return_code: int, *, cleanup: TerminationResult
) -> SuiteResult:
    cleanup_failure = _cleanup_failure_message(cleanup)
    if cleanup_failure is not None:
        return _failure(suite, cleanup_failure)
    if return_code != 0:
        return _failure(suite, f"command failed with exit code {return_code}")
    return _result(suite, SuiteDisposition.PASSED, "current required suite command passed")


async def _terminate_suite_process(
    process: asyncio.subprocess.Process, process_owner: str
) -> TerminationResult:
    result = await terminate_owned_processes(
        _SUITE_OWNER_ENV,
        process_owner,
        term_grace_seconds=_PROCESS_TERM_GRACE_SECONDS,
        kill_grace_seconds=_PROCESS_KILL_GRACE_SECONDS,
        candidate_pids=(process.pid,),
        candidate_session_ids=(process.pid,),
    )
    if result.outcome in {TerminationOutcome.SURVIVED, TerminationOutcome.UNKNOWN}:
        return result
    if process.returncode is not None:
        return result
    try:
        await asyncio.wait_for(process.wait(), timeout=_PROCESS_KILL_GRACE_SECONDS)
    except TimeoutError:
        return result.with_outcome(TerminationOutcome.SURVIVED)
    return result


def _cleanup_failure_message(cleanup: TerminationResult) -> str | None:
    if cleanup.outcome is TerminationOutcome.UNKNOWN:
        return f"owned process cleanup UNKNOWN ({cleanup.observation_summary()})"
    if cleanup.outcome is TerminationOutcome.SURVIVED:
        return "owned process cleanup failed"
    return None


def _execution_command(command: tuple[str, ...]) -> tuple[str, ...]:
    if command[0] == _PORTABLE_PYTHON:
        return (sys.executable, *command[1:])
    return command


def _failure(suite: _SuiteSpec, message: str) -> SuiteResult:
    return _result(suite, SuiteDisposition.FAILED, message)


def _result(suite: _SuiteSpec, disposition: SuiteDisposition, message: str) -> SuiteResult:
    return SuiteResult(
        suite_id=suite.suite_id,
        owner=suite.owner,
        phase=suite.phase,
        path=suite.path,
        command=suite.command,
        timeout_seconds=suite.timeout_seconds,
        disposition=disposition,
        message=message,
    )
