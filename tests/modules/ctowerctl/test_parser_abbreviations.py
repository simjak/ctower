"""The public CLI accepts authored long option names, never their prefixes."""

from __future__ import annotations

import pytest

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
