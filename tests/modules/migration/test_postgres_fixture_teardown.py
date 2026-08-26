"""Regression tests for migration fixture crash teardown."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from . import _postgres as postgres_fixture

__all__: tuple[str, ...] = ()


def test_migration_fixture_arms_crash_teardown_before_compose_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str]] = []

    def register(project: str) -> None:
        events.append(("register", project))

    def compose(command: list[str], _environment: dict[str, str], *arguments: str) -> None:
        events.append((arguments[0], command[3]))
        raise RuntimeError("stop after Compose start")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(postgres_fixture, "_register_crash_teardown", register, raising=False)
    monkeypatch.setattr(postgres_fixture, "_compose", compose)

    database = postgres_fixture.isolated_database()
    with pytest.raises(RuntimeError, match="stop after Compose start"):
        next(database)

    assert [event for event, _project in events] == ["register", "up"]
    assert events[0][1] == events[1][1]


def test_crash_teardown_is_idempotent_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = "ctower-migration-test-project"
    attempts = 0

    def fail_run(*_args: object, **_kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("simulated teardown failure")

    monkeypatch.setattr(postgres_fixture, "_CRASH_TEARDOWN_PROJECTS", {project}, raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(subprocess, "run", fail_run)

    postgres_fixture._teardown_compose_project(project)
    postgres_fixture._teardown_compose_project(project)

    assert attempts == 1
    assert set() == postgres_fixture._CRASH_TEARDOWN_PROJECTS
