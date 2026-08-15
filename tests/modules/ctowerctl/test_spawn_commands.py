"""CLI boundary tests for generated spawn-custody commands."""

from __future__ import annotations

from uuid import uuid4

from ctower_client.models import SpawnRecordCreateRequest, SpawnTransitionRequest
from ctowerctl import _spawn_commands
from ctowerctl._parser import parse_arguments

__all__: tuple[str, ...] = ()


def test_spawn_record_command_builds_the_pre_dispatch_fact() -> None:
    command_id = uuid4()
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "spawn",
            "record",
            "--command-id",
            str(command_id),
            "--project-key",
            "ctower",
            "--seat-key",
            "engineer",
            "--crew-name",
            "mc-engineer-r3000-spawn",
            "--task-file-ref",
            "coordination/spawn.task.md",
            "--worktree-path",
            "/srv/projects/ctower/.worktrees/r3000-spawn",
            "--harness",
            "codex-crew",
            "--model",
            "gpt-5-codex",
            "--effort",
            "high",
        ]
    )

    payload = _spawn_commands.build_mutation(arguments)

    assert isinstance(payload.request, SpawnRecordCreateRequest)
    assert payload.request.project_key == "ctower"
    assert payload.request.workspace_id is None
    assert payload.path_parameters == {}


def test_spawn_transition_command_builds_an_append_only_post() -> None:
    spawn_id = uuid4()
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "spawn",
            "transition",
            str(spawn_id),
            "--command-id",
            str(uuid4()),
            "--to-status",
            "running",
            "--reason",
            "driver accepted the host session",
        ]
    )

    payload = _spawn_commands.build_mutation(arguments)

    assert isinstance(payload.request, SpawnTransitionRequest)
    assert payload.request.to_status == "running"
    assert payload.path_parameters == {"spawn_id": str(spawn_id)}


def test_spawn_queries_are_explicit_generated_client_calls() -> None:
    spawn_id = uuid4()
    listed = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "spawn",
            "list",
            "--project-key",
            "ctower",
            "--status",
            "running",
        ]
    )
    shown = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "spawn",
            "show",
            str(spawn_id),
        ]
    )

    assert listed.cli_name == "spawn list"
    assert listed.project_key == "ctower"
    assert listed.status == "running"
    assert shown.cli_name == "spawn show"
    assert shown.spawn_id == spawn_id
    assert _spawn_commands.mutation_command_names() == {
        "spawn record",
        "spawn transition",
    }
    assert _spawn_commands.query_command_names() == {"spawn list", "spawn show"}
