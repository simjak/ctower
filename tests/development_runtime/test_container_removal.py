"""Readback-verified forced-removal tests for the E2 development runtime."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import tools.development_runtime.interface as lifecycle
import tools.process_execution as process_execution  # noqa: PLR0402

__all__: tuple[str, ...] = ()

_DAEMON_UNREACHABLE_STDERR = (
    "failed to connect to the docker API at unix:///var/run/docker.sock; check if "
    "the path is correct and if the daemon is running: dial unix "
    "/var/run/docker.sock: connect: no such file or directory\n"
)


def _not_found_stderr(name: str) -> str:
    return f"Error response from daemon: No such container: {name}\n"


@pytest.mark.parametrize(
    ("returncode", "stderr", "expected"),
    [
        pytest.param(0, "", True, id="inspect-exit-zero"),
        pytest.param(1, _not_found_stderr("ctower-test"), False, id="not-found-marker"),
    ],
)
def test_container_exists_discriminates_definite_states(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int,
    stderr: str,
    expected: bool,
) -> None:
    monkeypatch.setattr(
        process_execution,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=returncode, stdout="", stderr=stderr),
    )
    monkeypatch.setattr(lifecycle, "docker_path", lambda: "/usr/bin/docker")

    assert lifecycle._container_exists("ctower-test") is expected


def test_container_exists_refuses_by_name_when_inspect_fails_for_an_unknown_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F1: a daemon-error inspect must UNKNOWN-refuse, never read as 'gone'."""
    monkeypatch.setattr(
        process_execution,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr=_DAEMON_UNREACHABLE_STDERR
        ),
    )
    monkeypatch.setattr(lifecycle, "docker_path", lambda: "/usr/bin/docker")

    with pytest.raises(RuntimeError, match="ctower-test-unreachable"):
        lifecycle._container_exists("ctower-test-unreachable")


def test_force_remove_container_succeeds_once_readback_confirms_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def run(arguments: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(tuple(arguments))
        if tuple(arguments[1:3]) == ("container", "rm"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            returncode=1, stdout="", stderr=_not_found_stderr("ctower-test-gone")
        )

    monkeypatch.setattr(process_execution, "run", run)
    monkeypatch.setattr(lifecycle, "docker_path", lambda: "/usr/bin/docker")

    lifecycle._force_remove_container("ctower-test-gone")

    assert calls == [
        ("/usr/bin/docker", "container", "rm", "--force", "ctower-test-gone"),
        ("/usr/bin/docker", "container", "inspect", "ctower-test-gone"),
    ]


def test_force_remove_container_refuses_by_name_when_container_lingers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revert-probe: pre-fix `_force_remove_container` returned here silently."""
    rm_calls: list[tuple[str, ...]] = []

    def run(arguments: list[str], **_kwargs: object) -> SimpleNamespace:
        if tuple(arguments[1:3]) == ("container", "rm"):
            rm_calls.append(tuple(arguments))
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(process_execution, "run", run)
    monkeypatch.setattr(lifecycle, "docker_path", lambda: "/usr/bin/docker")
    monkeypatch.setattr(lifecycle, "_container_state", lambda _name: "running")

    with pytest.raises(RuntimeError, match="ctower-test-stuck") as raised:
        lifecycle._force_remove_container("ctower-test-stuck")

    assert len(rm_calls) == lifecycle._FORCE_REMOVE_ATTEMPTS
    assert "running" in str(raised.value)


def test_force_remove_container_refuses_by_name_when_readback_cannot_tell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F1: daemon-error/timeout-shaped readback must UNKNOWN-refuse, not silent-gone.

    A single rm attempt, not a blind retry loop: once the readback itself is
    unreadable, retrying the same unreachable daemon cannot resolve it.
    """
    rm_calls: list[tuple[str, ...]] = []

    def run(arguments: list[str], **_kwargs: object) -> SimpleNamespace:
        if tuple(arguments[1:3]) == ("container", "rm"):
            rm_calls.append(tuple(arguments))
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr=_DAEMON_UNREACHABLE_STDERR)

    monkeypatch.setattr(process_execution, "run", run)
    monkeypatch.setattr(lifecycle, "docker_path", lambda: "/usr/bin/docker")

    with pytest.raises(RuntimeError, match="ctower-test-unreachable"):
        lifecycle._force_remove_container("ctower-test-unreachable")

    assert len(rm_calls) == 1
