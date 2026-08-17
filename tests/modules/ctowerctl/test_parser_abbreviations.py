"""The public CLI accepts authored long option names, never their prefixes."""

from __future__ import annotations

from uuid import uuid4

import pytest

from ctowerctl import _beat_dispatch_commands
from ctowerctl._parser import parse_arguments

__all__: tuple[str, ...] = ()

_BASE_URL_PREFIXES = tuple(f"--{'base-url'[:length]}" for length in range(1, len("base-url")))


@pytest.mark.parametrize("prefix", _BASE_URL_PREFIXES)
@pytest.mark.parametrize("joined", [False, True])
def test_public_cli_does_not_abbreviate_base_url(prefix: str, *, joined: bool) -> None:
    attacker = "https://attacker.invalid"
    override = [f"{prefix}={attacker}"] if joined else [prefix, attacker]

    with pytest.raises(ValueError, match="usage:"):
        parse_arguments([*override, "control", "health"])


def test_beat_retire_parses_and_builds_the_strict_generated_request() -> None:
    command_id = uuid4()
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "beat-dispatch",
            "retire",
            "ctower.beat.health@1",
            "--command-id",
            str(command_id),
        ]
    )

    payload = _beat_dispatch_commands.build_mutation(arguments)

    assert arguments.cli_name == "beat-dispatch retire"
    assert arguments.command_id == command_id
    assert payload.request.model_dump(mode="json") == {}
    assert payload.path_parameters == {"routine_ref": "ctower.beat.health@1"}
